"""Portfolio headline numbers and the home-page visuals. Every endpoint here needs a signed-in persona: nothing
data-driven is shown before sign-in. (The router is still named public for the URL the frontend already uses.)"""

import json

from fastapi import APIRouter, Depends, Response

from api.deps import current_session
from api.services import public_visuals as pv
from common.config import get_settings

router = APIRouter(prefix="/public", tags=["portfolio"], dependencies=[Depends(current_session)])


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


@router.get("/map")
def public_map(response: Response) -> dict:
    """Province and postal-area risk numbers for the landing map: all four metrics, last 12 months, one payload."""
    response.headers["Cache-Control"] = "private, max-age=300"
    return pv.public_map()


@router.get("/flow")
def public_flow(response: Response) -> dict:
    """Counts at each step of last night's decision run. Empty (available=false) if the plan is not built."""
    response.headers["Cache-Control"] = "private, max-age=300"
    return pv.public_flow()


@router.get("/sample-customer")
def public_sample_customer(response: Response) -> dict:
    """One anonymous customer: source systems, match confidences and the proposed next action. No identifiers."""
    response.headers["Cache-Control"] = "private, max-age=300"
    return pv.public_sample()
