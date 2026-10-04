"""Binding of the spec suite to the REAL pipeline on synthetic source tables (a mapping layer, not a second pipeline).

`load_sources(tables)` keeps the spec-shaped tables (data-dictionary names, as in factories.ryan_mitchell_tables).
`run_pipeline(as_of)` converts them to release-shaped bronze parquet in a private temporary data directory and then
runs the production steps with the Makefile / jobs-entrypoint environment, pointed at that directory:

    dbt run silver -> identity.run -> dbt build gold (contract tests) -> features.extract_text -> dbt run features
    -> features.parity

Nothing touches data/warehouse.duckdb or data/ops.db. Builds are cached per (tables, as_of) for the whole session.
Reads (golden record, features, NBA) use the temporary warehouse only.

Mapping assumptions (the spec's tables are thinner than the release's):
* card `crm_customer_id` becomes account_monthly_snapshot rows (the release's account-to-CRM history, which
  identity.run votes on). Loans and deposits carry no CRM id in the spec: they take the owner of a card that shares
  their `src_customer_ref`, else the one customer whose first and last name both appear in the account's name.
* card status `delinquent` becomes `active` (the release marks delinquency by DPD, not by status).
* a case with `hardship_mentioned_flag` and no `hardship_flag` becomes hardship_flag true, source `model`.
* `status_ts` of a promise: broken or partly kept at due date + grace days 06:00, kept at its paid date.
"""

from __future__ import annotations

import atexit
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TORONTO = ZoneInfo("America/Toronto")
SENTINEL = "2999-01-01 06:00:00"
TYPED = ROOT / "pipeline" / "models" / "silver" / "typed"
FAR = "9999-12-31 00:00:00"

_BASE: Path | None = None
_CACHE: dict[str, dict[str, Any]] = {}
_OFFLINE_SQL: str | None = None


def _base() -> Path:
    global _BASE
    if _BASE is None:
        _BASE = Path(tempfile.mkdtemp(prefix="spec_pipeline_"))
        atexit.register(shutil.rmtree, _BASE, True)
    return _BASE


# ------------------------------------------------------------------ release shapes
def release_columns(table: str) -> list[str]:
    """Column names of a release table, from the generated typed silver model (committed, no raw data needed)."""
    out = []
    for line in (TYPED / f"{table}.sql").read_text().splitlines():
        m = re.search(r'as "(\w+)",?$', line) or re.match(r'^\s*"(\w+)",?$', line)
        if m:
            out.append(m.group(1))
    return out


def _s(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and v != v):
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, dt.datetime):
        if v.tzinfo:
            v = v.astimezone(TORONTO).replace(tzinfo=None)
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (list, dict, tuple)):
        return json.dumps(v)
    return str(v)


def _local_ts(v: Any) -> str | None:
    """Timestamps of the release are naive local time."""
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = dt.datetime.fromisoformat(v)
        except ValueError:
            return v
    return _s(v)


def _tokens(name: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (name or "").lower()))


def _bronze(tables: dict[str, list[dict]], as_of: dt.datetime) -> dict[str, list[dict]]:
    """Spec-shaped tables -> release-shaped rows (values still python; `_s` makes them text)."""
    day = as_of.astimezone(TORONTO).date()
    snap = day.isoformat()
    t = {k: list(v) for k, v in tables.items()}
    customers = t.get("customers", [])
    out: dict[str, list[dict]] = {}

    # ---- accounts and their owners
    cards, loans, deps = t.get("card_accounts", []), t.get("loan_accounts", []), t.get("deposit_accounts", [])
    ref_owner = {c["src_customer_ref"]: c["crm_customer_id"] for c in cards if c.get("crm_customer_id")}

    def by_name(raw: str | None) -> str | None:
        toks = _tokens(raw)
        hits = [c["crm_customer_id"] for c in customers
                if _tokens(c["first_name"]) <= toks and _tokens(c["last_name"]) <= toks]
        return hits[0] if len(set(hits)) == 1 else None

    owner: dict[str, str | None] = {}
    for c in cards:
        owner[c["card_account_id"]] = c.get("crm_customer_id")
    for a in loans:
        owner[a["loan_account_id"]] = ref_owner.get(a.get("src_customer_ref")) or by_name(a.get("borrower_name_raw"))
    for a in deps:
        owner[a["deposit_account_id"]] = ref_owner.get(a.get("src_customer_ref")) or by_name(a.get("holder_name_raw"))

    snapshot, card_by_crm = [], {}
    out["card_accounts"] = []
    for c in cards:
        card_by_crm.setdefault(c.get("crm_customer_id"), c)
        status = {"delinquent": "active"}.get(c.get("status"), c.get("status") or "active")
        out["card_accounts"].append({
            "card_account_id": c["card_account_id"], "snapshot_date": snap, "src_customer_ref": c.get("src_customer_ref"),
            "cardholder_name_raw": c.get("cardholder_name_raw"), "product_code": c.get("card_brand") or "CARD",
            "open_date": "2020-01-01", "months_on_book": 80, "account_status": status,
            "current_balance": c.get("current_balance"), "past_due_amount": c.get("past_due_amount"),
            "minimum_payment_due": c.get("minimum_payment_due"), "purchase_apr": c.get("purchase_apr"),
            "dpd": c.get("dpd"), "dispute_open_flag": c.get("dispute_open_flag", False), "chargeoff_flag": False,
            "hardship_program_flag": False})
        snapshot.append(("card", c["card_account_id"], status, c.get("current_balance"), c.get("dpd")))
    out["loan_accounts"] = []
    for a in loans:
        bal = sum(a.get(k) or 0 for k in ("principal_balance", "accrued_interest", "fees_outstanding"))
        out["loan_accounts"].append({
            "loan_id": a["loan_account_id"], "product_type": a.get("product_type"), "product_code": a.get("product_type"),
            "src_customer_ref": a.get("src_customer_ref"), "snapshot_date": snap, "open_date": "2020-01-01",
            "principal_balance": a.get("principal_balance"), "total_outstanding": bal,
            "past_due_amount": a.get("past_due_amount"), "scheduled_payment_amount": a.get("scheduled_payment_amount"),
            "remaining_term_months": a.get("remaining_term_months"), "interest_rate": a.get("interest_rate"),
            "accrued_interest": a.get("accrued_interest"), "fees_outstanding": a.get("fees_outstanding"),
            "dpd": a.get("dpd"), "chargeoff_flag": False, "hardship_program_flag": False,
            "borrower_name_raw": a.get("borrower_name_raw")})
        snapshot.append((a.get("product_type") or "loan", a["loan_account_id"], "active", bal, a.get("dpd")))
    out["deposit_accounts"] = []
    for a in deps:
        row = {k: a.get(k) for k in release_columns("deposit_accounts") if k in a}
        row.update({"deposit_account_id": a["deposit_account_id"], "snapshot_date": snap, "account_status": "active",
                    "product_type": "chequing", "chargeoff_flag": False})
        out["deposit_accounts"].append(row)
        snapshot.append(("chequing", a["deposit_account_id"], "active", None, None))
    out["account_monthly_snapshot"] = [
        {"account_id": aid, "crm_customer_id": owner.get(aid), "month_end_date": snap, "product_type": pt,
         "account_status": st, "balance": bal, "dpd": dpd}
        for pt, aid, st, bal, dpd in snapshot if owner.get(aid)]

    # ---- customers (protected columns stay only in the raw customers table, as in the release)
    cols = set(release_columns("customers"))
    ren = {"email_bounced_flag": "email_bounce_flag", "customer_since": "customer_since_date"}
    out["customers"] = []
    for c in customers:
        r = {ren.get(k, k): v for k, v in c.items() if ren.get(k, k) in cols}
        r.setdefault("effective_to_ts", FAR)
        r.setdefault("customer_status", "active")
        r["full_name_raw"] = f"{c['first_name']} {c['last_name']}"
        out["customers"].append(r)

    # ---- cases, promises, contacts
    agents = {a["agent_id"]: a for a in t.get("agents", [])}
    contacts = t.get("contact_history", [])
    case_of = {k["crm_customer_id"]: k for k in t.get("collections_cases", [])}
    out["collections_cases"] = []
    for k in t.get("collections_cases", []):
        crm = k["crm_customer_id"]
        card = card_by_crm.get(crm)
        pa = card["card_account_id"] if card else None
        mentioned = bool(k.get("hardship_mentioned_flag"))
        hflag = bool(k.get("hardship_flag")) or mentioned
        c7 = sum(1 for h in contacts if h["crm_customer_id"] == crm
                 and 0 <= (day - dt.datetime.fromisoformat(h["contact_ts"]).date()).days < 7)
        r = {kk: vv for kk, vv in k.items() if kk in set(release_columns("collections_cases"))}
        r.update({
            "coll_customer_ref": crm, "primary_account_id": pa, "current_bucket": k.get("dpd_bucket"),
            "current_dpd": card.get("dpd") if card else k.get("entry_dpd"),
            "total_overdue": card.get("past_due_amount") if card else None,
            "hardship_flag": hflag, "hardship_source": "agent_coded" if k.get("hardship_flag") else ("model" if mentioned else None),
            "cease_contact_flag": False, "contacts_last_7d": c7,
            "assigned_team": (agents.get(k.get("assigned_agent_id")) or {}).get("team_id"),
            "dispute_status": k.get("dispute_status")})
        out["collections_cases"].append(r)
    out["promises_to_pay"] = []
    seq: dict[str, list] = {}
    for p in sorted(t.get("promises_to_pay", []), key=lambda x: x["ptp_created_ts"]):
        created = dt.datetime.fromisoformat(p["ptp_created_ts"])
        due = dt.date.fromisoformat(p["ptp_due_date"])
        st = p["ptp_status"]
        if st in ("broken", "partially_kept"):
            sts = dt.datetime.combine(due + dt.timedelta(days=p.get("grace_days") or 0), dt.time(6))
        elif st == "kept":
            sts = dt.datetime.combine(dt.date.fromisoformat(p["paid_date"]) if p.get("paid_date") else due, dt.time(12))
        else:
            sts = created
        k = next((c for c in t.get("collections_cases", []) if c["case_id"] == p["case_id"]), {})
        card = card_by_crm.get(p["crm_customer_id"])
        prior = seq.setdefault(p["case_id"], [])
        overdue = card.get("past_due_amount") if card else None
        out["promises_to_pay"].append({
            **{kk: vv for kk, vv in p.items() if kk in set(release_columns("promises_to_pay"))},
            "account_id": card["card_account_id"] if card else None, "product": k.get("primary_product"),
            "ptp_channel": "call", "ptp_type": "single", "status_ts": sts,
            "days_to_due_at_creation": (due - created.date()).days, "ptp_sequence_in_case": len(prior) + 1,
            "prior_broken_ptp_count": sum(1 for x in prior if x in ("broken", "partially_kept")),
            "overdue_at_creation": overdue, "dpd_at_creation": card.get("dpd") if card else None,
            "ptp_to_overdue_ratio": (p["ptp_amount"] / overdue) if overdue else None,
            "reminder_scheduled_flag": False})
        prior.append(st)
    out["contact_history"] = []
    for h in contacts:
        k = case_of.get(h["crm_customer_id"], {})
        ts = _local_ts(h["contact_ts"])
        out["contact_history"].append({
            "contact_id": h["contact_id"], "case_id": k.get("case_id"), "crm_customer_id": h["crm_customer_id"],
            "channel_v2": h.get("channel_v2"), "direction": "outbound", "contact_ts_local": ts, "contact_ts_utc": ts,
            "outcome_code": h.get("outcome"), "rpc_flag": h.get("outcome") in ("ptp_taken", "rpc"),
            "ptp_made_flag": h.get("outcome") == "ptp_taken", "transcript_id": h.get("transcript_id")})

    # ---- transcripts: turns go to files, rows carry file_path (release layout)
    out["call_transcripts"], files = [], {}
    contact_by_id = {h["contact_id"]: h for h in contacts}
    for tr in t.get("call_transcripts", []):
        h = contact_by_id.get(tr.get("contact_id"), {})
        crm = h.get("crm_customer_id")
        end = _local_ts(tr.get("call_end_ts"))
        path = f"transcripts/{end[:4]}/{end[5:7]}/{tr['transcript_id']}.json"
        files[path] = {"transcript_id": tr["transcript_id"], "turns": tr.get("turns", [])}
        out["call_transcripts"].append({
            "transcript_id": tr["transcript_id"], "contact_id": tr.get("contact_id"),
            "case_id": case_of.get(crm, {}).get("case_id"), "crm_customer_id": crm, "call_end_ts": end,
            "call_start_ts": end, "asr_confidence_avg": tr.get("asr_confidence_avg"), "file_path": path})
    out["_files"] = files  # type: ignore[assignment]
    out["agent_notes"] = [
        {**n, "case_id": n.get("case_id") or case_of.get(n.get("crm_customer_id"), {}).get("case_id")}
        for n in t.get("agent_notes", [])]

    # ---- bureau, programs, events, capacity, agents
    out["external"] = [{**e, "pull_date": e.get("pull_date")} for e in t.get("external", [])]
    out["bureau_history"] = [{k: e.get(k) for k in ("bank_subject_ref", "pull_date", "risk_score")}
                             for e in t.get("external", [])]
    out["hardship_programs"] = [
        {**h, "version": "1", "program_name": h["program_id"], "effective_from": "2025-01-01", "effective_to": "9999-12-31"}
        for h in t.get("hardship_programs", [])]
    out["ops_events"] = []
    for e in t.get("ops_events", []):
        e = dict(e)
        e["event_type"] = "app_outage" if e.get("event_type") == "outage" else e.get("event_type")
        e["start_ts"], e["end_ts"] = _local_ts(e.get("start_ts")), _local_ts(e.get("end_ts"))
        if isinstance(e.get("affected_tables"), str):
            e["affected_tables"] = [x.strip() for x in e["affected_tables"].split(",") if x.strip()]
        out["ops_events"].append(e)
    for name in ("agents", "channel_capacity", "agent_shifts", "metric_definitions", "offers"):
        out[name] = list(t.get(name, []))
    return out


def write_bronze(tables: dict[str, list[dict]], as_of: dt.datetime, data_dir: Path) -> None:
    rel = _bronze(tables, as_of)
    files = rel.pop("_files")  # type: ignore[arg-type]
    bronze = data_dir / "bronze"
    bronze.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for f in sorted(TYPED.glob("*.sql")):
        name = f.stem
        cols = release_columns(name)
        rows = [{c: _s(r.get(c)) for c in cols} for r in rel.get(name, [])]
        df = pd.DataFrame(rows, columns=cols, dtype="object")
        for c in cols:
            df[c] = df[c].astype("string")
        con.register("df", df)
        con.execute(f"COPY (SELECT * FROM df) TO '{bronze / (name + '.parquet')}' (FORMAT parquet)")
        con.unregister("df")
    con.close()
    root = data_dir / "raw" / "maple_collections_release" / "files"
    for path, body in files.items():  # type: ignore[attr-defined]
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(json.dumps(body))


# ------------------------------------------------------------------ running the production steps
def _env(key_dir: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    data = key_dir / "data"
    wh = key_dir / "wh" / "warehouse.duckdb"
    env = dict(os.environ)
    env.update({
        "C360_DATA_DIR": str(data), "C360_WAREHOUSE": str(wh), "WAREHOUSE_PATH": str(wh), "DATA_DIR": str(data),
        "RAW_DIR": str(data / "raw"), "BRONZE_DIR": str(data / "bronze"), "FEATURES_DIR": str(data / "features"),
        "OPS_DB_PATH": str(key_dir / "ops.db"), "REPORTS_DIR": str(key_dir / "reports"), "LLM_PROVIDER": "offline"})
    env.update(extra or {})
    return env


def _run(cmd: list[str], env: dict[str, str], cwd: Path, allow_fail: bool = False) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True)
    if r.returncode and not allow_fail:
        raise RuntimeError(f"{' '.join(cmd[-6:])} failed:\n{(r.stdout + r.stderr)[-3000:]}")
    return r


def _dbt(args: list[str], env: dict[str, str], target: Path) -> subprocess.CompletedProcess:
    exe = Path(sys.executable).parent / "dbt"
    return _run([str(exe), *args, "--profiles-dir", ".", "--target-path", str(target),
                 "--log-path", str(target / "logs")], env, ROOT / "pipeline", allow_fail=True)


def _rule_results(run_results: Path) -> list:
    from tests_spec.adapter import QualityRuleResult

    contract = __import__("yaml").safe_load((ROOT / "docs" / "contracts" / "c360_customer.v1.yaml").read_text())
    sev = {r["id"]: r["severity"] for r in contract["quality_rules"]}
    names = {1: ("unique_c360_customer_golden_id", "not_null_c360_customer_golden_id"),
             2: ("dbt_utils_free_range",), 3: ("contract_dpd_implies_past_due",),
             4: ("contract_consent_most_restrictive", "not_null_c360_customer_consent_call"),
             5: ("contract_no_conflicting_national_id",), 6: ("contract_crm_maps_once",),
             8: ("contract_no_protected_columns",), 9: ("contract_freshness",)}
    status: dict[str, tuple[str, int]] = {}
    for r in json.loads(run_results.read_text())["results"]:
        status[r["unique_id"]] = (r["status"], r.get("failures") or 0)
    out = []
    for rid, pats in names.items():
        hits = [v for k, v in status.items() if k.startswith("test.") and any(p in k for p in pats)]
        if not hits:
            continue
        bad = [v for v in hits if v[0] not in ("pass",)]
        out.append(QualityRuleResult(rid, not bad, sev[rid] if not bad or bad[0][0] != "warn" else "warn",
                                     [], f"{sum(v[1] for v in hits)} failing rows" if bad else ""))
    return out


def build(tables: dict[str, list[dict]], as_of: dt.datetime) -> dict[str, Any]:
    key = hashlib.sha1((json.dumps(tables, default=str, sort_keys=True) + as_of.isoformat()).encode()).hexdigest()[:16]
    if key in _CACHE:
        return _CACHE[key]
    kd = _base() / key
    (kd / "wh").mkdir(parents=True)
    write_bronze(tables, as_of, kd / "data")
    (kd / "reports").mkdir()
    live = ROOT / "reports" / "model_eval.json"
    if live.exists():  # scoring reads the model decision; its summary is written to the private copy
        shutil.copy(live, kd / "reports" / "model_eval.json")
    env = _env(kd)
    local = as_of.astimezone(TORONTO).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    vars_ = json.dumps({"as_of_ts": local})
    target = _base() / "dbt_target"
    target.mkdir(exist_ok=True)

    def check(r: subprocess.CompletedProcess, what: str) -> None:
        if r.returncode:
            raise RuntimeError(f"dbt {what} failed:\n{r.stdout[-3000:]}")

    check(_dbt(["run", "--select", "silver"], env, target), "silver")
    _run([sys.executable, "-m", "identity.run"], env, ROOT)
    g = _dbt(["build", "--select", "gold", "--vars", vars_], env, target)
    rr = target / "run_results.json"
    results = _rule_results(rr)
    shutil.copy(rr, kd / "gold_run_results.json")
    if any(x["status"] == "error" and x["unique_id"].startswith("model.") for x in json.loads(rr.read_text())["results"]):
        raise RuntimeError(f"dbt gold failed:\n{g.stdout[-3000:]}")
    _run([sys.executable, "-m", "features.extract_text"], env, ROOT)
    check(_dbt(["run", "--select", "features", "--vars", vars_], env, target), "features")
    comp = target / "compiled" / "collections360" / "models" / "features" / "f_ptp_online.sql"
    shutil.copy(comp, kd / "f_ptp_online.sql")
    ts = as_of.timestamp()
    os.utime(kd / "wh" / "warehouse.duckdb", (ts, ts))  # "built at as_of": Ask reports freshness from the file time
    res = {"dir": kd, "wh": kd / "wh" / "warehouse.duckdb", "as_of": as_of, "local_as_of": local,
           "rules": results, "ptp_sql": kd / "f_ptp_online.sql", "env": env}
    _CACHE[key] = res
    return res


def offline_sql() -> str:
    """f_customer_online compiled once with a sentinel as-of, so any time can be substituted (same code, other date)."""
    global _OFFLINE_SQL
    if _OFFLINE_SQL is None:
        d = _base() / "offline"
        (d / "wh").mkdir(parents=True, exist_ok=True)
        env = _env(d)
        r = _dbt(["compile", "--select", "f_customer_online", "--vars", json.dumps({"as_of_ts": SENTINEL})], env, d / "t")
        p = d / "t" / "compiled" / "collections360" / "models" / "features" / "f_customer_online.sql"
        if not p.exists():
            raise RuntimeError(r.stdout[-2000:])
        _OFFLINE_SQL = p.read_text()
    return _OFFLINE_SQL


def _clear_caches() -> None:
    """Settings and the document index are cached per process; forget them when the warehouse changes."""
    from common.config import get_settings

    get_settings.cache_clear()
    for mod, fn in (("rag.retrieve", "_index"), ("rag.index", "load_sections")):
        f = getattr(sys.modules.get(mod), fn, None)
        if f is not None and hasattr(f, "cache_clear"):
            f.cache_clear()


@contextmanager
def settings_for(res: dict[str, Any], own_ops: bool = True):
    """Point common.config at the temporary warehouse (and a private ops db) for production code that reads settings."""

    keys = ["WAREHOUSE_PATH", "DATA_DIR", "FEATURES_DIR", "OPS_DB_PATH", "REPORTS_DIR", "AS_OF_DATE"]
    old = {k: os.environ.get(k) for k in keys}
    env = res["env"]
    for k in keys[:5]:
        if k != "OPS_DB_PATH" or own_ops:
            os.environ[k] = env[k]
    os.environ["AS_OF_DATE"] = res["as_of"].astimezone(TORONTO).date().isoformat()
    _clear_caches()
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _clear_caches()


def _aware(ts: Any) -> dt.datetime | None:
    if ts is None:
        return None
    if isinstance(ts, dt.date) and not isinstance(ts, dt.datetime):
        ts = dt.datetime.combine(ts, dt.time())
    return ts.replace(tzinfo=TORONTO).astimezone(dt.UTC) if ts.tzinfo is None else ts


# ------------------------------------------------------------------ the mixin
ALIASES = {"risk_score_delta_90d": "bureau_score_delta_90d", "stated_delay_reason": "last_stated_delay_reason"}
NOT_BUILT_FEATURES = {"ptp_intent_strength"}


class PipelineMixin:
    _pl_tables: dict | None = None
    _pl_res: dict | None = None

    def pl_reset(self) -> None:
        self._pl_tables = None
        self._pl_res = None

    def load_sources(self, tables):
        self._pl_tables = json.loads(json.dumps(tables, default=str))
        self._pl_res = None

    def run_pipeline(self, as_of):
        if self._pl_tables is None:
            raise RuntimeError("load_sources first")
        from tests_spec.adapter import QualityReport

        self._pl_res = build(self._pl_tables, as_of)
        rules = self._pl_res["rules"]
        return QualityReport(results=rules, publish_blocked=any(not r.passed and r.severity == "error" for r in rules))

    # -- helpers
    def _res(self) -> dict:
        if self._pl_res is None:
            raise RuntimeError("run_pipeline first")
        return self._pl_res

    def _q(self, sql: str, params: list | None = None, res: dict | None = None) -> list[dict]:
        con = duckdb.connect(str(( res or self._res())["wh"]), read_only=True)
        try:
            rel = con.execute(sql, params or [])
            cols = [d[0] for d in rel.description]
            return [dict(zip(cols, r, strict=True)) for r in rel.fetchall()]
        finally:
            con.close()

    # -- Layer 1
    def find_golden_id(self, source_system, source_key):
        sysmap = {"cards": "cards", "loans": "lending", "deposits": "core_banking", "bureau": "bureau"}
        if source_system == "crm":
            rows = self._q("select golden_id from identity.crm_golden where crm_customer_id = ?", [source_key])
        else:
            rows = self._q("select golden_id from identity.account_xref where account_id = ? and source_system = ? "
                           "and golden_id is not null", [source_key, sysmap.get(source_system, source_system)])
            rows = rows or self._q("select golden_id from identity.source_key_xref where source_ref = ? and source_system = ?",
                                   [source_key, sysmap.get(source_system, source_system)])
        return rows[0]["golden_id"] if rows else None

    def get_golden_record(self, golden_id):
        from tests_spec.adapter import GoldenRecord

        rows = self._q("select * from gold.c360_customer where golden_id = ?", [golden_id])
        if not rows:
            raise KeyError(golden_id)
        r = rows[0]
        contract = __import__("yaml").safe_load((ROOT / "docs" / "contracts" / "c360_customer.v1.yaml").read_text())
        known = ["customers", "card_accounts", "loan_accounts", "deposit_accounts", "collections_cases", "external",
                 "c360_account", "c360_case", "promises_to_pay", "identity_xref", "geo_reference"]
        lineage = {c["name"]: [k for k in known if re.search(rf"\b{k}\b", c.get("source_rule", ""))]
                   for c in contract["schema"]}
        f = lambda v: None if v is None else float(v)  # noqa: E731
        return GoldenRecord(
            golden_id=r["golden_id"], crm_customer_ids=list(r["crm_customer_ids"] or []),
            source_ids=list(r["source_refs"] or []), match_method=r["match_method"],
            match_confidence=f(r["match_confidence"]), display_name=r["display_name"], email_token=r["email_token"],
            phone_token=r["phone_token"], province_code=r["province_code"], fsa=r["fsa"], time_zone=r["time_zone"],
            preferred_language=r["preferred_language"],
            consent={c: r[f"consent_{c}"] for c in ("call", "sms", "email", "push")},
            permitted_call_start_local=r["permitted_call_start_local"],
            permitted_call_end_local=r["permitted_call_end_local"], contact_block=r["contact_block"],
            hardship_flag=r["hardship_flag"], vulnerability_flag=bool(r["vulnerability_flag"]),
            dispute_open_flag=bool(r["dispute_open_flag"]), employer_key=r["employer_key"],
            payroll_delay_days=r["payroll_delay_days"], max_dpd=r["max_dpd"], total_past_due_cad=f(r["total_past_due_cad"]),
            open_case_id=r["open_case_id"], refreshed_at=_aware(r["_refreshed_at"]), lineage=lineage)

    # -- Layer 3
    def _vector(self, gid: str, names, row: dict | None, as_of_local: dt.datetime, res: dict):
        from features.registry import load_registry
        from tests_spec.adapter import FeatureValue, FeatureVector

        reg = {s.name: s for s in load_registry()}
        ptp = self._q("select * from features.f_ptp_online where golden_id = ? order by ptp_due_date limit 1", [gid], res)
        ptp = ptp[0] if ptp else None
        pull = self._q("select max(e.pull_date) d from silver.stg_external e join identity.source_key_xref k "
                       "on k.source_system = 'bureau' and k.source_ref = e.bank_subject_ref where k.golden_id = ?",
                       [gid], res)[0]["d"]
        known = _aware(as_of_local)
        vals: dict[str, FeatureValue] = {}
        for n in names:
            col = ALIASES.get(n, n)
            ver = str(getattr(reg.get(col) or reg.get(n), "version", "1")) if (col in reg or n in reg) else None
            v, present, at = None, False, known
            if n in NOT_BUILT_FEATURES:
                pass
            elif n == "hardship_signal" and row is not None:
                v = row.get("last_call_hardship_signal") or row.get("last_note_hardship_signal")
                present = v is not None
                ver = str(reg["last_call_hardship_signal"].version) if "last_call_hardship_signal" in reg else ver
            elif row is not None and col in row:
                v = row[col]
                present = v is not None
            elif ptp is not None and col in ptp:
                v = ptp[col]
                present = v is not None
            appr = self.__dict__.get("_pl_approved", {}).get(gid)
            if appr and n in ("hardship_signal", "stated_delay_reason") and appr[0].get(n) not in (None, "none"):
                v, present, at, ver = appr[0][n], True, appr[2], appr[1]  # only approved values reach the store
            if hasattr(v, "item"):
                v = v.item()
            if isinstance(v, __import__("decimal").Decimal):
                v = float(v)
            if n == "risk_score_delta_90d" and pull is not None:
                at = _aware(pull)
            vals[n] = FeatureValue(v if present else None, at, present, ver)
        return FeatureVector(gid, vals)

    def get_features_online(self, entity_id, names):
        res = self._res()
        rows = self._q("select * from features.f_customer_online where golden_id = ?", [entity_id], res)
        row = rows[0] if rows else None
        as_of = row["as_of_ts"] if row else dt.datetime.fromisoformat(res["local_as_of"])
        return self._vector(entity_id, names, row, as_of, res)

    def get_features_offline(self, entity_id, as_of, names):
        res = self._res()
        local = as_of.astimezone(TORONTO).replace(tzinfo=None)
        sql = offline_sql().replace(SENTINEL, local.strftime("%Y-%m-%d %H:%M:%S")).replace(SENTINEL[:10], local.date().isoformat())
        con = duckdb.connect(str(res["wh"]), read_only=True)
        try:
            con.execute("SET search_path = 'silver,gold,features,identity'")
            rel = con.execute(f"select * from ({sql}) where golden_id = ?", [entity_id])
            cols = [d[0] for d in rel.description]
            rows = [dict(zip(cols, r, strict=True)) for r in rel.fetchall()]
        finally:
            con.close()
        row = rows[0] if rows else None
        if row and as_of:
            # text only counts when it already existed (the model bounds it by day; the value reports its own time)
            pass
        return self._vector(entity_id, names, row, local, res)

    def run_parity_check(self, sample_size):
        from features.parity import run
        from tests_spec.adapter import ParityReport

        res = self._res()
        out = run(sample_size, warehouse=res["wh"], compiled=res["ptp_sql"], write_report=False)
        return ParityReport(out["sampled"], out["mismatched_rows"], not out["ok"])

    # -- Layer 4 over the temporary warehouse
    def propose_next_best_action_for_case(self, case_id, at):
        from decisioning import context, explain, nba
        from decisioning.allocator import priority
        from tests_spec import adapter_l4_nba as L
        from tests_spec.adapter import Explanation, NbaDecision

        res = self._res()
        with settings_for(res, own_ops=False), self._ops_scope():
            from models.ptp_break import score

            score.main()  # production scoring of the temporary warehouse's open promises -> its own ptp_scores.parquet
            rows = context.load_cases(case_id=case_id)
            if not rows:
                raise KeyError(f"no open case {case_id}")
            r = rows[0]
            programs = context.load_programs()
            offers = context.load_offer_history([r["golden_id"]]).get(r["golden_id"], [])
            plan_date = L._plan_date(at, r["time_zone"] or "America/Toronto")
            d = nba.decide(r, programs, offers, plan_date=plan_date)
            act, g, p = d["action"], d["gate"], d["p_break"]
            alts = nba.alternatives(d, r)
            ex = explain.explain(act, g, d["reasons"], r, d["customer"], p, alts, plan_date, d["program_name"])
            review = nba._review_mode(r, act, g)
        risk = [x.text for x in explain.drivers(r, p)]
        rules = [x.text for x in ex.rules_applied]
        changes = [x.text for x in ex.what_changed]
        text = ". ".join([ex.recommendation] + ([f"Rules applied: {'; '.join(rules)}"] if rules else [])
                         + ([f"Main reasons for the risk: {'; '.join(risk)}"] if risk else [])
                         + ([f"What changed: {'; '.join(changes)}"] if changes else []))
        ev = None
        if act.treatment.value != "no_contact" and p is not None:
            amt = r.get("total_overdue") or 0.0
            ev = priority(p, amt, amt, 0.0, nba.CFG)
        return NbaDecision(
            decision_id=f"DEC-{case_id}-{plan_date.isoformat()}", case_id=case_id, action=L._to_spec_action(act),
            break_probability=p, expected_value=ev,
            explanation=Explanation(rules, risk, changes, text, ex.generated_by), review_mode=review,
            route_to=g.route_to, model_version=r.get("risk_model"),
            alternatives=[L._to_spec_action(L._alt(a)) for a in alts if a["allowed"]])


@contextmanager
def _record_llm(adapter):
    """Record what is sent through llm.client.complete_json (every LLM call goes through it) for llm_request_log()."""
    from llm import client

    real = client.complete_json
    log = adapter.__dict__.setdefault("_pl_llm", [])

    def spy(prompt_id, version, inputs, schema_name, provider=None):
        from tests_spec.adapter import LlmRequest

        log.append(LlmRequest(purpose=prompt_id, prompt_text=json.dumps(inputs, default=str),
                              model_host=provider or client.effective_provider()))
        return real(prompt_id, version, inputs, schema_name, provider)

    client.complete_json = spy
    try:
        yield
    finally:
        client.complete_json = real


def install(cls) -> None:
    """Make `cls` use the pipeline binding (a one-line hook in adapter_impl.py)."""
    for name in ("load_sources", "run_pipeline", "find_golden_id", "get_golden_record", "get_features_online",
                 "get_features_offline", "run_parity_check", "propose_next_best_action_for_case"):
        setattr(cls, name, getattr(PipelineMixin, name))
    for name in ("_vector", "_q", "_res", "pl_reset"):
        setattr(cls, name, getattr(PipelineMixin, name))
    orig_reset, orig_ask = cls.reset, cls.ask
    orig_draft, orig_approve = cls.draft_post_call_summary, cls.approve_post_call_summary

    def draft(self, transcript, recorded_promise=None):
        d = orig_draft(self, transcript, recorded_promise)
        self.__dict__.setdefault("_pl_draft_gid", {})[d.draft_id] = (transcript.golden_id, transcript.case_id)
        return d

    def approve(self, draft, approver, edits=None):
        out = orig_approve(self, draft, approver, edits)
        gid, case = self.__dict__.get("_pl_draft_gid", {}).get(draft.draft_id, (None, None))
        res = getattr(self, "_pl_res", None)
        if res is not None and not gid and case:
            r = self._q("select golden_id from identity.case_xref where case_id = ?", [case])
            gid = r[0]["golden_id"] if r else None
        if gid:
            from decisioning.post_call import raise_hardship_from_approval

            approved = {"signals": {k: out.saved_fields.get(k) for k in ("hardship_signal", "stated_delay_reason")}}
            if res is not None:
                with settings_for(res, own_ops=False), self._ops_scope():
                    raise_hardship_from_approval(gid, approved, approver.actor_id)
            else:
                with self._ops_scope():
                    raise_hardship_from_approval(gid, approved, approver.actor_id)
            self.__dict__.setdefault("_pl_approved", {})[gid] = (approved["signals"], "rules-v1", dt.datetime.now(dt.UTC))
        return out

    def reset(self):
        orig_reset(self)
        self._pl_tables = None
        self._pl_res = None
        self._pl_draft_gid, self._pl_approved, self._pl_llm = {}, {}, []

    def ask(self, question, user, token_overrides=None):
        res = getattr(self, "_pl_res", None)
        if res is None:
            with _record_llm(self):
                return orig_ask(self, question, user, token_overrides)
        with settings_for(res, own_ops=False), self._ops_scope(), _record_llm(self):
            ans = orig_ask(self, question, user, token_overrides)
            total = self._q("select count(*) n from gold.c360_customer")[0]["n"]
            from governance import audit  # api/routers/ask.py records every question, answered or refused

            # the router logs a refusal as its own event type; the suite wants every question under "query", so both
            for et in (("query", "refusal") if ans.refused else ("query",)):
                audit.record(user.user_id, user.role, et, "question", None,
                             {"q": question, "mode": "default"}, {"refused": ans.refused})
        if getattr(ans, "coverage", None) is None and not ans.refused:
            from tests_spec.adapter import Coverage

            ans.coverage = Coverage(min(len(ans.rows), total), total)
        if getattr(ans, "data_products", None):
            # name each product with its schema (gold.c360_case), as the contract and the brief do
            schemas = {r["table_name"]: r["table_schema"] for r in self._q(
                "select table_schema, table_name from information_schema.tables "
                "where table_schema in ('gold', 'silver', 'features')")}
            ans.data_products = [p if "." in p or p not in schemas else f"{schemas[p]}.{p}" for p in ans.data_products]
        return ans

    cls.reset, cls.ask = reset, ask
    cls.llm_request_log = lambda self: list(self.__dict__.get("_pl_llm", []))
    cls.draft_post_call_summary, cls.approve_post_call_summary = draft, approve
