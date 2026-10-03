"""Prepare hand-labelling samples (agents prepare, the human labels):
~200 identity pairs (borderline-weighted), 200 hardship snippets (>= 70 positives, sampled by
hardship_mentioned_flag + keywords, NOT the LLM under test), 30 RAG answers."""


def main(kind: str) -> None:
    raise NotImplementedError("TODO(WS-H)")
