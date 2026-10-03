"""Check that every `table.column` referenced in a file exists in the data dictionary.

Usage: python scripts/check_fields.py README.md decisioning/*.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLS = ROOT / "docs" / "data_dictionary" / "CIBC Hackathon - Data Dictionary - Columns.csv"


def known() -> tuple[set[str], set[str]]:
    with COLS.open() as f:
        rows = list(csv.DictReader(f))
    return {r["Table"] for r in rows}, {f"{r['Table']}.{r['Column']}" for r in rows}


def main(paths: list[str]) -> int:
    tables, cols = known()
    pat = re.compile(r"\b([a-z_]+)\.([a-z0-9_]+)\b(?!\*)")
    bad = 0
    for p in paths:
        for m in pat.finditer(Path(p).read_text()):
            ref = f"{m.group(1)}.{m.group(2)}"
            if m.group(1) in tables and ref not in cols:
                print(f"{p}: unknown column {ref}")
                bad += 1
    print("OK" if not bad else f"{bad} unknown reference(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
