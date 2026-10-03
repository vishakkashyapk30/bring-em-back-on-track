"""H1 hardship plan simulator, arithmetic only. Never uses household_size / dependants_count.
Outputs: new payment vs monthly surplus; months to clear + total interest; bank impact vs status quo
(discount rate + LGD as stated assumptions); observed hold rate of similar offers ('observed, not causal');
approver level + eligibility. Every run is logged to ops.db simulator_runs + audit_log."""

ASSUMPTIONS = {"annual_discount_rate": 0.06, "lgd": 0.65}  # TBC, shown on screen


def simulate(case_id: str, levers: dict) -> dict:
    raise NotImplementedError("TODO(WS-D)")
