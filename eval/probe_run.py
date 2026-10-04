"""Run the 60 probe questions (eval/probe/questions.csv) through Ask under the configured provider and tally
how many are answered, refused, and by whom. Usage: LLM_PROVIDER=openai uv run python -m eval.probe_run [--mode llm]"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from common import llm_mode
from common.ask_scope import use_scope
from nlq.pipeline import ask


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="llm", choices=["llm", "rules"])
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(Path(__file__).parent / "probe" / "questions.csv")))
    out, good, t0 = [], 0, time.time()
    for r in rows:
        with use_scope(None), llm_mode.use_mode(a.mode):
            ans = ask(r["question"])
        ok = r["expect"] == "either" or (r["expect"] == "refuse") == ans.refused
        good += ok
        out.append({"id": r["id"], "question": r["question"], "expect": r["expect"], "refused": ans.refused,
                    "kind": ans.kind, "answered_by": ans.answered_by, "generated": ans.generated, "ok": ok,
                    "citations": len(ans.citations)})
        mark = "ok  " if ok else "BAD "
        print(f"{mark}{r['id']} {ans.kind:12} {ans.answered_by:15} gen={ans.generated!s:5} {r['question'][:70]}")
    by_model = sum(o["answered_by"] == "language model" for o in out)
    print(f"\n{good}/{len(rows)} as expected, {sum(o['generated'] for o in out)} model-written SQL, "
          f"{by_model} by a language model, {time.time() - t0:.0f}s")
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
