# ruff: noqa: E501
"""The committed sample (data/sample, tools/make_sample.py) is self-consistent, keeps the data quirks the cleaning code
looks for, and stays inside its size budget. Reads files only: no warehouse needed."""

from __future__ import annotations

import csv
import zlib
from pathlib import Path

import duckdb
import pytest

from common.config import ROOT, Settings

SAMPLE = ROOT / "data" / "sample" / "maple_collections_sample"
pytestmark = pytest.mark.skipif(not (SAMPLE / "README.md").exists(), reason="data/sample not present")

MAX_RAW_MB = 150
MAX_COMPRESSED_MB = 60  # "in git terms": zlib-compressed bytes of every file
# The release itself has these quirks (about 2.8% of cases carry a mistyped CRM id, about 29% of promises have no account).
MAX_UNRESOLVED_SHARE = 0.06


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect()
    for p in (SAMPLE / "data").glob("*.csv"):
        c.execute(f"CREATE VIEW {p.stem} AS SELECT * FROM read_csv('{p}', all_varchar=true, header=true)")
    c.execute("CREATE VIEW all_accounts AS SELECT card_account_id id FROM card_accounts UNION ALL "
              "SELECT loan_id FROM loan_accounts UNION ALL SELECT deposit_account_id FROM deposit_accounts")
    return c


def n(con, sql: str) -> int:
    return con.execute(sql).fetchone()[0]


def test_layout_matches_the_release():
    for name in ("README.md", "MANIFEST.csv", "DATA_DICTIONARY.xlsx"):
        assert (SAMPLE / name).exists(), name
    for d in ("data", "files/docs", "files/transcripts", "labels", "schema"):
        assert (SAMPLE / d).is_dir(), d
    assert (SAMPLE / "schema" / "schema.json").exists()
    assert not (SAMPLE / "files" / "voice").exists(), "voice WAVs are not part of the sample"
    release_header = {"customers": '"crm_customer_id","customer_uuid"', "benchmark_questions": "question_id,question_text"}
    for table, start in release_header.items():
        assert (SAMPLE / "data" / f"{table}.csv").open().readline().startswith(start)


def test_sample_is_about_five_thousand_customers(con):
    assert 4_000 <= n(con, "SELECT count(*) FROM customers") <= 7_000
    assert n(con, "SELECT count(DISTINCT crm_customer_id) FROM customers") == n(con, "SELECT count(*) FROM customers")


def test_every_case_has_a_customer_and_an_account(con):
    total = n(con, "SELECT count(*) FROM collections_cases")
    assert total > 1_000
    assert n(con, "SELECT count(*) FROM collections_cases c LEFT JOIN all_accounts a ON a.id = c.primary_account_id "
                  "WHERE a.id IS NULL") == 0
    missing = n(con, "SELECT count(*) FROM collections_cases c LEFT JOIN customers u ON u.crm_customer_id = c.coll_customer_ref "
                     "WHERE u.crm_customer_id IS NULL")
    # a few cases keep the release's mistyped CRM id on purpose; the identity step recovers them through the account
    assert missing / total <= MAX_UNRESOLVED_SHARE


def test_every_promise_has_its_account_case_and_customer(con):
    total = n(con, "SELECT count(*) FROM promises_to_pay")
    assert total > 1_000
    assert n(con, "SELECT count(*) FROM promises_to_pay p LEFT JOIN all_accounts a ON a.id = p.account_id "
                  "WHERE p.account_id IS NOT NULL AND a.id IS NULL") == 0
    assert n(con, "SELECT count(*) FROM promises_to_pay p LEFT JOIN collections_cases c USING (case_id) "
                  "WHERE c.case_id IS NULL") == 0
    missing = n(con, "SELECT count(*) FROM promises_to_pay p LEFT JOIN customers u USING (crm_customer_id) "
                     "WHERE u.crm_customer_id IS NULL")
    assert missing / total <= MAX_UNRESOLVED_SHARE
    statuses = {r[0] for r in con.execute("SELECT DISTINCT ptp_status FROM promises_to_pay").fetchall()}
    assert {"kept", "broken"} <= statuses


def test_every_transcript_file_exists_and_voice_rows_point_at_sampled_calls(con):
    paths = [r[0] for r in con.execute("SELECT file_path FROM call_transcripts WHERE file_path IS NOT NULL").fetchall()]
    assert len(paths) > 500
    missing = [p for p in paths if not (SAMPLE / "files" / p).exists()]
    assert not missing, missing[:3]
    assert n(con, "SELECT count(*) FROM voice_samples v LEFT JOIN call_transcripts t USING (transcript_id) "
                  "WHERE t.transcript_id IS NULL") == 0


def test_dependent_tables_only_hold_sampled_keys(con):
    assert n(con, "SELECT count(*) FROM offers o LEFT JOIN collections_cases c USING (case_id) WHERE c.case_id IS NULL") == 0
    assert n(con, "SELECT count(*) FROM case_assignment_history o LEFT JOIN collections_cases c USING (case_id) "
                  "WHERE c.case_id IS NULL") == 0
    assert n(con, "SELECT count(*) FROM agent_notes a LEFT JOIN collections_cases c USING (case_id) "
                  "WHERE a.case_id IS NOT NULL AND c.case_id IS NULL") == 0
    assert n(con, "SELECT count(*) FROM agent_notes") > 5_000
    assert n(con, "SELECT count(*) FROM model_scores WHERE model_name = 'ptp_break'") > 100


def test_parquet_history_is_filtered_to_sampled_accounts(con):
    base = SAMPLE / "data"
    for table, key in (("card_statements", "card_account_id"), ("loan_instalments", "loan_id"),
                       ("account_monthly_snapshot", "account_id")):
        files = list((base / table).glob("year=*/part-*.parquet"))
        assert files, table
        orphans = n(con, f"SELECT count(*) FROM (SELECT DISTINCT {key} k FROM read_parquet('{base / table}/*/*.parquet')) t "
                         "LEFT JOIN all_accounts a ON a.id = t.k WHERE a.id IS NULL")
        assert orphans == 0, table


def test_data_quality_quirks_are_kept(con):
    assert n(con, "SELECT count(*) FROM customers WHERE duplicate_of_crm_id IS NOT NULL") > 100  # duplicate CRM records
    assert n(con, "SELECT count(*) FROM card_accounts WHERE cardholder_phone_raw LIKE '%xxx%'") > 0  # masked phones
    assert n(con, "SELECT count(*) FROM deposit_accounts WHERE src_customer_ref LIKE '0%'") > 0  # CIF leading zeros as text
    dob = con.execute("SELECT DISTINCT regexp_replace(dob_raw, '[0-9]', '9', 'g') FROM customers").fetchall()
    assert len(dob) >= 2, "mixed date formats expected in dob_raw"
    assert n(con, "SELECT count(*) FROM collections_cases WHERE case_status = 'open'") > 300
    assert n(con, "SELECT count(*) FROM collections_cases WHERE hardship_flag = 'true'") > 100


def test_manifest_lists_every_file_with_the_right_size():
    rows = list(csv.DictReader((SAMPLE / "MANIFEST.csv").open()))
    listed = {r["path"]: int(r["bytes"]) for r in rows}
    files = {p.relative_to(SAMPLE).as_posix(): p.stat().st_size for p in SAMPLE.rglob("*")
             if p.is_file() and p.name != "MANIFEST.csv"}
    assert set(listed) == set(files)
    assert all(listed[k] == files[k] for k in files)


def test_size_is_within_budget():
    files = [p for p in SAMPLE.rglob("*") if p.is_file()]
    raw = sum(p.stat().st_size for p in files)
    assert raw <= MAX_RAW_MB * 2**20, f"{raw / 2**20:.0f} MB raw"
    packed = sum(len(zlib.compress(p.read_bytes(), 3)) for p in files)
    assert packed <= MAX_COMPRESSED_MB * 2**20, f"{packed / 2**20:.0f} MB compressed"


def test_sample_mode_never_writes_into_the_full_data_build():
    s = Settings(data_source="sample", _env_file=None)
    assert s.is_sample and s.release_dir == SAMPLE
    for p in (s.warehouse_path, s.bronze_dir, s.features_dir, s.reports_dir, s.artefacts_dir,
              s.deliverables_dir, s.quality_report_md):
        assert Path(ROOT / "data" / "sample_build") in p.parents, p
    full = Settings(data_source="full", _env_file=None)
    assert not full.is_sample and full.warehouse_path == ROOT / "data" / "warehouse.duckdb"
    assert full.release_dir == full.raw_dir / "maple_collections_release"
