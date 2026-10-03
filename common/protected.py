"""Protected attributes. Nothing in features, semantic layer, prompts or models may use them.

Only `governance/fairness/` may read these, through the restricted auditor view.
"""

from __future__ import annotations

from collections.abc import Iterable

PROTECTED_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "gender_code",
        "marital_status",
        "citizenship_status",
        "household_size",
        "dependants_count",
        "newcomer_program_flag",
        "newcomer_arrival_date",
        "accessibility_needs_flag",
        "accessibility_type",
        "vulnerability_type",
        "ccb_deposit_flag",
        "customer_accent_region",
    }
)

# Our own extra exclusions: age is a protected ground in Canada; voice acoustics can proxy gender/age/accent.
EXTRA_EXCLUDED: frozenset[str] = frozenset(
    {"age", "age_band", "pitch_mean", "pitch_std", "energy_mean", "speaking_rate", "filler_rate"}
)

FORBIDDEN: frozenset[str] = PROTECTED_ATTRIBUTES | EXTRA_EXCLUDED


class ProtectedAttributeError(ValueError):
    pass


def find_forbidden(names: Iterable[str]) -> set[str]:
    """Return any forbidden names in `names` (matched on the bare column name, case-insensitive)."""
    found = set()
    for n in names:
        bare = n.split(".")[-1].strip().lower()
        if bare in FORBIDDEN:
            found.add(n)
    return found


def assert_no_protected(names: Iterable[str], where: str) -> None:
    bad = find_forbidden(names)
    if bad:
        raise ProtectedAttributeError(f"{where} references protected/excluded attributes: {sorted(bad)}")
