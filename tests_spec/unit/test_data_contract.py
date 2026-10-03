"""Draft data contract `gold.c360_customer` v1.0 and its quality rules (V1 Part 3; Brief Part 1 item 3)."""

from __future__ import annotations

import datetime as dt

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C

pytestmark = pytest.mark.contract

NOW = F.AS_OF


def _report(adapter, rows=None, **tables):
    return adapter.run_quality_rules(F.valid_snapshot(rows, **tables), NOW)


# ---------------------------------------------------------------------------
# The contract document itself
# ---------------------------------------------------------------------------
def test_contract_declares_owner_schema_rules_uses_and_refresh(adapter):
    """Brief Part 1 "Draft data contract: owner, schema, 3+ quality rules, allowed uses, refresh
    frequency"; Brief ground rules "Publish a data contract"."""
    c = adapter.get_data_contract(C.C360_PRODUCT)
    assert c.owner and c.steward and c.policy_approver
    assert c.columns
    assert len(c.quality_rules) >= C.CONTRACT_MIN_QUALITY_RULES
    assert c.allowed_uses and c.prohibited_uses
    assert c.refresh
    assert c.freshness_sla_hours == pytest.approx(C.FRESHNESS_SLA_HOURS)


def test_contract_owner_roles_match_the_design(adapter):
    """V1 Part 3: owner = Head of Collections Analytics; steward = Collections Data Engineering lead;
    policy approver = Collections Policy Office."""
    c = adapter.get_data_contract(C.C360_PRODUCT)
    assert "collections analytics" in c.owner.lower()
    assert "data engineering" in c.steward.lower()
    assert "policy office" in c.policy_approver.lower()


@pytest.mark.fairness
def test_contract_schema_has_no_protected_attributes(adapter):
    """V1 Part 3 rule 8 and V1 §10."""
    c = adapter.get_data_contract(C.C360_PRODUCT)
    names = {col.name for col in c.columns}
    assert not names & set(C.ALL_EXCLUDED_FROM_DECISIONS)


def test_direct_pii_is_masked_or_tokenised(adapter):
    """V1 Part 3 schema: display_name "Direct PII, masked for analysts"; phone/email "tokenised"."""
    c = adapter.get_data_contract(C.C360_PRODUCT)
    by = {col.name: col for col in c.columns}
    assert "display_name" in by and "mask" in by["display_name"].pii_class.lower()
    for tok in ("phone_token", "email_token"):
        assert tok in by and "token" in by[tok].pii_class.lower()


@pytest.mark.parametrize(
    "use",
    ["marketing", "credit decision", "outside collections", "external llm", "protected attributes"],
)
def test_contract_prohibits_the_listed_uses(adapter, use):
    """V1 Part 3 Uses, Not allowed: marketing or cross-selling; credit decisions or limit changes; any
    purpose outside collections; ...; joining protected attributes back in; raw PII to an external LLM."""
    c = adapter.get_data_contract(C.C360_PRODUCT)
    blob = " | ".join(c.prohibited_uses).lower()
    words = use.split()
    assert all(w in blob for w in words), f"{use!r} not in prohibited uses: {blob}"


# ---------------------------------------------------------------------------
# Quality rules (each a dbt test; error blocks publish unless warn)
# ---------------------------------------------------------------------------
def test_valid_snapshot_passes_and_publishes(adapter):
    """V1 Part 3 Quality rules: a clean snapshot passes every rule and is not blocked."""
    rep = _report(adapter)
    assert not rep.publish_blocked
    assert all(r.passed for r in rep.results if r.severity == "error")


@pytest.mark.parametrize(
    "rule_id,rows",
    [
        (1, [F.c360_row(), F.c360_row()]),  # duplicate golden_id
        (1, [F.c360_row(golden_id=None)]),
        (2, [F.c360_row(match_confidence=1.2)]),
        (2, [F.c360_row(match_confidence=-0.1)]),
        (2, [F.c360_row(match_method="probabilistic", match_confidence=0.10)]),  # below any sane auto-merge cut-off
        (3, [F.c360_row(max_dpd=38, total_past_due_cad=0.0)]),
        (4, [F.c360_row(consent_sms=None)]),
        (8, [F.c360_row(gender_code="F")]),
        (8, [F.c360_row(age=41)]),
        (9, [F.c360_row(_refreshed_at=NOW - dt.timedelta(hours=C.FRESHNESS_SLA_HOURS + 1))]),
    ],
    ids=["dup-id", "null-id", "conf>1", "conf<0", "conf<cutoff", "dpd-no-pastdue", "null-consent",
         "protected-col", "age-col", "stale"],
)
def test_error_rules_fail_and_block_publish(adapter, rule_id, rows):
    """V1 Part 3 Quality rules 1, 2, 3, 4, 8, 9 (severity Error): "a failure blocks publish"."""
    rep = _report(adapter, rows)
    r = rep.rule(rule_id)
    assert r.passed is False
    assert r.severity == "error"
    assert rep.publish_blocked


def test_rule2_low_confidence_allowed_when_reviewed_or_deterministic(adapter):
    """V1 Part 3 rule 2: "at or above the auto-merge cut-off unless match_method is deterministic or
    reviewed"."""
    rep = _report(adapter, [F.c360_row(match_method="reviewed", match_confidence=0.40)])
    assert rep.rule(2).passed


def test_rule3_zero_dpd_with_past_due_is_only_a_warning(adapter):
    """V1 Part 3 rule 3: "max_dpd = 0 with more than CAD 1 past due: warn"."""
    rep = _report(adapter, [F.c360_row(max_dpd=0, total_past_due_cad=25.0)])
    warn = [r for r in rep.results if r.rule_id == 3 and r.severity == "warn"]
    assert warn and not warn[0].passed
    assert not any(r.rule_id == 3 and r.severity == "error" and not r.passed for r in rep.results)


def test_rule4_consent_more_permissive_than_a_linked_crm_record_fails(adapter):
    """V1 Part 3 rule 4: consent "never more permissive than any linked current CRM record"."""
    snap = F.valid_snapshot([F.c360_row(consent_call=True)])
    snap.tables["crm_current"][0]["consent_call"] = False
    rep = adapter.run_quality_rules(snap, NOW)
    assert not rep.rule(4).passed and rep.publish_blocked


def test_rule5_two_national_id_hashes_in_one_golden_id_fails(adapter):
    """V1 Part 3 rule 5: "No golden_id links two different non-null national_id_hash values"."""
    row = F.c360_row(crm_customer_ids=["RYM-1142", "RYM-9999"])
    snap = F.valid_snapshot([row])
    snap.tables["crm_current"][1]["national_id_hash"] = "a-different-hash"
    rep = adapter.run_quality_rules(snap, NOW)
    assert not rep.rule(5).passed and rep.publish_blocked


def test_rule6_unmapped_crm_record_or_account_without_primary_fails(adapter):
    """V1 Part 3 rule 6: "Every current CRM record maps to one golden_id; every c360_account row has one
    primary party"."""
    snap = F.valid_snapshot()
    snap.tables["crm_current"].append({"crm_customer_id": "ORPHAN-1", "golden_id": None, "national_id_hash": "x",
                                       "consent_call": True, "consent_sms": True, "consent_email": True, "consent_push": True})
    assert not adapter.run_quality_rules(snap, NOW).rule(6).passed
    snap2 = F.valid_snapshot()
    snap2.tables["c360_account"][0]["party_role"] = "joint"
    assert not adapter.run_quality_rules(snap2, NOW).rule(6).passed


@pytest.mark.hardship
def test_rule7_hardship_lowered_without_reviewed_event_fails(adapter):
    """V1 Part 3 rule 7: "Every change of hardship_flag down to none has a hardship_flag_events row with
    a reviewer and reason"."""
    events = [{"golden_id": "G-004817", "from_level": "possible", "to_level": "none", "reviewer": None, "reason": None}]
    rep = _report(adapter, [F.c360_row(hardship_flag="none")], hardship_flag_events=events)
    assert not rep.rule(7).passed and rep.publish_blocked
    ok_events = [{"golden_id": "G-004817", "from_level": "possible", "to_level": "none",
                  "reviewer": "spec-001", "reason": "Income evidence provided"}]
    assert _report(adapter, [F.c360_row(hardship_flag="none")], hardship_flag_events=ok_events).rule(7).passed


def test_rule9_fresh_within_26_hours_passes(adapter):
    """V1 Part 3 rule 9 / Freshness SLA: `_refreshed_at` within the last 26 hours."""
    rep = _report(adapter, [F.c360_row(_refreshed_at=NOW - dt.timedelta(hours=C.FRESHNESS_SLA_HOURS - 1))])
    assert rep.rule(9).passed


@pytest.mark.s1
def test_rule10_low_employer_match_rate_warns_but_does_not_block(adapter):
    """V1 Part 3 rule 10 (V1 only, TBC): employer_key match rate at least 90% on the
    transactions.payroll_employer_key sample; severity Warn."""
    sample = [{"employer_key_true": "E1", "employer_key_matched": "E1"}] * 5 + \
             [{"employer_key_true": "E1", "employer_key_matched": "E2"}] * 5
    rep = _report(adapter, employer_match_sample=sample)
    r = rep.rule(10)
    assert r.passed is False and r.severity == "warn"
    assert not rep.publish_blocked


def test_report_lists_at_least_the_ten_contract_rules(adapter):
    """V1 Part 3 Quality rules table (rules 1-10); Brief Layer 1 must deliver "A data quality report"."""
    rep = _report(adapter)
    assert {r.rule_id for r in rep.results} >= set(range(1, 11))
