"""NBA orchestration: open cases -> gate -> risk -> ladder -> allocator -> explanation.
Nightly queue (`make score`) and event re-score (< 5 min after call/payment/broken PTP/hardship raise)."""


def build_queue(date: str) -> list:
    raise NotImplementedError("TODO(WS-D)")


def propose(case_id: str):
    raise NotImplementedError("TODO(WS-D)")
