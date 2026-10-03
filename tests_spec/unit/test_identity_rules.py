"""Identity matching safety rules and survivorship (V1 §3; v2 §3; contract rules 5-6)."""

from __future__ import annotations

import dataclasses

import pytest

from tests_spec import factories as F
from tests_spec import spec_constants as C
from tests_spec.factories import member_key

pytestmark = pytest.mark.identity


def _cluster_of(result, rec):
    gid = result.golden_id_of(member_key(rec))
    assert gid is not None, f"{member_key(rec)} was not placed in any cluster"
    return gid


def test_ryan_four_source_ids_resolve_to_one_golden_id(adapter):
    """Brief Layer 1 example: "4 source IDs -> 1 golden ID" (cards:C-88213, loans:L-5538921,
    crm:RYM-1142, deposits:CHQ-7730); takeaway "One customer, one ID"."""
    recs = F.ryan_source_records()
    res = adapter.resolve_identities(recs)
    gids = {_cluster_of(res, r) for r in recs}
    assert len(gids) == 1


def test_match_confidence_is_shown_and_bounded(adapter):
    """Brief Layer 1 takeaway "with the match confidence shown"; contract rule 2 `match_confidence`
    between 0 and 1; `match_method` in deterministic / probabilistic / reviewed."""
    res = adapter.resolve_identities(F.ryan_source_records())
    for c in res.clusters:
        assert 0.0 <= c.match_confidence <= 1.0
        assert c.match_method in C.MATCH_METHODS


def test_different_people_stay_apart(adapter):
    """V1 §3: "Merging two people means calling the wrong person about a debt, so I would rather miss a
    link"."""
    recs = F.ryan_source_records() + [F.other_person_record(1)]
    res = adapter.resolve_identities(recs)
    assert _cluster_of(res, recs[0]) != _cluster_of(res, recs[-1])


def test_exact_key_duplicate_of_crm_id_links_deterministically(adapter):
    """V1 §3 pass 1 "Exact keys ... duplicate_of_crm_id ... Linked automatically"."""
    a = F.other_person_record(1)
    b = F.other_person_record(2, first_name="P.", raw_name="P RAMAN", phone=None, duplicate_of_crm_id=a.source_key,
                              national_id_hash=None)
    res = adapter.resolve_identities([a, b])
    assert _cluster_of(res, a) == _cluster_of(res, b)
    cl = next(c for c in res.clusters if member_key(a) in c.members)
    assert cl.match_method == "deterministic"


def test_shared_national_id_hash_links_crm_records(adapter):
    """V1 §3 pass 1: "Same national_id_hash across CRM records" -> linked automatically."""
    a = F.other_person_record(1)
    b = F.other_person_record(2, national_id_hash=a.national_id_hash, phone="+14165550999")
    res = adapter.resolve_identities([a, b])
    assert _cluster_of(res, a) == _cluster_of(res, b)


def test_cannot_link_two_different_national_id_hashes(adapter):
    """V1 §3 Safety rules: "A cluster can never contain two different national ID hashes"; v2: "hard
    cannot-link"; contract rule 5. Same name, DOB, phone and postcode but different hashes."""
    a = F.other_person_record(1)
    b = F.other_person_record(2, phone=a.phone, national_id_hash="nidhash-DIFFERENT")
    res = adapter.resolve_identities([a, b])
    assert _cluster_of(res, a) != _cluster_of(res, b)


def test_cannot_link_survives_transitive_chains(adapter):
    """V1 §3 Safety rules + v2 "go to review, not chain-merge": A~B and B~C must not pull together A and C
    when A and C carry different national ID hashes."""
    a = F.other_person_record(1, national_id_hash="nid-A")
    b = F.other_person_record(2, source_system="cards", national_id_hash=None, crm_customer_id=None,
                              raw_name="PRIYA RAMAN", phone=a.phone)
    c = F.other_person_record(3, national_id_hash="nid-C", phone=a.phone)
    res = adapter.resolve_identities([a, b, c])
    hashes_per_cluster: dict[str, set] = {}
    by_key = {member_key(r): r for r in (a, b, c)}
    for cl in res.clusters:
        hs = {by_key[m].national_id_hash for m in cl.members if m in by_key and by_key[m].national_id_hash}
        hashes_per_cluster[cl.golden_id] = hs
    assert all(len(hs) <= 1 for hs in hashes_per_cluster.values()), hashes_per_cluster


def test_large_cluster_goes_to_human_review(adapter):
    """V1 §3 Safety rules: "any cluster with more than five CRM records goes to a person"."""
    n = C.MAX_CRM_RECORDS_PER_AUTO_CLUSTER + 1
    base = F.other_person_record(0)
    recs = [base] + [
        F.other_person_record(i, national_id_hash=None, duplicate_of_crm_id=base.source_key) for i in range(1, n)
    ]
    res = adapter.resolve_identities(recs)
    reviewed_keys = {k for item in res.review_queue for k in item.member_keys}
    auto_linked = [
        c for c in res.clusters
        if c.status == "linked" and len([m for m in c.members if m.startswith("crm:")]) > C.MAX_CRM_RECORDS_PER_AUTO_CLUSTER
    ]
    assert not auto_linked, "a cluster with more than five CRM records must not be auto-linked"
    assert reviewed_keys & {member_key(r) for r in recs}


def test_cluster_of_five_crm_records_may_auto_link(adapter):
    """V1 §3: the review threshold is *more than* five, so exactly five is not forced to review."""
    n = C.MAX_CRM_RECORDS_PER_AUTO_CLUSTER
    base = F.other_person_record(0)
    recs = [base] + [
        F.other_person_record(i, national_id_hash=None, duplicate_of_crm_id=base.source_key) for i in range(1, n)
    ]
    res = adapter.resolve_identities(recs)
    assert len({_cluster_of(res, r) for r in recs}) == 1


def test_review_items_show_masked_data_only(adapter):
    """V1 §3 pass 3: "An AI reads a masked pair; a data steward decides"; contract Not allowed:
    "Sending raw PII to an external LLM"."""
    n = C.MAX_CRM_RECORDS_PER_AUTO_CLUSTER + 1
    base = F.other_person_record(0)
    recs = [base] + [F.other_person_record(i, national_id_hash=None, duplicate_of_crm_id=base.source_key) for i in range(1, n)]
    res = adapter.resolve_identities(recs)
    assert res.review_queue
    for item in res.review_queue:
        blob = repr(item.masked_view)
        for r in recs:
            assert r.phone not in blob
            if r.national_id_hash:
                assert r.national_id_hash not in blob
        assert item.decided is False, "only a data steward decides"


def test_golden_ids_are_stable_across_reruns(adapter):
    """V1 §3: "Customers keep the same ID when I rerun"; contract `golden_id` "stable across reruns"."""
    recs = F.ryan_source_records() + [F.other_person_record(1)]
    first = adapter.resolve_identities(recs)
    second = adapter.resolve_identities(recs, previous=first)
    for r in recs:
        assert first.golden_id_of(member_key(r)) == second.golden_id_of(member_key(r))


def test_golden_ids_stay_stable_when_new_records_arrive(adapter):
    """v2 §3 Stable IDs: "On rerun a cluster keeps the golden_id of the old cluster it overlaps most"."""
    recs = F.ryan_source_records()
    first = adapter.resolve_identities(recs)
    newcomer = F.other_person_record(7)
    second = adapter.resolve_identities(recs + [newcomer], previous=first)
    assert second.golden_id_of(member_key(recs[0])) == first.golden_id_of(member_key(recs[0]))
    assert second.golden_id_of(member_key(newcomer)) != first.golden_id_of(member_key(recs[0]))


def test_merge_keeps_the_older_id(adapter):
    """v2 §3 Stable IDs: "Merges keep the older ID and identity_events keeps aliases"."""
    a = F.other_person_record(1)
    first = adapter.resolve_identities([a])
    old = first.golden_id_of(member_key(a))
    b = F.other_person_record(2, duplicate_of_crm_id=a.source_key, national_id_hash=None)
    second = adapter.resolve_identities([a, b], previous=first)
    assert second.golden_id_of(member_key(b)) == old


# ---------------------------------------------------------------------------
# Survivorship
# ---------------------------------------------------------------------------
def _golden(res, rec):
    gid = _cluster_of(res, rec)
    assert gid in res.golden_records, "resolve_identities must return golden records for clusters"
    return res.golden_records[gid]


@pytest.mark.parametrize("channel", C.CONSENT_CHANNELS)
def test_consent_takes_the_most_restrictive_value(adapter, channel):
    """V1 §3 Safety rules: "For consent and do-not-contact flags I take the strictest value I find";
    contract `consent_*` "most restrictive across linked records"; rule 4."""
    a = F.other_person_record(1, consent={ch: True for ch in C.CONSENT_CHANNELS})
    b = F.other_person_record(2, national_id_hash=a.national_id_hash,
                              consent={**{ch: True for ch in C.CONSENT_CHANNELS}, channel: False})
    g = _golden(adapter.resolve_identities([a, b]), a)
    assert g.consent.get(channel) is False


def test_cease_on_any_linked_record_applies_to_customer(adapter):
    """V1 §3: strictest do-not-contact value wins (v2: "Consent, cease and do-not-call: most restrictive")."""
    a = F.other_person_record(1)
    b = F.other_person_record(2, national_id_hash=a.national_id_hash, cease_communication_flag=True)
    g = _golden(adapter.resolve_identities([a, b]), a)
    assert g.contact_block == "cease"


@pytest.mark.hardship
@pytest.mark.parametrize("field_name,value", [("hardship_flag", "possible"), ("vulnerability_flag", True)])
def test_hardship_or_vulnerability_on_any_linked_record_applies(adapter, field_name, value):
    """V1 §3: "a hardship or vulnerability flag on any linked record applies to the customer"."""
    a = F.other_person_record(1)
    b = F.other_person_record(2, national_id_hash=a.national_id_hash, **{field_name: value})
    g = _golden(adapter.resolve_identities([a, b]), a)
    assert getattr(g, field_name) == value


def test_name_and_birth_date_come_from_the_current_crm_record(adapter):
    """V1 §3: "Name and birth date come from the current CRM record" (current = effective_to_ts
    9999-12-31, not is_deleted)."""
    old = F.other_person_record(1, first_name="Pria", raw_name="Pria Ramen", is_current=False, dob_raw="1990-02-11")
    cur = F.other_person_record(1, source_key="CRM-OTHER-001b", first_name="Priya", is_current=True,
                                national_id_hash=old.national_id_hash)
    g = _golden(adapter.resolve_identities([old, cur]), cur)
    assert "Priya" in (g.display_name or "")
    assert g.date_of_birth is not None and g.date_of_birth.isoformat() == "1990-11-02"


def test_email_used_only_if_verified_and_not_bounced(adapter):
    """Contract `email_token`: "email (verified, not bounced)"."""
    bounced = F.other_person_record(1, email="p@example.test", email_verified=True, email_bounced=True)
    g = _golden(adapter.resolve_identities([bounced]), bounced)
    assert g.email_token in (None, "")


@pytest.mark.parametrize(
    "raw_name,dob_raw",
    [("R. MITCHELL", "12/04/1985"), ("MITCHELL, RYAN JAMES", "19850412"), ("RYAN MITCHELL", "Apr 12 1985")],
)
def test_messy_name_and_dob_formats_still_match(adapter, raw_name, dob_raw):
    """V1 §3 Messy data: "Birth dates come in four formats, and names appear as 'R. MITCHELL' or
    'MITCHELL, RYAN JAMES', so I parse each source on its own terms"."""
    crm = F.ryan_source_records()[0]
    other = dataclasses.replace(F.ryan_source_records()[2], raw_name=raw_name, dob_raw=dob_raw)
    res = adapter.resolve_identities([crm, other])
    assert _cluster_of(res, crm) == _cluster_of(res, other)


@pytest.mark.fairness
def test_golden_record_has_no_protected_attributes(adapter):
    """Contract rule 8: "No protected-attribute column (the 12 in Governance, plus age, age_band)
    exists in this table"."""
    recs = [dataclasses.replace(r, protected=dict(F.PROTECTED_VARIANT_B)) for r in F.ryan_source_records()]
    g = _golden(adapter.resolve_identities(recs), recs[0])
    present = set(vars(g)) | set(g.extra)
    assert not present & set(C.ALL_EXCLUDED_FROM_DECISIONS)
