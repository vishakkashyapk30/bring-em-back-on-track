"""Accuracy of the offline transcript extractor against the release's 500 public transcript labels.
Run: python -m eval.eval_text_rules  -> prints per-field accuracy and writes reports/text_rules_eval.json"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date

from common.config import get_settings
from features.text_rules import extract, summary

R = get_settings().release_dir


def load_ptps() -> dict[str, dict]:
    out = {}
    with open(R / "data" / "promises_to_pay.csv") as f:
        for r in csv.DictReader(f):
            if r["contact_id"]:
                out[r["contact_id"]] = {"amount": r["ptp_amount"], "date": r["ptp_due_date"]}
    return out


def main() -> None:
    labels = list(csv.DictReader(open(R / "labels" / "call_transcripts_labels_public_500.csv")))
    meta = {r["transcript_id"]: r for r in csv.DictReader(open(R / "data" / "call_transcripts.csv"))}
    ptps = load_ptps()
    hits, n = Counter(), 0
    misses = []
    for lab in labels:
        m = meta[lab["transcript_id"]]
        d = json.load(open(R / "files" / m["file_path"]))
        call_date = date.fromisoformat(m["call_start_ts"][:10])
        f = extract(d["turns"], call_date, ptps.get(m["contact_id"]))
        n += 1
        hits["hardship"] += f["hardship"] == lab["label_hardship"]
        hits["hardship_reason"] += (f["hardship_reason"] or "") == lab["label_hardship_reason"]
        hits["dispute"] += str(f["dispute"]).lower() == lab["label_dispute"]
        hits["complaint"] += str(f["complaint"]).lower() == lab["label_complaint"]
        hits["cease_request"] += str(f["cease_request"]).lower() == lab["label_cease_request"]
        hits["next_step"] += f["next_step"] == lab["label_next_step"]
        hits["ptp_mentioned"] += str(f["ptp"] is not None).lower() == lab["label_ptp_mentioned"]
        hits["stated_delay_reason"] += (f["stated_delay_reason"] or "") == lab["label_stated_delay_reason"]
        want = lab["label_ptp_intent_strength"]
        hits["ptp_intent_strength"] += (f["ptp_intent_strength"] is None and want == "") or (
            f["ptp_intent_strength"] is not None and want != "" and abs(f["ptp_intent_strength"] - float(want)) < 1e-6)
        s = summary(f)
        ok = s.lower() == lab["label_summary_gold"].lower()
        hits["summary_exact"] += ok
        if not ok and len(misses) < 12:
            misses.append({"id": lab["transcript_id"], "ours": s, "gold": lab["label_summary_gold"]})
        rec = lab["label_hardship"] != "none"
        hits["hardship_tp"] += rec and f["hardship"] != "none"
        hits["hardship_pos"] += rec
    acc = {k: round(v / n, 3) for k, v in hits.items() if k not in ("hardship_tp", "hardship_pos")}
    acc["hardship_recall"] = round(hits["hardship_tp"] / max(hits["hardship_pos"], 1), 3)
    print(json.dumps(acc, indent=2))
    for mm in misses:
        print(mm)
    out = get_settings().reports_dir / "text_rules_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"n": n, "accuracy": acc, "sample_misses": misses}, indent=2))


if __name__ == "__main__":
    main()
