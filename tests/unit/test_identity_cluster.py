import math

from identity.cluster import assign_golden_ids, cluster


def test_missing_national_id_does_not_block_merge():
    roots = cluster(["A", "B"], [("A", "B")], {"A": "h1", "B": None})
    assert roots["A"] == roots["B"]


def test_conflicting_national_ids_never_merge_even_through_a_chain():
    roots = cluster(["A", "B", "C"], [("A", "B"), ("B", "C")], {"A": "h1", "B": None, "C": "h2"})
    assert roots["A"] != roots["C"]


def test_nan_is_not_a_national_id():
    # regression: NaN from pandas must be treated as missing by callers (identity.run builds nid with isinstance)
    nid = {c: (h if isinstance(h, str) and h else None) for c, h in [("A", "h1"), ("B", math.nan)]}
    roots = cluster(["A", "B"], [("A", "B")], nid)
    assert roots["A"] == roots["B"]


def test_golden_ids_are_stable_and_derived_from_smallest_member():
    roots = {"KIW-6380": "KIW-6380", "ABC-1": "ABC-1", "ABC-2": "ABC-1"}
    ids = assign_golden_ids(roots)
    assert ids == assign_golden_ids(dict(reversed(list(roots.items()))))
    assert ids["KIW-6380"] == "G-KIW6380" and ids["ABC-1"] == "G-ABC1"
