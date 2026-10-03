"""Proxy-feature gate (H4) and the feature registry (V1 §5, §10; NI H4)."""

from __future__ import annotations

import random

import pytest

from tests_spec import spec_constants as C

pytestmark = pytest.mark.fairness


def _table(n=400, seed=11):
    rng = random.Random(seed)
    feats, prot = [], []
    for i in range(n):
        g = rng.choice(["F", "M"])
        newcomer = rng.random() < 0.3
        feats.append({
            "entity_id": f"G-{i}",
            "gender_copy": 1.0 if g == "F" else 0.0,  # perfect proxy
            "noisy_newcomer": (1.0 if newcomer else 0.0) + rng.gauss(0, 0.15),  # strong proxy
            "dpd_max_current": rng.randint(0, 120),  # independent
            "card_utilisation": rng.random(),  # independent
        })
        prot.append({"entity_id": f"G-{i}", "gender_code": g, "newcomer_program_flag": newcomer})
    return feats, prot


@pytest.mark.h4
def test_feature_group_that_predicts_a_protected_attribute_is_dropped_or_coarsened(adapter):
    """V1 §5 Fairness gate (H4): "If a group of features can predict a protected attribute (AUC above
    0.65), I drop it or make it coarser"."""
    feats, prot = _table()
    rep = adapter.proxy_feature_gate(feats, prot, {"proxy": ["gender_copy"], "newcomer": ["noisy_newcomer"]})
    for g in ("proxy", "newcomer"):
        assert rep.groups[g].max_auc > C.PROXY_AUC_THRESHOLD
        assert rep.groups[g].decision in ("drop", "coarsen")


@pytest.mark.h4
def test_independent_feature_group_is_kept(adapter):
    """V1 §5 H4: a group that does not predict any protected attribute (AUC near 0.5) stays."""
    feats, prot = _table()
    rep = adapter.proxy_feature_gate(feats, prot, {"delinquency": ["dpd_max_current", "card_utilisation"]})
    assert rep.groups["delinquency"].max_auc <= C.PROXY_AUC_THRESHOLD
    assert rep.groups["delinquency"].decision == "keep"


@pytest.mark.h4
def test_gate_names_the_attribute_a_proxy_stands_in_for(adapter):
    """NI H4 (report which protected attribute, plus mutual information)."""
    feats, prot = _table()
    rep = adapter.proxy_feature_gate(feats, prot, {"proxy": ["gender_copy"]})
    assert rep.groups["proxy"].worst_protected_attribute == "gender_code"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
@pytest.mark.features
def test_registry_records_owner_source_refresh_version_and_builder(adapter):
    """V1 §5: "A registry records each feature's owner, source, refresh time and version, and how it is
    built (SQL, AI or voice analysis)"."""
    reg = adapter.get_feature_registry()
    assert reg
    for f in reg:
        assert f.owner and f.source and f.refresh and f.version, f.name
        assert f.built_by.lower() in {"sql", "ai", "llm", "voice"}, f.built_by


@pytest.mark.features
def test_ai_features_carry_prompt_version_and_accuracy(adapter):
    """V1 §5: "AI features are stored with the prompt version that produced them and their accuracy
    against hand labels"; Brief Layer 3 takeaway "LLM features are tested"."""
    ai = [f for f in adapter.get_feature_registry() if f.built_by.lower() in ("ai", "llm")]
    assert ai, "the design names hardship_signal, stated_delay_reason, ptp_intent_strength, dispute_signal"
    for f in ai:
        assert f.prompt_version, f.name
        assert f.label_accuracy is not None and 0 <= f.label_accuracy <= 1, f.name


@pytest.mark.features
def test_registry_contains_the_designed_text_features(adapter):
    """V1 §5 table: `hardship_signal`, `stated_delay_reason`, `ptp_intent_strength`, `dispute_signal`."""
    names = {f.name for f in adapter.get_feature_registry()}
    assert {"hardship_signal", "stated_delay_reason", "ptp_intent_strength", "dispute_signal"} <= names


@pytest.mark.features
def test_no_protected_attribute_is_a_feature(adapter):
    """V1 §10: none of the 12 protected attributes (plus age, age band) feed a model."""
    names = {f.name.lower() for f in adapter.get_feature_registry()}
    assert not names & {a.lower() for a in C.ALL_EXCLUDED_FROM_DECISIONS}


@pytest.mark.features
@pytest.mark.a3
def test_no_voice_characteristic_features(adapter):
    """V1 §5: "From voice I use only call-level measures, never pitch, speaking speed or accent"; v2:
    pitch, energy, speaking rate, filler rate and customer_accent_region stay out."""
    for f in adapter.get_feature_registry():
        lname = f.name.lower()
        assert not any(k in lname for k in C.FORBIDDEN_VOICE_FEATURE_KEYWORDS), f.name


@pytest.mark.features
def test_email_open_flag_is_not_used(adapter):
    """v2 §5: link clicks, "not email_opened_flag: Apple MPP inflates it"; NI §4 channel optimisation."""
    names = {f.name.lower() for f in adapter.get_feature_registry()}
    assert "email_opened_flag" not in names
