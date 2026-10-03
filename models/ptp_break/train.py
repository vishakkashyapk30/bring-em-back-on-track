"""Train LightGBM with monotone constraints (e.g. more late payments never lowers risk)."""

MONOTONE = {"ptp_broken_count_90d": 1, "dpd_max_current": 1, "payroll_delay_days": 1}  # TODO(WS-C)


def main() -> None:
    raise NotImplementedError("TODO(WS-C)")


if __name__ == "__main__":
    main()
