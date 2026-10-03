"""Identity resolution -> golden record -> features -> NBA (Brief Layers 1, 3, 4; V1 §3, §5, §6)."""

from __future__ import annotations

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.helpers import is_pressure

pytestmark = [pytest.mark.identity, pytest.mark.nba]

RYAN_SOURCES = [("cards", "C-88213"), ("loans", "L-5538921"), ("crm", "RYM-1142"), ("deposits", "CHQ-7730")]


def test_all_four_source_ids_resolve_to_one_golden_id(loaded):
    """Brief Layer 1 example: "4 source IDs -> 1 golden ID"; must deliver "Customer ID matching across
    sources"."""
    gids = {loaded.find_golden_id(s, k) for s, k in RYAN_SOURCES}
    assert len(gids) == 1 and None not in gids


def test_colleagues_get_their_own_golden_ids(loaded, ryan_gid):
    """V1 §3 ("I would rather miss a link"): same employer and postcode must not merge different people."""
    other = loaded.find_golden_id("crm", "LKS-0000")
    assert other and other != ryan_gid


def test_golden_record_carries_the_c360_fields(loaded, ryan_gid):
    """V1 Part 3 schema (`gold.c360_customer`) and Brief C360 mock-up badges (bucket, consent, hardship)."""
    g = loaded.get_golden_record(ryan_gid)
    assert g.max_dpd == 38
    assert g.payroll_delay_days == 29
    assert g.time_zone == F.TORONTO
    assert g.consent.get("push") is False and g.consent.get("sms") is True
    assert g.permitted_call_start_local == "08:00" and g.permitted_call_end_local == "20:00"
    assert g.open_case_id == "CASE-RYM-0001"
    assert 0 <= (g.match_confidence or 0) <= 1


def test_every_field_carries_lineage_and_a_refresh_time(loaded, ryan_gid):
    """Brief Layer 1 takeaway "Trusted, not just joined. Every field carries lineage, a refresh time and
    the quality checks behind it"."""
    g = loaded.get_golden_record(ryan_gid)
    assert g.refreshed_at is not None
    assert g.lineage, "lineage must be recorded"
    assert set(g.lineage.get("max_dpd", [])) & {"card_accounts", "loan_accounts", "c360_account"}


@pytest.mark.hardship
def test_hardship_mention_on_the_case_raises_the_golden_hardship_flag(loaded, ryan_gid):
    """V1 Part 3 `hardship_flag` "from collections_cases.hardship_flag, hardship_mentioned_flag,
    hardship_signal"; V1 §10: any signal raises to possible."""
    assert loaded.get_golden_record(ryan_gid).hardship_flag in ("possible", "clear")


@pytest.mark.fairness
def test_protected_attributes_do_not_reach_the_golden_record_or_features(loaded, ryan_gid):
    """V1 Part 3 rule 8 + V1 §10: the 12 protected attributes (and age, age_band) are not in the C360 and
    not features, although the raw `customers` table carries them."""
    g = loaded.get_golden_record(ryan_gid)
    assert not (set(vars(g)) | set(g.extra)) & set(C.ALL_EXCLUDED_FROM_DECISIONS)
    names = {f.name for f in loaded.get_feature_registry()}
    vec = loaded.get_features_online(ryan_gid, sorted(names))
    assert not set(vec.values) & set(C.ALL_EXCLUDED_FROM_DECISIONS)


@pytest.mark.features
def test_online_features_reflect_the_golden_record(loaded, ryan_gid):
    """Brief Layer 3 example online vector (dpd_max_current 38, payroll_delay_days 29, ptp_broken_count_90d 1)."""
    vec = loaded.get_features_online(ryan_gid, ["dpd_max_current", "payroll_delay_days", "ptp_broken_count_90d"])
    assert vec.values["dpd_max_current"].value == 38
    assert vec.values["payroll_delay_days"].value == 29
    assert vec.values["ptp_broken_count_90d"].value == 1


@pytest.mark.explanation
def test_nba_for_ryan_is_explained_with_his_own_facts(loaded):
    """V1 §6 step 5 "Payroll 29 days late"; NI §8 demo step 2."""
    d = loaded.propose_next_best_action_for_case("CASE-RYM-0001", F.weekday_local(9, 0))
    reasons = " ".join(d.explanation.risk_reasons).lower()
    assert "payroll" in reasons and "29" in reasons


@pytest.mark.hardship
def test_nba_for_ryan_has_no_pressure_because_of_the_hardship_flag(loaded):
    """NI §8 step 4 "The latch has already stopped pressure actions"; V1 §6 step 1."""
    d = loaded.propose_next_best_action_for_case("CASE-RYM-0001", F.weekday_local(9, 0))
    assert not is_pressure(d.action)
    assert d.review_mode == "individual"


def test_pipeline_quality_report_is_produced_and_clean(loaded_with_report):
    """Brief Layer 1 must deliver "A data quality report"; V1 Part 3 Quality rules."""
    _, rep = loaded_with_report
    assert rep is not None and rep.results
    assert not rep.publish_blocked


def test_conflicting_national_ids_block_a_merge_end_to_end(adapter):
    """V1 §3 Safety rules (cannot-link) through the real pipeline: a twin CRM record with the same name,
    DOB and phone but a different national_id_hash stays a separate golden ID."""
    t = F.ryan_mitchell_tables(include_cohort=False)
    twin = {**t["customers"][0], "crm_customer_id": "RYM-TWIN", "national_id_hash": "nidhash-someone-else"}
    t["customers"].append(twin)
    adapter.load_sources(t)
    adapter.run_pipeline(F.AS_OF)
    assert adapter.find_golden_id("crm", "RYM-TWIN") != adapter.find_golden_id("crm", "RYM-1142")


def test_rerunning_the_pipeline_keeps_golden_ids(adapter):
    """V1 §3 "Customers keep the same ID when I rerun"; V1 §9 nightly rebuild."""
    adapter.load_sources(F.ryan_mitchell_tables())
    adapter.run_pipeline(F.AS_OF)
    first = {k: adapter.find_golden_id(s, k) for s, k in RYAN_SOURCES}
    adapter.run_pipeline(F.AS_OF.replace(day=7))
    second = {k: adapter.find_golden_id(s, k) for s, k in RYAN_SOURCES}
    assert first == second


def test_most_restrictive_consent_survives_through_the_pipeline(adapter):
    """V1 §3 survivorship + contract rule 4: a duplicate CRM record without SMS consent removes SMS for the
    customer, and NBA then never proposes SMS."""
    t = F.ryan_mitchell_tables(include_cohort=False)
    dup = {**t["customers"][0], "crm_customer_id": "RYM-1142-DUP", "consent_sms": False,
           "duplicate_of_crm_id": "RYM-1142"}
    t["customers"].append(dup)
    adapter.load_sources(t)
    adapter.run_pipeline(F.AS_OF)
    gid = adapter.find_golden_id("crm", "RYM-1142")
    assert adapter.find_golden_id("crm", "RYM-1142-DUP") == gid
    assert adapter.get_golden_record(gid).consent.get("sms") is False
    d = adapter.propose_next_best_action_for_case("CASE-RYM-0001", F.weekday_local(9, 0))
    assert d.action.channel != "sms"
