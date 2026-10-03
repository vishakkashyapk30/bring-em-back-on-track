"""Feature store: same values offline and online, point-in-time correct, no future leakage
(Brief Layer 3; V1 §5; v2 §5)."""

from __future__ import annotations

import datetime as dt
import re

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C

pytestmark = pytest.mark.features

SQL_FEATURES = ["dpd_max_current", "ptp_broken_count_90d", "payroll_delay_days"]


def test_online_equals_offline_at_the_same_time(loaded, ryan_gid):
    """Brief Layer 3 takeaway "Same values everywhere. One definition for training (offline) and live
    scoring (online)"; V1 §5 "The same code builds both"."""
    on = loaded.get_features_online(ryan_gid, SQL_FEATURES)
    off = loaded.get_features_offline(ryan_gid, F.AS_OF, SQL_FEATURES)
    for name in SQL_FEATURES:
        assert on.values[name].value == off.values[name].value, name
        assert on.values[name].version == off.values[name].version, name


def test_nightly_parity_check_finds_no_mismatch(loaded):
    """V1 §5: "Each night I recompute 1,000 online values the offline way and raise an alert if any
    differ"."""
    rep = loaded.run_parity_check(C.PARITY_SAMPLE_SIZE)
    assert rep.sampled > 0
    assert rep.mismatches == 0 and rep.alert_raised is False


def test_every_value_carries_when_it_was_known(loaded, ryan_gid):
    """V1 §5: "Every value carries the time I could first have known it"; v2 `available_ts`."""
    off = loaded.get_features_offline(ryan_gid, F.AS_OF, SQL_FEATURES)
    for name, v in off.values.items():
        assert v.available_ts is not None, name
        assert v.available_ts <= F.AS_OF, f"{name} known at {v.available_ts}, after as_of {F.AS_OF}"


def test_point_in_time_excludes_a_break_not_yet_known(loaded, ryan_gid):
    """V1 §5 "training on history never sees the future"; v2 "point-in-time join 'as of' each decision
    time". Ryan's PTP-0090311 (due 25 Sep, grace 2 days) cannot count as broken on 20 Sep."""
    early = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.UTC)
    off_early = loaded.get_features_offline(ryan_gid, early, ["ptp_broken_count_90d"])
    off_now = loaded.get_features_offline(ryan_gid, F.AS_OF, ["ptp_broken_count_90d"])
    assert off_early.values["ptp_broken_count_90d"].value == 0
    assert off_now.values["ptp_broken_count_90d"].value == 1


def test_offline_as_of_never_returns_values_from_the_future(loaded, ryan_gid):
    """V1 §5 point-in-time (property over several as-of dates)."""
    names = [f.name for f in loaded.get_feature_registry()]
    for days_back in (1, 7, 15, 30):
        as_of = F.AS_OF - dt.timedelta(days=days_back)
        off = loaded.get_features_offline(ryan_gid, as_of, names)
        for name, v in off.values.items():
            if v.present and v.available_ts is not None:
                assert v.available_ts <= as_of, (name, days_back)


def test_wide_monthly_columns_are_not_training_inputs(loaded):
    """V1 §3: "Models train on monthly snapshots ... never on the wide _m01 to _m12 columns, because those
    were computed at a later date and would leak the future"."""
    for f in loaded.get_feature_registry():
        assert not re.search(r"_m(0[1-9]|1[0-2])$", f.name), f.name


def test_text_features_without_a_transcript_are_missing_not_zero(loaded):
    """V1 §5 Coverage: "text and voice features are marked present or missing"; v2 `has_transcript`."""
    gid = loaded.find_golden_id("crm", "LKS-0001")  # colleague with no transcript
    vec = loaded.get_features_online(gid, ["hardship_signal", "ptp_intent_strength", "stated_delay_reason"])
    for name, v in vec.values.items():
        assert v.present is False, f"{name} should be missing, got {v.value!r}"


@pytest.mark.s7
def test_stress_signals_exist_for_every_customer(loaded):
    """V1 §5 Coverage: "the stress signals (S7) matter: they exist for every customer"."""
    for crm in ("RYM-1142", "LKS-0000", "LKS-0005"):
        gid = loaded.find_golden_id("crm", crm)
        vec = loaded.get_features_online(gid, ["nsf_count_mtd", "days_negative_mtd"])
        assert all(v.present for v in vec.values.values()), crm


def test_bureau_features_keep_their_pull_date(loaded, ryan_gid):
    """V1 §5 table: `risk_score_delta_90d` "(keeps its pull date)"; v2 "the pull date for bureau data"."""
    v = loaded.get_features_online(ryan_gid, ["risk_score_delta_90d"]).values["risk_score_delta_90d"]
    assert v.available_ts is not None and v.available_ts.date() >= dt.date(2026, 7, 1)
