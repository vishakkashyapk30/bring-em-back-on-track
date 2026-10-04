"""`make identity`: resolve every source system's customer key to one golden ID.

Passes (docs/profiling/profiling_decisions.md §2):
  1. CRM clusters: shared national_id_hash, duplicate_of_crm_id (cannot-link on conflicting national IDs).
  2. Accounts -> CRM: majority vote over the valid CRM IDs in account_monthly_snapshot (fixes mistyped IDs).
  3. Source keys (cards, lending, core-banking CIF) -> golden ID: majority of their linked accounts; all accounts
     of the key follow. The bureau shares the CIF with core banking.
  4. Remaining source keys: scored matching (identity/matching.py); unique best >= 0.90 links, 0.70-0.90 goes to
     the steward review queue.
  5. Collections: coll_customer_ref is a CRM ID.

Writes schema `identity` in the warehouse: crm_golden, source_key_xref, account_xref, identity_xref, review_queue,
metrics. Reads silver.* only.
"""

from __future__ import annotations

import logging
import time

import duckdb
import pandas as pd

from common.config import get_settings
from identity import matching
from identity.cluster import MAX_CRM_RECORDS_PER_CLUSTER, assign_golden_ids, cluster

log = logging.getLogger("identity")

SYSTEMS = {  # source_system -> (silver table, account id column is `account_id`)
    "cards": "silver.stg_card_accounts",
    "lending": "silver.stg_loan_accounts",
    "core_banking": "silver.stg_deposit_accounts",
}


def crm_clusters(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    crm = con.sql("SELECT crm_customer_id, national_id_hash FROM silver.stg_customers").df()
    # Only real string hashes count; pandas NaN is truthy and would wrongly trigger the cannot-link guard.
    nid = {c: (h if isinstance(h, str) and h else None) for c, h in zip(crm.crm_customer_id, crm.national_id_hash, strict=True)}
    nid_edges = con.sql("""
        SELECT crm_customer_id a, min(crm_customer_id) OVER (PARTITION BY national_id_hash) b
        FROM silver.stg_customers WHERE national_id_hash IS NOT NULL""").fetchall()
    dup_edges = con.sql("""
        SELECT c.crm_customer_id, c.duplicate_of_crm_id FROM silver.stg_customers c
        JOIN silver.stg_customers d ON d.crm_customer_id = c.duplicate_of_crm_id""").fetchall()
    roots = cluster(crm.crm_customer_id, [e for e in nid_edges if e[0] != e[1]] + dup_edges, nid)
    gid = assign_golden_ids(roots)
    df = pd.DataFrame({"crm_customer_id": list(roots), "root": list(roots.values())})
    df["golden_id"] = df.root.map(gid)
    df["cluster_size"] = df.groupby("golden_id").crm_customer_id.transform("count")
    dup_set = {a for a, _ in dup_edges} | {b for _, b in dup_edges}
    nid_set = {a for a, b in nid_edges if a != b} | {b for a, b in nid_edges if a != b}
    df["link_evidence"] = [
        "national_id+duplicate_of" if (c in nid_set and c in dup_set) else
        "national_id" if c in nid_set else "duplicate_of" if c in dup_set else "single_record"
        for c in df.crm_customer_id
    ]
    df["review_flag"] = df.cluster_size > MAX_CRM_RECORDS_PER_CLUSTER
    conflicts = len(dup_edges) - sum(1 for a, b in dup_edges if roots[a] == roots[b])
    log.info("crm: %d records -> %d golden ids; %d duplicate_of links refused by the national-ID guard",
             len(df), df.golden_id.nunique(), conflicts)
    return df.drop(columns="root")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    s = get_settings()
    t0 = time.perf_counter()
    con = duckdb.connect(str(s.warehouse_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS identity")

    # Pass 1: CRM clusters
    crm = crm_clusters(con)
    con.register("crm_df", crm)
    con.execute("CREATE OR REPLACE TABLE identity.crm_golden AS SELECT * FROM crm_df")

    # Pass 2: account -> golden via snapshot majority vote (valid CRM IDs only)
    con.execute("""
        CREATE OR REPLACE TEMP TABLE acct_vote AS
        WITH v AS (
            SELECT s.account_id, g.golden_id, count(*) votes
            FROM silver.stg_account_snapshot s JOIN identity.crm_golden g USING (crm_customer_id)
            GROUP BY ALL),
        r AS (SELECT *, sum(votes) OVER (PARTITION BY account_id) n_total,
                     count(*) OVER (PARTITION BY account_id) n_golden,
                     row_number() OVER (PARTITION BY account_id ORDER BY votes DESC, golden_id) rn FROM v)
        SELECT account_id, golden_id, votes / n_total AS vote_share, n_golden FROM r WHERE rn = 1""")

    # Accounts of every system, with their source key
    union_accounts = " UNION ALL ".join(
        f"SELECT '{sysname}' source_system, account_id, product_type, src_customer_ref source_ref FROM {tbl}"
        for sysname, tbl in SYSTEMS.items())
    con.execute(f"CREATE OR REPLACE TEMP TABLE accounts AS {union_accounts}")

    # Pass 3: source key -> golden (majority of its voted accounts); conflicts flagged
    con.execute("""
        CREATE OR REPLACE TEMP TABLE key_det AS
        WITH k AS (
            SELECT a.source_system, a.source_ref, v.golden_id, count(*) n_acc, avg(v.vote_share) avg_share
            FROM accounts a JOIN acct_vote v USING (account_id) GROUP BY ALL),
        r AS (SELECT *, sum(n_acc) OVER (PARTITION BY source_system, source_ref) n_total,
                     count(*) OVER (PARTITION BY source_system, source_ref) n_golden,
                     row_number() OVER (PARTITION BY source_system, source_ref ORDER BY n_acc DESC, golden_id) rn FROM k)
        SELECT source_system, source_ref, golden_id, 'deterministic' match_method,
               round(avg_share * n_acc / n_total, 3) match_confidence, n_golden > 1 AS has_conflict FROM r WHERE rn = 1""")
    # Bureau shares the 10-digit CIF with core banking
    con.execute("""
        INSERT INTO key_det
        SELECT 'bureau', e.bank_subject_ref, k.golden_id, 'deterministic', k.match_confidence, k.has_conflict
        FROM silver.stg_external e JOIN key_det k
          ON k.source_system = 'core_banking' AND k.source_ref = e.bank_subject_ref""")

    # Pass 4: scored matching for keys still unlinked
    probe_parts = [
        f"""SELECT '{sysname}' source_system, src_customer_ref source_ref, any_value(last_name_key) last_name_key,
                   any_value(first_initial) first_initial, any_value(dob) dob, any_value(postal) postal,
                   any_value(phone_digits) phone_digits
            FROM {tbl} GROUP BY ALL"""
        for sysname, tbl in SYSTEMS.items()]
    probe_parts.append("""SELECT 'bureau', bank_subject_ref, any_value(last_name_key), any_value(first_initial),
                                 any_value(dob), any_value(postal), NULL FROM silver.stg_external GROUP BY ALL""")
    con.execute(f"CREATE OR REPLACE TEMP TABLE all_keys AS {' UNION ALL '.join(probe_parts)}")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE idx AS
        SELECT DISTINCT g.golden_id, c.last_name_key, c.first_initial, c.dob, c.postal, c.phone_digits
        FROM silver.stg_customers c JOIN identity.crm_golden g USING (crm_customer_id)""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE probe AS
        SELECT k.* FROM all_keys k ANTI JOIN key_det d USING (source_system, source_ref)""")
    con.execute(f"CREATE OR REPLACE TEMP TABLE scored AS {matching.score_sql()}")

    # Evaluate the scorer on deterministic links (answer key): sample of linked keys run through the same scorer
    con.execute("""
        CREATE OR REPLACE TEMP TABLE probe_eval AS
        SELECT k.* FROM all_keys k SEMI JOIN key_det d USING (source_system, source_ref)
        USING SAMPLE 20000 ROWS (reservoir, 42)""")
    con.execute("ALTER TABLE probe RENAME TO probe_live")
    con.execute("ALTER TABLE probe_eval RENAME TO probe")
    ev = con.sql(f"""
        WITH s AS ({matching.score_sql()})
        SELECT count(*) evaluated,
               count(*) FILTER (WHERE s.score >= {matching.AUTO_LINK} AND s.n_plausible = 1) auto_linked,
               count(*) FILTER (WHERE s.score >= {matching.AUTO_LINK} AND s.n_plausible = 1
                                 AND s.golden_id = d.golden_id) auto_correct
        FROM probe p LEFT JOIN s USING (source_system, source_ref)
        JOIN key_det d USING (source_system, source_ref)""").fetchone()
    con.execute("ALTER TABLE probe RENAME TO probe_eval")
    con.execute("ALTER TABLE probe_live RENAME TO probe")
    evaluated, auto_linked, auto_correct = ev
    precision = auto_correct / auto_linked if auto_linked else None
    recall = auto_correct / evaluated if evaluated else None

    con.execute(f"""
        CREATE OR REPLACE TABLE identity.source_key_xref AS
        SELECT source_system, source_ref, golden_id, match_method, match_confidence, has_conflict FROM key_det
        UNION ALL
        SELECT source_system, source_ref, golden_id, 'probabilistic', score, false
        FROM scored WHERE score >= {matching.AUTO_LINK} AND n_plausible = 1""")
    con.execute(f"""
        CREATE OR REPLACE TABLE identity.review_queue AS
        SELECT 'P-' || lpad(cast(row_number() OVER (ORDER BY source_system, source_ref) AS varchar), 7, '0') pair_id,
               source_system, source_ref, golden_id candidate_golden_id, score,
               CASE WHEN n_plausible > 1 THEN 'several plausible candidates' ELSE 'score in review band' END reason
        FROM scored
        WHERE score >= {matching.REVIEW} AND NOT (score >= {matching.AUTO_LINK} AND n_plausible = 1)""")

    # Account-level xref: snapshot vote where available, else the key's golden ID
    con.execute("""
        CREATE OR REPLACE TABLE identity.account_xref AS
        SELECT a.source_system, a.account_id, a.product_type, a.source_ref,
               coalesce(v.golden_id, x.golden_id) golden_id,
               CASE WHEN v.golden_id IS NOT NULL THEN 'deterministic' ELSE x.match_method END match_method,
               coalesce(round(v.vote_share, 3), x.match_confidence) match_confidence,
               CASE WHEN v.golden_id IS NOT NULL THEN 'snapshot_vote'
                    WHEN x.golden_id IS NOT NULL THEN 'source_key' END link_path
        FROM accounts a
        LEFT JOIN acct_vote v USING (account_id)
        LEFT JOIN identity.source_key_xref x USING (source_system, source_ref)""")

    # Collections cases: coll_customer_ref is a CRM ID, but ~2.8% carry a mistyped digit; fall back to the case's
    # primary account. Child tables (contacts, promises, notes, transcripts) inherit the case's golden ID.
    con.execute("""
        CREATE OR REPLACE TABLE identity.case_xref AS
        SELECT k.case_id, k.coll_customer_ref,
               coalesce(g.golden_id, x.golden_id) golden_id,
               CASE WHEN g.golden_id IS NOT NULL THEN 'coll_customer_ref'
                    WHEN x.golden_id IS NOT NULL THEN 'primary_account' END link_path,
               g.golden_id IS NULL AS crm_ref_invalid
        FROM silver.collections_cases k
        LEFT JOIN identity.crm_golden g ON g.crm_customer_id = k.coll_customer_ref
        LEFT JOIN identity.account_xref x ON x.account_id = k.primary_account_id""")

    # Contract-facing xref: CRM records + source keys + collections
    con.execute("""
        CREATE OR REPLACE TABLE identity.identity_xref AS
        SELECT golden_id, 'crm' source_system, crm_customer_id source_ref, crm_customer_id,
               CASE WHEN link_evidence = 'single_record' THEN 'deterministic' ELSE 'deterministic' END match_method,
               1.0 match_probability, link_evidence evidence
        FROM identity.crm_golden
        UNION ALL
        SELECT golden_id, source_system, source_ref, NULL, match_method, match_confidence,
               CASE WHEN has_conflict THEN 'conflicting accounts, majority used' END
        FROM identity.source_key_xref
        UNION ALL
        SELECT golden_id, 'collections', case_id, coll_customer_ref, 'deterministic',
               CASE WHEN link_path = 'coll_customer_ref' THEN 1.0 ELSE 0.95 END, link_path
        FROM identity.case_xref WHERE golden_id IS NOT NULL""")

    # Metrics for the data quality report
    m = con.sql("""
        SELECT
          (SELECT count(*) FROM identity.crm_golden) crm_records,
          (SELECT count(DISTINCT golden_id) FROM identity.crm_golden) golden_ids,
          (SELECT count(*) FROM identity.crm_golden WHERE cluster_size > 1) crm_records_in_multi_clusters,
          (SELECT count(*) FROM identity.crm_golden WHERE review_flag) crm_records_flagged_large_cluster,
          (SELECT count(*) FROM accounts) accounts,
          (SELECT count(*) FROM identity.account_xref WHERE golden_id IS NOT NULL) accounts_linked,
          (SELECT count(*) FROM identity.account_xref WHERE link_path = 'snapshot_vote') accounts_by_snapshot_vote,
          (SELECT count(*) FROM identity.account_xref WHERE link_path = 'source_key') accounts_by_source_key,
          (SELECT count(*) FROM all_keys) source_keys,
          (SELECT count(*) FROM key_det) keys_deterministic,
          (SELECT count(*) FROM identity.source_key_xref WHERE match_method = 'probabilistic') keys_probabilistic,
          (SELECT count(*) FROM identity.review_queue) keys_in_review,
          (SELECT count(*) FROM probe) - (SELECT count(*) FROM identity.source_key_xref
                                          WHERE match_method = 'probabilistic')
            - (SELECT count(*) FROM identity.review_queue) keys_unlinked,
          (SELECT count(*) FROM key_det WHERE has_conflict) keys_with_conflicting_accounts,
          (SELECT count(*) FROM acct_vote WHERE n_golden > 1) accounts_voting_two_golden_ids,
          (SELECT count(*) FROM identity.case_xref WHERE crm_ref_invalid) cases_with_mistyped_crm_ref,
          (SELECT count(*) FROM identity.case_xref WHERE crm_ref_invalid AND golden_id IS NOT NULL)
            cases_recovered_via_account,
          (SELECT count(*) FROM identity.case_xref WHERE golden_id IS NULL) cases_unlinked
    """).df().iloc[0].to_dict()
    m.update(scorer_evaluated=evaluated, scorer_auto_linked=auto_linked, scorer_auto_correct=auto_correct,
             scorer_precision=round(precision, 4) if precision is not None else None,
             scorer_recall=round(recall, 4) if recall is not None else None,
             runtime_s=round(time.perf_counter() - t0, 1))
    metrics = pd.DataFrame({"metric": list(m), "value": [str(v) for v in m.values()]})
    con.register("metrics_df", metrics)
    con.execute("CREATE OR REPLACE TABLE identity.metrics AS SELECT * FROM metrics_df")
    for k, v in m.items():
        log.info("%-38s %s", k, v)
    con.close()


if __name__ == "__main__":
    main()
