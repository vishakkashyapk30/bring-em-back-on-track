"""Binding of the specification suite (tests_spec/) to the real system, Layers 1 to 3.

Run:  SPEC_ADAPTER=tests_spec.adapter_impl:make_adapter uv run pytest tests_spec -q -rs

Rules followed here:
* Each bound operation calls the real module named in its comment. Glue only converts the suite's dataclasses
  to and from our own shapes. No test input is special-cased and no expected value is hard-coded.
* Where the real system has no equivalent for in-memory inputs (identity on `SourceRecord`s, the contract
  rules on a `C360Snapshot`), the adapter re-states the production rule in Python and says which SQL it mirrors.
* Anything not built (or deliberately not built) raises NotImplementedError with the reason, so the test SKIPS.
* Layer 4 operations (policy gate, ladder, NBA, simulator, eligibility, hardship transitions, approvals, system
  journeys) are left unbound on purpose (inherited NotImplementedError from SpecAdapterBase).
* The live warehouse (data/warehouse.duckdb) is only ever opened read-only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from tests_spec.adapter import (
    ApprovedSummary,
    AskAnswer,
    Citation,
    ContractColumn,
    DataContract,
    DriftReport,
    FeatureDefinition,
    GoldenRecord,
    IdentityCluster,
    IdentityReviewItem,
    MapBubble,
    MapResult,
    OutageVictimReport,
    PolicyAnswer,
    ProposedAction,
    ProposedFix,
    ProxyGateReport,
    ProxyGroupResult,
    QualityReport,
    QualityRuleResult,
    QuestionTokens,
    ResolutionResult,
    ScorecardRow,
    SourceRecord,
    SpecAdapterBase,
    SqlCheck,
    SummaryDraft,
    SummaryPromise,
)
from tests_spec.adapter_l4_hardship import HardshipMixin
from tests_spec.adapter_l4_nba import NbaMixin

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "contracts" / "c360_customer.v1.yaml"

NOT_BUILT_PIPELINE = (
    "running the dbt pipeline on synthetic source tables is not bound: the suite's tables use the spec's column "
    "names and shapes (e.g. card crm_customer_id, inline transcript turns), which the release-shaped bronze "
    "models do not accept; see reports/spec_suite_results.md")


# =====================================================================================================
# Layer 1, identity: Python restatement of the production rules for in-memory SourceRecords.
#   parsing  <- pipeline/macros/normalise.sql + pipeline/models/silver/stg_*.sql
#   passes   <- identity/run.py (CRM clusters, account/key votes, scored matching, review queue)
#   clusters <- identity/cluster.py (union-find with the national-ID cannot-link, G- + smallest CRM ID)
#   scoring  <- identity/matching.py (SCORE_SQL weights, AUTO_LINK 0.90, REVIEW 0.70)
#   survivorship <- pipeline/models/gold/c360_customer.sql
# =====================================================================================================
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_text(x: str | None) -> str | None:
    """normalise.sql norm_text: upper, strip accents, every non-letter becomes a space, trim."""
    s = re.sub(r"[^A-Z ]", " ", _strip_accents(x or "").upper()).strip()
    return s or None


def last_token(x: str | None) -> str | None:
    m = re.search(r"([A-Z]+)$", norm_text(x) or "")
    return m.group(1) if m else None


def first_token(x: str | None) -> str | None:
    m = re.match(r"^([A-Z]+)", norm_text(x) or "")
    return m.group(1) if m else None


def phone_digits(x: str | None) -> str | None:
    """normalise.sql phone_digits: keep digits and the mask letter x; drop a leading country code 1."""
    d = re.sub(r"[^0-9x]", "", x or "")
    if len(d) == 11 and d[0] == "1":
        return d[1:]
    return d or None


def postal(x: str | None) -> str | None:
    return re.sub(r"[^A-Za-z0-9]", "", x or "").upper() or None


def parse_date(x: str | None) -> dt.date | None:
    """normalise.sql parse_date: ISO, YYYYMMDD, YYYY/MM/DD, 'Mon DD YYYY', DD-MM-YYYY, then slash dates
    (middle part > 12 means MM/DD, otherwise DD/MM, the Canadian convention)."""
    if not x:
        return None
    s = str(x).strip()
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        pass
    for fmt in ("%Y%m%d", "%Y/%m/%d", "%b %d %Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    parts = s.split("/")
    if len(parts) == 3:
        fmt = "%m/%d/%Y" if parts[1].isdigit() and int(parts[1]) > 12 else "%d/%m/%Y"
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            return None
    return None


def name_keys(rec: SourceRecord) -> tuple[str | None, str | None]:
    """(last_name_key, first_initial).

    CRM rows use the first_name / last_name columns (stg_customers). Raw source names are parsed with the
    silver rules, chosen by the shape of the name because the suite's records do not follow the release's
    per-system formats: 'LAST/FIRST' (stg_card_accounts), 'LAST, FIRST' (stg_external), 'LAST F M'
    (stg_deposit_accounts: only initials after the surname), otherwise 'First Last' / 'F. LAST'
    (stg_loan_accounts, stg_card_accounts)."""
    if rec.last_name or rec.first_name:
        fi = first_token(rec.first_name)
        return last_token(rec.last_name), fi[0] if fi else None
    raw = rec.raw_name or ""
    if "/" in raw:
        last, first = raw.split("/", 1)
        fi = first_token(first)
        return last_token(last), fi[0] if fi else None
    if "," in raw:
        last, first = raw.split(",", 1)
        fi = first_token(first)
        return last_token(last), fi[0] if fi else None
    toks = (norm_text(raw) or "").split()
    if len(toks) >= 2 and all(len(t) == 1 for t in toks[1:]):
        return toks[0], toks[1]
    fi = first_token(raw)
    return last_token(raw), fi[0] if fi else None


def _key(rec: SourceRecord) -> str:
    return f"{rec.source_system}:{rec.source_key}"


def _id_profile(rec: SourceRecord) -> dict:
    last, fi = name_keys(rec)
    return {"last": last, "fi": fi, "dob": parse_date(rec.dob_raw), "postal": postal(rec.postal_code),
            "phone": phone_digits(rec.phone)}


def _score(p: dict, i: dict) -> float | None:
    """identity/matching.py SCORE_SQL for one probe/index pair (None = not in any block)."""
    fi = 0.20 if (p["fi"] is not None and p["fi"] == i["fi"]) else -0.25
    if p["last"] is not None and p["last"] == i["last"] and p["dob"] is not None and p["dob"] == i["dob"]:
        pp, ip = p["phone"], i["phone"]
        phone_ok = (pp is not None and ip is not None and len(pp) == 10 and len(ip) == 10
                    and (pp == ip or ("x" in pp and pp[:6] == ip[:6] and pp[-2:] == ip[-2:])))
        return (0.55 + fi + (0.15 if p["postal"] is not None and p["postal"] == i["postal"] else 0)
                + (0.15 if phone_ok else 0))
    if p["dob"] is None and p["last"] is not None and p["last"] == i["last"] and p["postal"] is not None \
            and p["postal"] == i["postal"]:
        return 0.45 + fi + 0.15
    return None


_HARDSHIP_ORDER = {"none": 0, "possible": 1, "clear": 2}


def resolve_in_memory(records: Sequence[SourceRecord]) -> ResolutionResult:
    from identity import matching
    from identity.cluster import MAX_CRM_RECORDS_PER_CLUSTER, assign_golden_ids, cluster

    # Pass 1: CRM clusters over current CRM rows (current_crm_filter: effective_to_ts = 9999-12-31)
    crm = [r for r in records if r.source_system == "crm" and r.is_current]
    crm_by_id = {(r.crm_customer_id or r.source_key): r for r in crm}
    nid = {cid: (r.national_id_hash or None) for cid, r in crm_by_id.items()}
    first_with_nid: dict[str, str] = {}
    for cid in sorted(crm_by_id):
        if nid[cid]:
            first_with_nid.setdefault(nid[cid], cid)
    nid_edges = [(cid, first_with_nid[nid[cid]]) for cid in crm_by_id if nid[cid] and first_with_nid[nid[cid]] != cid]
    dup_edges = [(cid, r.duplicate_of_crm_id) for cid, r in crm_by_id.items()
                 if r.duplicate_of_crm_id and r.duplicate_of_crm_id in crm_by_id]
    roots = cluster(list(crm_by_id), nid_edges + dup_edges, nid)
    gid_of_root = assign_golden_ids(roots)
    crm_gid = {cid: gid_of_root[root] for cid, root in roots.items()}
    evidence = {cid: ("duplicate_of" if any(cid in e for e in dup_edges) else
                      "national_id" if any(cid in e for e in nid_edges) else "single_record") for cid in crm_by_id}

    links: dict[str, tuple[str, str, float]] = {_key(r): (crm_gid[cid], "deterministic", 1.0)
                                                  for cid, r in crm_by_id.items()}

    # Passes 2-3: accounts vote through the CRM ID they carry (account_monthly_snapshot.crm_customer_id); a source
    # key follows the majority of its linked accounts; core-banking CIF = bureau bank_subject_ref.
    def source_key(r: SourceRecord) -> tuple[str, str] | None:
        if r.source_system in ("deposits", "core_banking", "crm") and r.src_customer_ref:
            return ("cif", r.src_customer_ref.strip().rjust(10, "0"))
        if r.source_system == "bureau" and (r.bank_subject_ref or r.src_customer_ref):
            return ("cif", (r.bank_subject_ref or r.src_customer_ref).strip().rjust(10, "0"))
        if r.src_customer_ref:
            return (r.source_system, r.src_customer_ref)
        return None

    votes: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in records:
        k = source_key(r)
        if r.source_system == "crm":
            cid = r.crm_customer_id or r.source_key
            if k and cid in crm_gid:
                votes[k][crm_gid[cid]] += 1
        elif r.crm_customer_id in crm_gid and k:
            votes[k][crm_gid[r.crm_customer_id]] += 1
    others = [r for r in records if r.source_system != "crm"]
    for r in others:
        if r.crm_customer_id in crm_gid:
            links[_key(r)] = (crm_gid[r.crm_customer_id], "deterministic", 1.0)
            continue
        k = source_key(r)
        if k and votes.get(k):
            best = sorted(votes[k].items(), key=lambda kv: (-kv[1], kv[0]))[0]
            links[_key(r)] = (best[0], "deterministic", round(best[1] / sum(votes[k].values()), 3))

    # Pass 4: scored matching for the remaining source keys against the CRM index
    index = [(crm_gid[cid], _id_profile(r)) for cid, r in crm_by_id.items()]
    review: list[IdentityReviewItem] = []
    for r in others:
        if _key(r) in links:
            continue
        p = _id_profile(r)
        best_by_gid: dict[str, float] = {}
        for g, i in index:
            s = _score(p, i)
            if s is not None:
                best_by_gid[g] = max(best_by_gid.get(g, s), s)
        if not best_by_gid:
            continue
        g, s = sorted(best_by_gid.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        s = min(s, 0.99)
        n_plausible = sum(1 for v in best_by_gid.values() if v >= matching.REVIEW)
        if s >= matching.AUTO_LINK and n_plausible == 1:
            links[_key(r)] = (g, "probabilistic", round(s, 3))
        elif s >= matching.REVIEW:
            review.append(IdentityReviewItem(
                item_id=f"P-{len(review) + 1:07d}", member_keys=[_key(r)],
                reason="several_plausible_candidates" if n_plausible > 1 else "borderline_probability",
                masked_view={"source_system": r.source_system, "source_ref": r.source_key,
                             "candidate_golden_id": g, "score": round(s, 3)}))

    members: dict[str, list[str]] = defaultdict(list)
    for k, (g, _m, _c) in links.items():
        members[g].append(k)
    clusters, golden = [], {}
    by_key = {_key(r): r for r in records}
    for g in sorted(members):
        keys = sorted(members[g])
        n_crm = sum(1 for k in keys if k.startswith("crm:"))
        methods = [links[k][1] for k in keys]
        conf = min(links[k][2] for k in keys)
        method = "probabilistic" if "probabilistic" in methods else "deterministic"
        status = "pending_review" if n_crm > MAX_CRM_RECORDS_PER_CLUSTER else "linked"
        clusters.append(IdentityCluster(g, keys, method, conf, status))  # type: ignore[arg-type]
        if status == "pending_review":
            review.append(IdentityReviewItem(
                item_id=f"C-{g}", member_keys=keys, reason="cluster_size",
                masked_view={"golden_id": g, "crm_records": n_crm,
                             "evidence": sorted({evidence[k.split(':', 1)[1]] for k in keys if k.startswith('crm:')})}))
        golden[g] = _survivorship(g, [by_key[k] for k in keys], method, conf)
    return ResolutionResult(clusters=clusters, review_queue=review, golden_records=golden)


def _sha(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()


def _survivorship(gid: str, recs: list[SourceRecord], method: str, conf: float) -> GoldenRecord:
    """gold/c360_customer.sql: name and contact from the primary CRM record (not a duplicate, then smallest ID);
    consent = bool_and(coalesce(consent, false)) over CRM rows; do-not-contact and vulnerability = any.
    Hardship: c360 reads it from cases; for in-memory records the strictest level on any linked record."""
    crm = sorted((r for r in recs if r.source_system == "crm"),
                 key=lambda r: (r.duplicate_of_crm_id is not None, r.crm_customer_id or r.source_key))
    p = crm[0]
    consent = {ch: all(bool(r.consent.get(ch)) for r in crm) for ch in ("call", "sms", "email", "push")}
    email = p.email if (p.email_verified and not p.email_bounced) else None
    level = max((r.hardship_flag for r in recs), key=lambda v: _HARDSHIP_ORDER.get(v, 0))
    return GoldenRecord(
        golden_id=gid,
        crm_customer_ids=sorted(r.crm_customer_id or r.source_key for r in crm),
        source_ids=sorted(_key(r) for r in recs),
        match_method=method,  # type: ignore[arg-type]
        match_confidence=conf,
        display_name=f"{p.preferred_name or p.first_name} {p.last_name}",
        date_of_birth=parse_date(p.dob_raw),
        email_token=_sha(email.lower()) if email else None,
        phone_token=_sha(p.phone) if p.phone else None,
        consent=consent,
        contact_block="cease" if any(r.cease_communication_flag for r in crm) else "none",
        hardship_flag=level,  # type: ignore[arg-type]
        vulnerability_flag=any(r.vulnerability_flag for r in recs),
        lineage={"display_name": ["customers"], "consent": ["customers"], "source_ids": ["identity_xref"]},
    )


# =====================================================================================================
# Layer 1, contract + quality rules
#   contract <- docs/contracts/c360_customer.v1.yaml
#   rules    <- the YAML's quality_rules, with the same logic as pipeline/tests/*.sql and gold/schema.yml
# =====================================================================================================
def load_contract() -> dict:
    return yaml.safe_load(CONTRACT_PATH.read_text())


def _rule_severity(contract: dict, rule_id: int) -> str:
    return next(r["severity"] for r in contract["quality_rules"] if r["id"] == rule_id)


def quality_rules(snapshot: Mapping[str, list[dict]], now: dt.datetime) -> QualityReport:
    from common.config import get_settings
    from common.protected import find_forbidden
    from identity.matching import AUTO_LINK

    contract = load_contract()
    rows = snapshot.get("c360_customer", [])
    crm = snapshot.get("crm_current", [])
    accts = snapshot.get("c360_account", [])
    out: list[QualityRuleResult] = []

    def add(rule_id: int, failing: list, msg: str, severity: str | None = None) -> None:
        out.append(QualityRuleResult(rule_id, not failing, severity or _rule_severity(contract, rule_id),  # type: ignore[arg-type]
                                     [str(f) for f in failing], msg))

    # 1: unique + not_null on golden_id (gold/schema.yml)
    ids = [r.get("golden_id") for r in rows]
    add(1, [i for i in ids if i is None] + [i for i, n in Counter(ids).items() if i is not None and n > 1],
        "golden_id is unique and not null")
    # 2: dbt_utils_free_range [0, 1], plus the auto cut-off (identity/matching.AUTO_LINK) unless deterministic/reviewed
    add(2, [r.get("golden_id") for r in rows
            if r.get("match_confidence") is None or not 0 <= r["match_confidence"] <= 1
            or r.get("match_method") not in ("deterministic", "probabilistic", "reviewed")
            or (r.get("match_method") == "probabilistic" and r["match_confidence"] < AUTO_LINK)],
        f"match_confidence in [0,1] and >= {AUTO_LINK} unless deterministic or reviewed")
    # 3: max_dpd > 0 implies past due > 0 (error per the contract); max_dpd = 0 with > CAD 1 past due (warn)
    add(3, [r.get("golden_id") for r in rows if (r.get("max_dpd") or 0) > 0 and (r.get("total_past_due_cad") or 0) <= 0],
        "max_dpd > 0 implies total_past_due_cad > 0")
    add(3, [r.get("golden_id") for r in rows if (r.get("max_dpd") or 0) == 0 and (r.get("total_past_due_cad") or 0) > 1.0],
        "max_dpd = 0 with more than CAD 1 past due", severity="warn")
    # 4: consent not null, and never more permissive than a linked current CRM record (contract_consent_most_restrictive)
    chans = ("consent_call", "consent_sms", "consent_email", "consent_push")
    by_gid = {r.get("golden_id"): r for r in rows}
    fail4 = [r.get("golden_id") for r in rows if any(r.get(c) is None for c in chans)]
    fail4 += [s.get("golden_id") for s in crm if s.get("golden_id") in by_gid
              and any(by_gid[s["golden_id"]].get(c) and not (s.get(c) or False) for c in chans)]
    add(4, fail4, "consent never null and never more permissive than a linked current CRM record")
    # 5: contract_no_conflicting_national_id
    hashes: dict[Any, set] = defaultdict(set)
    for s in crm:
        if s.get("national_id_hash") is not None and s.get("golden_id") is not None:
            hashes[s["golden_id"]].add(s["national_id_hash"])
    add(5, [g for g, h in hashes.items() if len(h) > 1], "no golden_id links two different national_id_hash values")
    # 6: contract_crm_maps_once (+ every golden_id is in the C360) and one primary party per account (account_party)
    gids_of: dict[Any, set] = defaultdict(set)
    for s in crm:
        gids_of[s.get("crm_customer_id")].add(s.get("golden_id"))
    fail6 = [c for c, g in gids_of.items() if len(g - {None}) != 1]
    fail6 += [g for g in {s.get("golden_id") for s in crm} - {None} if g not in by_gid]
    primaries = Counter(a.get("account_id") for a in accts if a.get("party_role") == "primary")
    fail6 += [a for a in {a.get("account_id") for a in accts} if primaries.get(a, 0) != 1]
    add(6, fail6, "every current CRM record maps to one golden_id; every account has one primary party")
    # 7: every drop of hardship_flag to none has a reviewer and a reason
    add(7, [e.get("golden_id") for e in snapshot.get("hardship_flag_events", [])
            if e.get("to_level") == "none" and e.get("from_level") not in (None, "none")
            and not (e.get("reviewer") and e.get("reason"))],
        "every lowering of hardship_flag to none has a reviewer and a reason")
    # 8: contract_no_protected_columns (common/protected.py: the 12 + age, age_band, voice acoustics)
    cols = {c for r in rows for c in r}
    add(8, sorted(find_forbidden(cols)), "no protected-attribute column")
    # 9: contract_freshness (settings.freshness_sla_hours = 26)
    sla = dt.timedelta(hours=get_settings().freshness_sla_hours)
    add(9, [r.get("golden_id") for r in rows if r.get("_refreshed_at") is None or r["_refreshed_at"] < now - sla],
        "_refreshed_at within the freshness SLA")
    # 10: employer_key match rate on the sample (warn), threshold from the contract text
    sample = snapshot.get("employer_match_sample", [])
    thr = float(re.search(r">=\s*(\d+)%", next(r["rule"] for r in contract["quality_rules"] if r["id"] == 10)).group(1)) / 100
    rate = (sum(s.get("employer_key_true") == s.get("employer_key_matched") for s in sample) / len(sample)) if sample else None
    add(10, [] if rate is None or rate >= thr else [f"match_rate={rate:.2f}"], f"employer_key match rate >= {thr:.0%}")
    blocked = any(not r.passed and r.severity == "error" for r in out)
    return QualityReport(results=out, publish_blocked=blocked)


# =====================================================================================================
# Adapter
# =====================================================================================================
class Layer123Adapter(NbaMixin, HardshipMixin, SpecAdapterBase):
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._sections = None          # injected reference-document corpus (load_reference_documents)
        self.reset_hardship()          # private ops.db of the hardship mixin

    # ---------------- Layer 1: identity ----------------
    def resolve_identities(self, records, previous=None):
        # identity/cluster.py + identity/matching.py rules (see resolve_in_memory). `previous` is not needed:
        # golden IDs are derived from the smallest CRM ID, so reruns reproduce them (design_changes.md #26).
        return resolve_in_memory(records)

    def system_client(self):
        # An in-process system on the seeded tables, built from the production modules (adapter_system.py).
        from tests_spec.adapter_system import SpecSystemClient

        return SpecSystemClient(self)

    def load_sources(self, tables):
        raise NotImplementedError(NOT_BUILT_PIPELINE)

    def run_pipeline(self, as_of):
        raise NotImplementedError(NOT_BUILT_PIPELINE)

    def find_golden_id(self, source_system, source_key):
        raise NotImplementedError(NOT_BUILT_PIPELINE)

    def get_golden_record(self, golden_id):
        raise NotImplementedError(NOT_BUILT_PIPELINE)

    # ---------------- Layer 1: contract and quality ----------------
    def get_data_contract(self, product):
        # docs/contracts/c360_customer.v1.yaml
        c = load_contract()
        if product != c["product"]:
            raise KeyError(f"no contract for {product}")
        sla = float(re.search(r"(\d+)\s*hours", c["freshness_sla"]).group(1))
        return DataContract(
            product=c["product"], version=str(c["version"]), owner=c["owner"], steward=c["steward"],
            policy_approver=c["policy_approver"], grain=c["grain"], consumers=list(c["consumers"]),
            refresh=c["refresh"], freshness_sla_hours=sla, retention=c["retention"],
            columns=[ContractColumn(s["name"], s["type"], s["pii_class"], s.get("source_rule", "")) for s in c["schema"]],
            quality_rules=[r["rule"] for r in c["quality_rules"]], allowed_uses=list(c["allowed_uses"]),
            prohibited_uses=list(c["not_allowed"]))

    def run_quality_rules(self, snapshot, now):
        return quality_rules(snapshot.tables, now)

    # ---------------- Layer 1: data health (S3) and outage victims (H5), adapter-level ----------------
    def detect_schema_drift(self, table, baseline_batch, new_batch):
        # Not built in production (llm/prompts/drift_fix has no offline handler). Implemented here as plain
        # load telemetry: column set, row count and null-rate changes; the fix is only a proposal.
        old_cols = {c for r in baseline_batch for c in r}
        new_cols = {c for r in new_batch for c in r}

        def null_rate(batch, col):
            return sum(r.get(col) is None for r in batch) / len(batch) if batch else 0.0

        common = sorted(old_cols & new_cols)
        changes = {c: round(null_rate(new_batch, c) - null_rate(baseline_batch, c), 4) for c in common}
        added, removed = sorted(new_cols - old_cols), sorted(old_cols - new_cols)
        fix = None
        if added or removed:
            fix = ProposedFix(f"FIX-{table}-{uuid.uuid4().hex[:6]}",
                              f"{table}: map {', '.join(removed) or '-'} -> {', '.join(added) or '-'} in the silver model",
                              status="pending_engineer_approval", applied=False)
        rc = (len(new_batch) - len(baseline_batch)) / len(baseline_batch) if baseline_batch else None
        return DriftReport(table, added, removed, rc, {c: v for c, v in changes.items() if v}, [], fix)

    def find_outage_victims(self, event, repayments):
        # NI H5 / V1 §3: due during the outage and paid the next day; a candidate list with proposals for a person.
        start, end = event.start_ts.date(), event.end_ts.date()
        cand = [r for r in repayments
                if start <= r.due_date <= end and r.paid_date is not None
                and r.paid_date == r.due_date + dt.timedelta(days=1)]
        proposals = []
        for r in cand:
            if r.fees_charged > r.fees_reversed:
                proposals.append(ProposedAction(f"PR-FEE-{r.account_id}", "fee_reversal", r.account_id,
                                                "pending_approval", "team_lead"))
            proposals.append(ProposedAction(f"PR-HOLD-{r.golden_id}", "pressure_hold", r.golden_id,
                                            "pending_approval", "team_lead"))
        ids = [r.account_id for r in cand]
        return OutageVictimReport(ids, len(ids), event.affected_customers_est, True, proposals)

    # ---------------- Layer 2: Ask ----------------
    def validate_sql(self, sql, user):
        # The two checks nlq/executor.execute() runs before any SQL reaches the read-only warehouse:
        # nlq/guard.validate (one SELECT, allowlisted tables, no protected columns, LIMIT) and
        # nlq/executor.check_columns (no direct identifiers, no SELECT *).
        # Agents also get the row filter (nlq/guard.apply_row_filters): their tables are wrapped in a sub-select.
        import sqlglot

        from nlq.executor import ALLOWED, check_columns
        from nlq.guard import DEFAULT_LIMIT, GuardError, agent_row_filters, apply_row_filters, validate

        try:
            safe = validate(sql, ALLOWED, max_limit=DEFAULT_LIMIT)
            check_columns(safe)
        except (GuardError, PermissionError) as e:
            return SqlCheck(False, [str(e)])
        lim = sqlglot.parse_one(safe, read="duckdb").args.get("limit")
        applied = False
        if user.role == "agent":
            safe, applied = apply_row_filters(safe, agent_row_filters(user.user_id))
        return SqlCheck(True, [], safe, int(lim.expression.name) if lim is not None else None, applied)

    def suppress_small_groups(self, rows, count_field):
        # Threshold: common/config.py suppression_min_group (10). Groups below it are hidden entirely.
        from common.config import get_settings

        k = get_settings().suppression_min_group
        return [r for r in rows if (r.get(count_field) or 0) >= k]

    @staticmethod
    def _tokens_from_chips(chips: dict) -> QuestionTokens:
        return QuestionTokens(metric=chips.get("metric"), dimensions=list(chips.get("dimensions") or []),
                              filters={f: True for f in chips.get("filters") or []}, time_period=chips.get("time"))

    def parse_question(self, question, user):
        # The offline parser is the semantic compiler (semantic/compiler.compile_question); nlq/parser.py is a stub.
        from common.config import get_settings
        from semantic.compiler import compile_question

        c = compile_question(question, get_settings().as_of_date)
        if c is None:
            return QuestionTokens()
        return self._tokens_from_chips({"metric": c.metric_id, "dimensions": c.dimensions, "filters": c.filters,
                                        "time": c.time_label})

    def ask(self, question, user, token_overrides=None):
        # nlq/pipeline.ask on the real warehouse (read-only). Follow-ups are the API's (api/routers/ask.py).
        chips = None
        if token_overrides is not None:
            t = token_overrides
            chips = {"metric": t.metric, "dimensions": list(t.dimensions or []), "filters": list(t.filters or {}),
                     "time": t.time_period}
        import sqlglot
        from sqlglot import exp

        from api.routers.ask import FOLLOWUPS
        from api.services.ask_access import scope_for
        from common.ask_scope import use_scope
        from nlq.pipeline import ask as run

        with use_scope(scope_for(str(user.role), user.user_id, user.team_id)):
            a = run(question, None, chips)
        if a.refused:
            return AskAnswer(refused=True, refusal_reason=a.refusal_reason)
        rows = [dict(zip(a.columns, r, strict=False)) for r in a.rows]
        sql = a.sql_or_sources if a.kind == "metric" else None
        products: list[str] = []
        if sql:
            ctes = {c.alias_or_name for c in sqlglot.parse_one(sql, read="duckdb").find_all(exp.CTE)}
            products = sorted({t.name for t in sqlglot.parse_one(sql, read="duckdb").find_all(exp.Table)} - ctes)
        else:
            products = [s.strip() for s in a.sql_or_sources.split(";") if s.strip()]
        incidents = [m.group(1) for c in a.caveats if (m := re.match(r"Incident in this period: ([^:]+):", c))]
        insight = (f"{len(a.rows)} row(s) returned from the certified {a.chips.get('metric')} definition."
                   if a.kind == "metric" and a.rows else (a.answer if a.kind != "metric" else None))
        return AskAnswer(
            refused=False, tokens=self._tokens_from_chips(a.chips) if a.kind == "metric" else None, sql=sql,
            rows=rows, data_products=products,
            freshness=dt.datetime.fromisoformat(a.freshness) if a.freshness else None, caveats=list(a.caveats), incidents=incidents,
            coverage=None, insight_text=insight, follow_ups=list(FOLLOWUPS.get(a.kind, [])))

    def cure_rate_30d(self, cases):
        # The certified cure_rate metric (semantic/registry.py) evaluated over the given cases with DuckDB.
        return _certified_cure_rate(cases)

    # ---------------- Layer 2: policy documents (rag/) ----------------
    def load_reference_documents(self, docs):
        # rag/index.sections_from_documents: same current-version filter and section split as load_sections().
        from rag.index import sections_from_documents

        self._sections = sections_from_documents([{
            "doc_id": d.doc_id, "section": d.section, "text": d.text, "doc_type": d.doc_type,
            "version": d.version, "language": d.language, "superseded_by": d.superseded_by,
            "applies_to_products": d.applies_to_products, "applies_to_provinces": d.applies_to_provinces,
        } for d in docs])

    def answer_policy_question(self, query, user):
        # rag/answer.answer_question with the product / province / language of the query; the corpus is the
        # loaded documents when the test loaded some (rag.retrieve.use_sections), else the release corpus.
        from contextlib import nullcontext

        from rag.answer import answer_question
        from rag.retrieve import use_sections

        ctx = use_sections(self._sections) if self._sections is not None else nullcontext()
        with ctx:
            a = answer_question(query.question, product=query.product, province=query.province,
                                language=query.language)
        if a["refused"]:
            return PolicyAnswer(False, None, [], a["refusal_reason"])
        return PolicyAnswer(True, a["answer"], [Citation(c["doc_id"], c["section"]) for c in a["citations"]])

    # ---------------- Layer 2: analyst views ----------------
    def strategy_scorecard(self, cases):
        # NI S4: strategy x (entry DPD band, product); causal only when every case in the cell was randomised.
        def band(d):
            d = d or 0
            return "1-30" if d <= 30 else "31-60" if d <= 60 else "61-90" if d <= 90 else "90+"

        cells: dict[tuple, list] = defaultdict(list)
        for c in cases:
            rnd = c.get("assignment_method") in ("random", "randomised_pilot")
            cells[(c.get("strategy_code"), band(c.get("entry_dpd")), c.get("primary_product"), rnd)].append(c)
        out = []
        for (strategy, b, product, rnd), cs in sorted(cells.items(), key=lambda kv: tuple(map(str, kv[0]))):
            rate = _certified_cure_rate(cs)
            cures = sum(1 for c in cs if c.get("cure_flag") and (c.get("days_to_cure") or 10**6) <= 30)
            cost = sum(c.get("contact_cost_cad") or 0 for c in cs)
            out.append(ScorecardRow(
                strategy_code=strategy, segment={"entry_dpd_band": b, "product": product}, cure_rate=rate,
                cost_per_cure=(cost / cures) if cures else None,
                complaints_per_1000=1000 * sum(bool(c.get("complaint_raised_flag")) for c in cs) / len(cs),
                causal=rnd, label="randomised: causal comparison within the cell" if rnd else "observed, not causal"))
        return out

    def employer_radar(self, observations, ops_events=()):
        raise NotImplementedError("S1 employer radar deliberately not built: profiling found no employer or regional "
                                  "cluster (docs/profiling_decisions.md §1, design_changes.md #20)")

    def weather_map(self, observations):
        # NI S2: one bubble per FSA, computed by SQL (shown), areas under the suppression threshold hidden.
        import duckdb
        import pandas as pd

        from common.config import get_settings

        k = get_settings().suppression_min_group
        df = pd.DataFrame([{"golden_id": o.golden_id, "fsa": o.fsa, "ptp_broken": o.ptp_broken,
                            "rolled_forward": o.rolled_forward} for o in observations])
        sql = ("SELECT fsa AS area, count(DISTINCT golden_id) AS n_customers, avg(ptp_broken::INT) AS broken_promise_rate, "
               "avg(rolled_forward::INT) AS roll_rate FROM area_obs GROUP BY fsa ORDER BY fsa")
        con = duckdb.connect()
        con.register("area_obs", df)
        rows = con.sql(sql).fetchall()
        con.close()
        kept = [MapBubble(a, n, b, r) for a, n, b, r in rows if n >= k]
        return MapResult(kept, sql, suppressed_areas=len(rows) - len(kept))

    # ---------------- Layer 3: features ----------------
    def get_feature_registry(self):
        # features/registry.yaml via features/registry.load_registry (built_by: sql | ai | voice)
        from features.registry import load_registry

        out = []
        for s in load_registry():
            acc = None
            if s.label_accuracy:
                m = re.search(r"\d*\.\d+", str(s.label_accuracy.get("value", "")))
                acc = float(m.group(0)) if m else None
            out.append(FeatureDefinition(s.name, s.entity, s.type, ", ".join(s.source), s.refresh, s.owner,
                                         str(s.version), s.built_by,
                                         str(s.prompt_version) if s.prompt_version else s.prompt, acc))
        return out

    def get_features_online(self, entity_id, names):
        raise NotImplementedError(NOT_BUILT_PIPELINE)

    def get_features_offline(self, entity_id, as_of, names):
        raise NotImplementedError(NOT_BUILT_PIPELINE)

    def run_parity_check(self, sample_size):
        raise NotImplementedError(NOT_BUILT_PIPELINE)

    def proxy_feature_gate(self, features, protected, groups):
        # governance/fairness/proxy_test.group_proxy_auc (the only package allowed to read protected attributes).
        from governance.fairness.proxy_test import group_proxy_auc

        res = group_proxy_auc(features, protected, groups)
        return ProxyGateReport({g: ProxyGroupResult(g, r["max_auc"], r["worst_attribute"], r["decision"])
                                for g, r in res.items()})

    # ---------------- Post-call summary ----------------
    def draft_post_call_summary(self, transcript, recorded_promise=None):
        # decisioning/post_call.draft_from_turns (the same function summarise() uses for warehouse transcripts)
        from decisioning.post_call import draft_from_turns

        turns = [{"turn_index": t.turn_index, "speaker": t.speaker, "text": t.text} for t in transcript.turns]
        record = ({"amount": recorded_promise.amount, "date": recorded_promise.due_date.isoformat()}
                  if recorded_promise else None)
        call_date = transcript.call_end_ts.date() if transcript.call_end_ts else None
        d = draft_from_turns(turns, call_date, record, transcript.asr_confidence_avg)
        f, payload = d["fields"], d["payload"]
        # The recorded promise is the default; when the call said something different, show what was said and
        # flag the mismatch (highlighted, never silently replaced).
        ptp = (d["checks"]["promise_in_transcript"] if not d["checks"]["promise_matches_record"] else f.get("ptp")) or {}
        due = ptp.get("date")
        promise = SummaryPromise(amount=ptp.get("amount"),
                                 due_date=dt.date.fromisoformat(due) if isinstance(due, str) else due,
                                 intent_strength=(payload.get("promise") or {}).get("ptp_intent_strength"))
        signals = {k: v for k, v in payload["signals"].items() if k != "turns"}
        citations = {k: v for k, v in d["evidence"].items() if v}
        return SummaryDraft(
            draft_id=f"D-{transcript.contact_id}", contact_id=transcript.contact_id, summary=d["summary"],
            promise=promise, signals=signals, next_steps=[s["text"] for s in payload["next_steps"]],
            citations=citations, mismatches=[] if d["checks"]["promise_matches_record"] else ["promise"],
            schema_valid=d["schema_valid"], status="draft")

    def approve_post_call_summary(self, draft, approver, edits=None):
        # decisioning/post_call.approve: writes call_summaries and the audit row (in this adapter's private ops.db).
        from decisioning.post_call import approve

        if approver.kind != "person":
            raise PermissionError("Only a person can approve a summary")
        original = {
            "summary": draft.summary,
            "promise": {"amount": draft.promise.amount,
                        "date": draft.promise.due_date.isoformat() if draft.promise.due_date else None,
                        "ptp_intent_strength": draft.promise.intent_strength},
            "signals": dict(draft.signals), "next_steps": list(draft.next_steps)}
        approved = {**original, "signals": dict(original["signals"])}
        for k, v in (edits or {}).items():
            if k in approved["signals"]:
                approved["signals"][k] = v
            else:
                approved[k] = v
        with self._ops_scope():
            res = approve(draft.contact_id, approved, approver.actor_id, approver.role or "agent", original=original,
                          draft_id=draft.draft_id)
        return ApprovedSummary(draft.draft_id, res["approved_by"], res["saved_fields"], res["edited_fields"],
                               str(res["audit_id"]))

def _certified_cure_rate(cases: Sequence[Mapping[str, Any]]) -> float | None:
    """semantic/registry.py METRICS['cure_rate'] (30-day cure) over an in-memory collections_cases table."""
    import duckdb
    import pandas as pd

    from semantic.registry import METRICS

    m = next(x for x in METRICS if x.id == "cure_rate")
    cols = ("case_id", "cure_flag", "days_to_cure", "insolvency_hold_flag", "deceased_hold_flag")
    df = pd.DataFrame([{c: x.get(c) for c in cols} for x in cases], columns=list(cols)).astype(
        {"cure_flag": "boolean", "insolvency_hold_flag": "boolean", "deceased_hold_flag": "boolean",
         "days_to_cure": "Float64"})
    sql = f"SELECT {m.select.replace('{cure_days}', '30')} FROM {m.base}"
    if m.where:
        sql += " WHERE " + " AND ".join(m.where)
    con = duckdb.connect()
    con.register("collections_cases", df)
    row = con.sql(sql).fetchone()
    con.close()
    return None if row is None or row[0] is None or row[1] == 0 else row[0] / 100.0


__import__("tests_spec.adapter_pipeline", fromlist=["install"]).install(Layer123Adapter)  # real pipeline on synthetic tables


def make_adapter() -> Layer123Adapter:
    from tests_spec.adapter_radar import bind

    return bind(Layer123Adapter())  # S1 radar, S3 drift, H5 outage shield (production modules)
