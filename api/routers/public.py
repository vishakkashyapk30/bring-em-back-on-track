"""Public (no sign-in) headline numbers for the landing page, read from the pipeline's own reports."""

import json

from fastapi import APIRouter

from common.config import get_settings

router = APIRouter(prefix="/public", tags=["public"])


def _load(name: str) -> dict:
    p = get_settings().reports_dir / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


@router.get("/summary")
def summary() -> dict:
    dq, bench = _load("data_quality"), _load("benchmark")
    parity, text = _load("feature_parity"), _load("text_rules_eval")
    ident, c360 = dq.get("identity", {}), dq.get("c360", {})
    accounts, linked = float(ident.get("accounts") or 0), float(ident.get("accounts_linked") or 0)
    tests = dq.get("contract_tests", [])
    return {
        "golden_customers": int(c360.get("customers") or ident.get("golden_ids") or 0),
        "crm_records": int(ident.get("crm_records") or 0),
        "accounts_linked_pct": round(100 * linked / accounts, 1) if accounts else None,
        "open_cases": int(c360.get("with_open_case") or 0),
        "issues_found": len(dq.get("issues", [])),
        "contract_tests_passed": sum(t.get("status") == "pass" for t in tests), "contract_tests": len(tests),
        "benchmark_questions": bench.get("questions"), "benchmark_dev_score": bench.get("dev_mean_score"),
        "parity_mismatches": parity.get("mismatched_rows"), "parity_sampled": parity.get("sampled"),
        "text_hardship_accuracy": (text.get("accuracy") or {}).get("hardship"),
    }
