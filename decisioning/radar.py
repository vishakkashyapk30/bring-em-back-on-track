"""S1 employer shock radar: weekly per employer_key with >= 10 customers: payroll-gap count, new EI
count, avg payroll_amount_change_pct vs own history and industry_naics2 peers. Gap + new EI = 'layoff-like';
gap without EI = 'payroll delay'. Check ops_events first. A radar, not a layoff detector."""


def employer_week(week: str) -> list[dict]:
    raise NotImplementedError("TODO(WS-D)")
