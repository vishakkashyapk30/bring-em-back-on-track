"""Training frame = labels + PIT features (features.pit). Time split: train to Mar 2026, validate
Apr-Jun, test Jul-Sep (TBC after profiling). Asserts no protected or wide _mNN columns."""

import re

from common.protected import assert_no_protected

WIDE_COLS = re.compile(r"_m(0[1-9]|1[0-2])$")


def check_columns(cols: list[str]) -> None:
    assert_no_protected(cols, "ptp_break training frame")
    leaked = [c for c in cols if WIDE_COLS.search(c)]
    if leaked:
        raise ValueError(f"Wide _m01.._m12 columns leak the future: {leaked}")


def build_dataset():
    raise NotImplementedError("TODO(WS-C)")
