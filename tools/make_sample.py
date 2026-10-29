# ruff: noqa: E501
"""Draw a small, self-consistent sample of the Maple Bank release, in the release's own layout and file formats.

Why: the full release is 13 GB uncompressed, which nobody can clone. The sample (about 5,000 customers, a few tens of
MB) lets a stranger run the whole pipeline, model and app: `make demo-data`. The data is synthetic, like the release.

How the sample is drawn (deterministic: same release + same --seed gives the same bytes):
  1. Seeded draw over `customers.crm_customer_id` (sorted ids, `random.Random(seed)`), stratified so that every
     feature of the app has data to show: customers with an open case, a hardship flag, broken promises, kept promises,
     agent notes, call transcripts, duplicate CRM records, the owners of the 500 + 500 public gold labels (so the text
     rules can still be scored), plus a plain uniform draw for the rest.
  2. Closure over the five customer keys, so identity resolution sees what it sees on the full data:
       CRM id -> accounts (snapshot, salary credits, cases) -> card / loan src_customer_ref and deposit CIF
       -> every account of those keys -> CRM records that share a national-id hash or duplicate_of link.
     Bureau / external rows are pulled by CIF (bank_subject_ref), collections rows by CRM id and case id.
  3. Every row that belongs to those customers is copied from every customer-level table (accounts, cases, contacts,
     promises, offers, notes, transcripts and their JSON files, scores, history Parquet). Policy documents, agents,
     shifts, capacity, geo and code lookups, metric definitions, benchmark questions and the gold labels are copied whole
     (they are small). Quirks are kept on purpose (mixed date formats, masked phones, lost CIF zeros, duplicates,
     mistyped CRM ids on cases, null account ids on promises) because the pipeline's cleaning code has to meet them.
  4. Voice recordings are not included (about 2 MB each at 8 kHz); `voice_samples.csv` keeps the rows of sampled
     calls, the WAV files are simply absent, which the code already handles (the voice pack is optional in the release).

Run (needs the release, read only):
    uv run python -m tools.make_sample [--release data/raw/maple_collections_release]
        [--out data/sample/maple_collections_sample] [--customers 4800] [--seed 20260928] [--stats]

Nothing in the release is modified. The output folder is deleted and rewritten on each run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = ROOT / "data" / "raw" / "maple_collections_release"
DEFAULT_OUT = ROOT / "data" / "sample" / "maple_collections_sample"

# Strata of the draw: name -> number of customers asked for (the closure adds duplicates and linked records on top).
QUOTAS = {
    "open_case": 600,
    "hardship_case": 350,
    "broken_promise": 500,
    "kept_promise": 400,
    "duplicate_record": 300,
    "has_transcript": 350,
    "has_note": 350,
    "persona_agent": 150,
}

SMALL_TABLES = [  # copied whole
    "agents", "agent_shifts", "channel_capacity", "ops_events", "geo_reference", "code_lookups", "metric_definitions",
    "benchmark_questions", "hardship_programs", "qa_checklist", "reference_documents",
]
PARQUET_TABLES = {  # table -> key column used for the filter ("A" = account set, "S" = CRM set, "CIF" = bank refs)
    "loan_instalments": ("loan_id", "A"),
    "transactions": ("account_id", "A"),
    "card_statements": ("card_account_id", "A"),
    "account_monthly_snapshot": ("account_id", "A"),
    "bureau_history": ("bank_subject_ref", "CIF"),
    "salary_credit_history": ("deposit_account_id", "A"),
}
BARE_TYPES = {"int", "date", "timestamp", "boolean"}  # plus every decimal(p,s): written without quotes in the release


def log(msg: str) -> None:
    print(f"[make_sample {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def q_in(col: str, tbl: str) -> str:
    return f"{col} IN (SELECT id FROM {tbl})"


class Sampler:
    def __init__(self, release: Path, out: Path, n_customers: int, seed: int):
        self.rel, self.out, self.n, self.seed = release, out, n_customers, seed
        self.d = release / "data"
        self.con = duckdb.connect()
        self.con.execute("SET threads TO 8")
        self.con.execute("SET memory_limit='10GB'")
        self.schema = json.loads((release / "schema" / "schema.json").read_text())

    # ---- helpers -----------------------------------------------------------------------------------------
    def csv(self, table: str) -> str:
        return f"read_csv('{self.d / (table + '.csv')}', all_varchar=true, header=true)"

    def pq(self, table: str) -> str:
        return f"read_parquet('{self.d / table}/*/*.parquet', union_by_name=true, filename=true)"

    def ids(self, name: str, values) -> None:
        self.con.execute(f"CREATE OR REPLACE TABLE {name} (id VARCHAR)")
        vals = sorted({v for v in values if v})
        self.con.executemany(f"INSERT INTO {name} VALUES (?)", [(v,) for v in vals])

    def one_col(self, sql: str) -> list[str]:
        return [r[0] for r in self.con.execute(sql).fetchall()]

    # ---- 1. the draw -------------------------------------------------------------------------------------
    def load_keys(self) -> None:
        c = self.con
        log("loading key columns")
        c.execute(f"CREATE TABLE customers_k AS SELECT crm_customer_id, duplicate_of_crm_id, national_id_hash "
                  f"FROM {self.csv('customers')}")
        c.execute(f"CREATE TABLE cases_k AS SELECT case_id, coll_customer_ref, primary_account_id, account_ids, "
                  f"case_status, hardship_flag, assigned_agent_id FROM {self.csv('collections_cases')}")
        c.execute(f"CREATE TABLE ptp_k AS SELECT ptp_id, case_id, crm_customer_id, account_id, ptp_status "
                  f"FROM {self.csv('promises_to_pay')}")
        c.execute(f"CREATE TABLE notes_k AS SELECT note_id, crm_customer_id, case_id FROM {self.csv('agent_notes')}")
        c.execute(f"CREATE TABLE tr_k AS SELECT transcript_id, crm_customer_id, case_id FROM {self.csv('call_transcripts')}")
        c.execute(f"CREATE TABLE card_k AS SELECT card_account_id AS acct, src_customer_ref AS ref "
                  f"FROM {self.csv('card_accounts')}")
        c.execute(f"CREATE TABLE loan_k AS SELECT loan_id AS acct, src_customer_ref AS ref FROM {self.csv('loan_accounts')}")
        c.execute(f"CREATE TABLE dep_k AS SELECT deposit_account_id AS acct, src_customer_ref AS ref "
                  f"FROM {self.csv('deposit_accounts')}")
        c.execute("CREATE TABLE acct_ref AS SELECT * FROM card_k UNION ALL SELECT * FROM loan_k UNION ALL SELECT * FROM dep_k")
        log("loading snapshot and salary keys")
        c.execute(f"CREATE TABLE snap_k AS SELECT DISTINCT account_id, crm_customer_id FROM {self.pq('account_monthly_snapshot')}")
        c.execute(f"CREATE TABLE sal_k AS SELECT DISTINCT deposit_account_id AS account_id, crm_customer_id "
                  f"FROM {self.pq('salary_credit_history')}")

    def draw(self) -> list[str]:
        rng = random.Random(self.seed)
        pools: dict[str, list[str]] = {
            "open_case": self.one_col("SELECT DISTINCT coll_customer_ref FROM cases_k WHERE case_status='open' "
                                      "AND coll_customer_ref IN (SELECT crm_customer_id FROM customers_k) ORDER BY 1"),
            "hardship_case": self.one_col("SELECT DISTINCT coll_customer_ref FROM cases_k WHERE hardship_flag='true' "
                                          "AND coll_customer_ref IN (SELECT crm_customer_id FROM customers_k) ORDER BY 1"),
            "broken_promise": self.one_col("SELECT DISTINCT crm_customer_id FROM ptp_k WHERE ptp_status='broken' "
                                           "AND crm_customer_id IN (SELECT crm_customer_id FROM customers_k) ORDER BY 1"),
            "kept_promise": self.one_col("SELECT DISTINCT crm_customer_id FROM ptp_k WHERE ptp_status='kept' "
                                         "AND crm_customer_id IN (SELECT crm_customer_id FROM customers_k) ORDER BY 1"),
            "duplicate_record": self.one_col("SELECT crm_customer_id FROM customers_k WHERE duplicate_of_crm_id IS NOT NULL "
                                             "ORDER BY 1"),
            "has_transcript": self.one_col("SELECT DISTINCT crm_customer_id FROM tr_k WHERE crm_customer_id IN "
                                           "(SELECT crm_customer_id FROM customers_k) ORDER BY 1"),
            # the demo personas' own queues (api/personas.py): a handful of open cases each, so no persona opens an empty app
            "persona_agent": self.one_col(
                "SELECT DISTINCT coll_customer_ref FROM cases_k WHERE case_status='open' AND assigned_agent_id IN "
                "('AG-6274', 'AG-5633', 'AG-9065') AND coll_customer_ref IN (SELECT crm_customer_id FROM customers_k) ORDER BY 1"),
            "has_note": self.one_col("SELECT DISTINCT crm_customer_id FROM notes_k WHERE crm_customer_id IN "
                                     "(SELECT crm_customer_id FROM customers_k) ORDER BY 1"),
        }
        chosen: dict[str, str] = {}  # crm id -> stratum that picked it first
        # the owners of the public gold labels: keep the text-rule evaluation meaningful
        lab_notes = {r["note_id"] for r in csv.DictReader(open(self.rel / "labels" / "agent_notes_labels_public_500.csv"))}
        lab_tr = {r["transcript_id"] for r in csv.DictReader(open(self.rel / "labels" / "call_transcripts_labels_public_500.csv"))}
        self.ids("lab_n", lab_notes)
        self.ids("lab_t", lab_tr)
        label_owners = self.one_col(
            "SELECT DISTINCT crm_customer_id FROM notes_k WHERE note_id IN (SELECT id FROM lab_n) "
            "UNION SELECT DISTINCT crm_customer_id FROM tr_k WHERE transcript_id IN (SELECT id FROM lab_t)")
        label_owners = sorted(x for x in label_owners if x in set(pools["has_note"]) | set(pools["has_transcript"]))
        for x in label_owners:
            chosen[x] = "gold_label"
        for name, want in QUOTAS.items():
            pool = pools[name]
            pick = rng.sample(pool, min(want, len(pool)))
            for x in pick:
                chosen.setdefault(x, name)
        everyone = self.one_col("SELECT crm_customer_id FROM customers_k ORDER BY 1")
        need = max(self.n - len(chosen), 0)
        while need > 0:
            for x in rng.sample(everyone, need):
                chosen.setdefault(x, "uniform")
            need = max(self.n - len(chosen), 0)
        counts: dict[str, int] = {}
        for v in chosen.values():
            counts[v] = counts.get(v, 0) + 1
        log(f"drawn {len(chosen)} CRM records: {counts}")
        self.strata = counts
        return sorted(chosen)

    def accounts_of_s(self, include_keys: bool = False) -> None:
        """A = accounts of the sample customers: snapshot, salary credits, cases (primary + list) and promises."""
        extra = "UNION SELECT acct FROM acct_ref WHERE ref IN (SELECT id FROM K) " if include_keys else ""
        self.con.execute(
            "CREATE OR REPLACE TABLE A AS SELECT DISTINCT id FROM ("
            "SELECT account_id id FROM snap_k WHERE crm_customer_id IN (SELECT id FROM S) "
            "UNION SELECT account_id FROM sal_k WHERE crm_customer_id IN (SELECT id FROM S) "
            "UNION SELECT primary_account_id FROM cases_k WHERE coll_customer_ref IN (SELECT id FROM S) "
            "UNION SELECT unnest(regexp_extract_all(account_ids, '[A-Z]+-[0-9]+')) FROM cases_k "
            "WHERE coll_customer_ref IN (SELECT id FROM S) AND account_ids IS NOT NULL "
            "UNION SELECT account_id FROM ptp_k WHERE crm_customer_id IN (SELECT id FROM S) "
            + extra + ") WHERE id IS NOT NULL")

    # ---- 2. closure --------------------------------------------------------------------------------------
    def closure(self, drawn: list[str]) -> None:
        c = self.con
        self.ids("S", drawn)
        for rnd in range(1, 5):
            before = (c.execute("SELECT count(*) FROM S").fetchone()[0])
            # duplicates and shared national id
            c.execute("""INSERT INTO S SELECT DISTINCT x FROM (
                SELECT d.crm_customer_id x FROM customers_k d JOIN customers_k o ON o.crm_customer_id = d.duplicate_of_crm_id
                  WHERE o.crm_customer_id IN (SELECT id FROM S)
                UNION SELECT d.duplicate_of_crm_id FROM customers_k d WHERE d.crm_customer_id IN (SELECT id FROM S)
                  AND d.duplicate_of_crm_id IN (SELECT crm_customer_id FROM customers_k)
                UNION SELECT o.crm_customer_id FROM customers_k o JOIN customers_k s ON s.national_id_hash = o.national_id_hash
                  WHERE s.crm_customer_id IN (SELECT id FROM S) AND o.national_id_hash IS NOT NULL
            ) WHERE x NOT IN (SELECT id FROM S)""")
            self.accounts_of_s()
            # source keys of those accounts, then every account of those keys
            c.execute("CREATE OR REPLACE TABLE K AS SELECT DISTINCT ref id FROM acct_ref WHERE acct IN (SELECT id FROM A) "
                      "AND ref IS NOT NULL")
            c.execute("INSERT INTO A SELECT DISTINCT acct FROM acct_ref WHERE ref IN (SELECT id FROM K) "
                      "AND acct NOT IN (SELECT id FROM A)")
            # valid CRM ids that the snapshot attaches to these accounts also belong to the sample
            c.execute("""INSERT INTO S SELECT DISTINCT s.crm_customer_id FROM snap_k s
                WHERE s.account_id IN (SELECT id FROM A) AND s.crm_customer_id IN (SELECT crm_customer_id FROM customers_k)
                  AND s.crm_customer_id NOT IN (SELECT id FROM S)""")
            after = c.execute("SELECT count(*) FROM S").fetchone()[0]
            log(f"closure round {rnd}: customers {before} -> {after}")
            if after == before:
                break
        self.accounts_of_s(include_keys=True)
        c.execute("CREATE OR REPLACE TABLE K AS SELECT DISTINCT ref id FROM acct_ref WHERE acct IN (SELECT id FROM A) "
                  "AND ref IS NOT NULL")
        # CIF = the deposit refs (the bureau and external key), keeping the leading zeros as text
        c.execute("CREATE OR REPLACE TABLE CIF AS SELECT DISTINCT ref id FROM dep_k WHERE acct IN (SELECT id FROM A) "
                  "AND ref IS NOT NULL")
        # cases of the sample: by customer, or by account (cases whose CRM ref was mistyped still resolve via the account)
        c.execute("CREATE OR REPLACE TABLE C AS SELECT DISTINCT case_id id FROM cases_k WHERE coll_customer_ref IN "
                  "(SELECT id FROM S) OR primary_account_id IN (SELECT id FROM A)")
        c.execute("CREATE OR REPLACE TABLE P AS SELECT DISTINCT ptp_id id FROM ptp_k WHERE crm_customer_id IN (SELECT id FROM S) "
                  "OR case_id IN (SELECT id FROM C)")
        # contacts, notes, transcripts are filtered inside the copy step (their key sets are small)
        self.ids_summary = {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("S", "A", "K", "CIF", "C", "P")}
        log(f"closure done: {self.ids_summary}")

    # ---- 3. writers --------------------------------------------------------------------------------------
    def column_types(self, table: str) -> dict[str, str]:
        t = self.schema.get(table)
        return {col["name"]: col["type"] for col in t["columns"]} if t else {}

    def write_csv(self, table: str, where: str | None) -> int:
        """Copy the rows matching `where` in the release's own CSV dialect: header and strings quoted, numbers, dates,
        timestamps and booleans bare, nulls empty, LF line ends. Tables whose header is not quoted (benchmark_questions)
        are written the way the release wrote them: quoted only when needed."""
        src = self.d / f"{table}.csv"
        header_quoted = src.open().readline().startswith('"')
        types = self.column_types(table)
        # ORDER BY ALL: a parallel scan does not keep file order, and the sample must be byte-for-byte reproducible
        cur = self.con.execute(f"SELECT * FROM {self.csv(table)}" + (f" WHERE {where}" if where else "") + " ORDER BY ALL")
        cols = [d[0] for d in cur.description]
        dest = self.out / "data" / f"{table}.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        quote = [header_quoted and not _is_bare(types.get(col, "string")) for col in cols]
        n = 0
        with dest.open("w", newline="", encoding="utf-8") as f:
            if header_quoted:
                f.write(",".join(f'"{c}"' for c in cols) + "\n")
            else:
                f.write(",".join(cols) + "\n")
            w = csv.writer(f, lineterminator="\n")  # only used for unquoted-header tables
            while True:
                rows = cur.fetchmany(20000)
                if not rows:
                    break
                for row in rows:
                    if header_quoted:
                        f.write(",".join(
                            "" if v is None or v == "" else ('"' + v.replace('"', '""') + '"' if qt else v)
                            for v, qt in zip(row, quote, strict=True)) + "\n")
                    else:
                        w.writerow(["" if v is None else v for v in row])
                    n += 1
        return n

    def write_parquet(self, table: str, key: str, keyset: str) -> int:
        src_dir = self.d / table
        cols_sql = f"SELECT * EXCLUDE (filename) FROM {self.pq(table)}"
        self.con.execute(f"CREATE OR REPLACE TABLE tmp_pq AS SELECT * FROM {self.pq(table)} "
                         f"WHERE {key} IN (SELECT id FROM {keyset})")
        n = 0
        years = self.one_col("SELECT DISTINCT regexp_extract(filename, 'year=([0-9]{4})', 1) FROM tmp_pq ORDER BY 1")
        del cols_sql, src_dir
        for y in years:
            dest = self.out / "data" / table / f"year={y}"
            dest.mkdir(parents=True, exist_ok=True)
            self.con.execute(
                f"COPY (SELECT * FROM (SELECT * EXCLUDE (filename) FROM tmp_pq WHERE filename LIKE '%year={y}/%') ORDER BY ALL) "
                f"TO '{dest / 'part-000.parquet'}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 12)")
            n += self.con.execute(f"SELECT count(*) FROM tmp_pq WHERE filename LIKE '%year={y}/%'").fetchone()[0]
        return n

    # ---- 4. the whole copy -------------------------------------------------------------------------------
    def run(self, stats_only: bool) -> dict:
        t0 = time.time()
        self.load_keys()
        drawn = self.draw()
        self.closure(drawn)
        summary = {"seed": self.seed, "strata": self.strata, "key_sets": self.ids_summary, "rows": {}}
        if stats_only:
            return summary
        if self.out.exists():
            shutil.rmtree(self.out)
        (self.out / "data").mkdir(parents=True)
        c = self.con
        by_crm_or_case = "(crm_customer_id IN (SELECT id FROM S) OR case_id IN (SELECT id FROM C))"
        plan: list[tuple[str, str | None]] = [
            ("customers", q_in("crm_customer_id", "S")),
            ("card_accounts", q_in("card_account_id", "A")),
            ("loan_accounts", q_in("loan_id", "A")),
            ("deposit_accounts", q_in("deposit_account_id", "A")),
            ("collections_cases", q_in("case_id", "C")),
            ("contact_history", by_crm_or_case),
            ("promises_to_pay", q_in("ptp_id", "P")),
            ("agent_notes", by_crm_or_case),
            ("call_transcripts", by_crm_or_case),
            ("external", q_in("bank_subject_ref", "CIF")),
            ("model_scores", "(crm_customer_id IN (SELECT id FROM S) OR case_id IN (SELECT id FROM C) "
                             "OR ptp_id IN (SELECT id FROM P))"),
            ("offers", q_in("case_id", "C")),
            ("case_assignment_history", q_in("case_id", "C")),
        ]
        for table, where in plan:
            summary["rows"][table] = self.write_csv(table, where)
            log(f"{table}: {summary['rows'][table]} rows")
        # voice rows for sampled calls only (WAV files are not shipped in the sample)
        c.execute(f"CREATE OR REPLACE TABLE T AS SELECT transcript_id id FROM read_csv('{self.out / 'data' / 'call_transcripts.csv'}', "
                  f"all_varchar=true, header=true)")
        summary["rows"]["voice_samples"] = self.write_csv("voice_samples", q_in("transcript_id", "T"))
        for table in SMALL_TABLES:
            summary["rows"][table] = self.write_csv(table, None)
        for table, (key, ks) in PARQUET_TABLES.items():
            summary["rows"][table] = self.write_parquet(table, key, ks)
            log(f"{table}: {summary['rows'][table]} rows (parquet)")
        self.copy_files(summary)
        self.write_static(summary)
        summary["seconds"] = round(time.time() - t0, 1)
        return summary

    def copy_files(self, summary: dict) -> None:
        paths = self.one_col(f"SELECT file_path FROM read_csv('{self.out / 'data' / 'call_transcripts.csv'}', all_varchar=true) "
                             "WHERE file_path IS NOT NULL")
        n = 0
        for p in paths:
            src = self.rel / "files" / p
            if src.exists():
                dest = self.out / "files" / p
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                n += 1
        summary["rows"]["transcript_json_files"] = n
        shutil.copytree(self.rel / "files" / "docs", self.out / "files" / "docs")
        summary["rows"]["policy_docs"] = sum(1 for p in (self.out / "files" / "docs").rglob("*") if p.is_file())

    def write_static(self, summary: dict) -> None:
        rel, out = self.rel, self.out
        (out / "labels").mkdir(parents=True, exist_ok=True)
        for name in ("benchmark_dev_answers.csv", "benchmark_answers_template.csv"):
            shutil.copy2(rel / "labels" / name, out / "labels" / name)
        # public gold labels: keep the rows whose note / transcript is in the sample
        notes = {r[0] for r in self.con.execute(f"SELECT note_id FROM read_csv('{out / 'data' / 'agent_notes.csv'}', all_varchar=true)").fetchall()}
        trs = {r[0] for r in self.con.execute(f"SELECT transcript_id FROM read_csv('{out / 'data' / 'call_transcripts.csv'}', all_varchar=true)").fetchall()}
        for name, key, keep in (("agent_notes_labels_public_500.csv", "note_id", notes),
                                ("call_transcripts_labels_public_500.csv", "transcript_id", trs)):
            raw = (rel / "labels" / name).read_text(encoding="utf-8")
            rows = list(csv.reader(raw.splitlines(keepends=True)))
            i = rows[0].index(key)
            kept = [rows[0]] + [r for r in rows[1:] if r[i] in keep]
            # re-write with the release's dialect: reuse the csv module on the whole text (quoted strings)
            with (out / "labels" / name).open("w", newline="", encoding="utf-8") as f:
                csv.writer(f, quoting=csv.QUOTE_NONNUMERIC, lineterminator="\n").writerows(
                    [kept[0]] + [[_num(v) for v in r] for r in kept[1:]])
            summary["rows"][f"labels/{name}"] = len(kept) - 1
        (out / "schema").mkdir(exist_ok=True)
        for name in ("ddl.sql", "load_duckdb.sql"):
            shutil.copy2(rel / "schema" / name, out / "schema" / name)
        sj = json.loads((rel / "schema" / "schema.json").read_text())
        for t, meta in sj.items():
            if t in summary["rows"] and isinstance(meta, dict) and "rows" in meta:
                meta["rows"] = summary["rows"][t]
        (out / "schema" / "schema.json").write_text(json.dumps(sj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.copy2(rel / "DATA_DICTIONARY.xlsx", out / "DATA_DICTIONARY.xlsx")
        readme = (rel / "README.md").read_text(encoding="utf-8")
        note = (f"> **This is the small sample of the release**, drawn by `tools/make_sample.py` (seed {self.seed}): "
                f"{self.ids_summary['S']:,} CRM records and everything that belongs to them. Same layout and formats as the "
                "full release. The Rows column below is the sample's, not the release's. `files/voice` (WAV recordings) is "
                "not included. See `data/sample/README.md`.\n\n")
        head, _, rest = readme.partition("\n\n")
        readme = head + "\n\n" + note + rest
        readme = re.sub(r"Customers: \*\*1,000,000\*\* people\s*\n\(1,020,000 CRM records\)",
                        f"Customers: **{self.ids_summary['S']:,}** CRM records (sample)", readme)

        def fix_row(m: re.Match) -> str:
            t = m.group(1)
            return f"| `{t}` | {m.group(2)} | {summary['rows'].get(t, 0):,} | {m.group(4)} |" if t in summary["rows"] else m.group(0)

        readme = re.sub(r"\| `(\w+)` \| ([^|]+) \| ([\d,]+) \| ([^|]+) \|", fix_row, readme)
        (out / "README.md").write_text(readme, encoding="utf-8")
        # MANIFEST.csv: every file of the sample with size and SHA-256 (same columns as the release)
        files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "MANIFEST.csv")
        with (out / "MANIFEST.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["path", "bytes", "sha256"])
            for p in files:
                w.writerow([p.relative_to(out).as_posix(), p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()])


def _is_bare(t: str) -> bool:
    return t in BARE_TYPES or t.startswith("decimal")


def _num(v: str):
    """Numbers stay bare under QUOTE_NONNUMERIC (the labels file quotes strings only)."""
    if re.fullmatch(r"-?\d+", v or ""):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v or ""):
        return float(v)
    return v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--customers", type=int, default=4800, help="CRM records drawn before the closure adds linked ones")
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--stats", action="store_true", help="draw and close, print the sizes, write nothing")
    a = ap.parse_args(argv)
    if not (a.release / "README.md").exists():
        print(f"release not found at {a.release}", file=sys.stderr)
        return 2
    summary = Sampler(a.release, a.out, a.customers, a.seed).run(a.stats)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
