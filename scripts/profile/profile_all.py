"""H0-H3 profiling. Writes reports/profile/*.md|json; record decisions in
reports/profile/decisions.md and update the TBCs in the docs and data contract.

Checks: row counts vs dictionary, key uniqueness, date ranges, batch_id per table, national_id_hash salt,
employer clusters (>= 10) + payroll-gap share by employer, employment_status values, hardship_programs
rate_override=0 / cards, customer_stated_income_date fill rate, assignment_method + test_cell, future
channel_capacity rows, benchmark mix, cases/month + cure baseline, demo customer candidates.
"""


def main() -> None:
    raise NotImplementedError("TODO(H0): run on data/bronze")


if __name__ == "__main__":
    main()
