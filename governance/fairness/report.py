"""Run the fairness audit and write reports/fairness.json (aggregates only).
Run: python -m governance.fairness.report"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from common.config import get_settings
from governance.fairness import outcome_test, proxy_test


def build() -> dict:
    proxy = proxy_test.run()
    outcome = outcome_test.run()
    reviews = [g["review_note"] for g in proxy["groups"] if g.get("review")]
    reviews += [f"{a['attribute']}: {r['group']} ({r['status']}, excess gap {r['excess_gap']:+.3f}, flag ratio "
                f"{r['flag_ratio']})" for a in outcome["attributes"] for r in a["groups"] if r["status"] == "review"]
    return {
        "meta": {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                 "source": "warehouse + ptp_test_scores.parquet", "fixture": False},
        "proxy": proxy,
        "outcome": outcome,
        "review_items": reviews,
        "note": "Aggregates only; groups under 10 customers are hidden. Protected attributes are read only by "
                "governance/fairness through the auditor view and are never model inputs.",
    }


def main() -> None:
    rep = build()
    path = get_settings().reports_dir / "fairness.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rep, indent=2, default=str))
    print(f"wrote {path}: {len(rep['review_items'])} items for review")
    for r in rep["review_items"]:
        print(" -", r)


if __name__ == "__main__":
    main()
