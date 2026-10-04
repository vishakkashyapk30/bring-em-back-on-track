#!/usr/bin/env python3
# ruff: noqa: E501  (layout code with long drawing calls)
"""Draw the final architecture diagram of what the build actually runs: docs/architecture/architecture.{svg,png,pdf}.

Run: python3 docs/architecture/make_diagram.py   (needs google-chrome for the PNG and PDF export)
Colours: sage = rule or code, apricot = model or AI step, straw = a person decides, slate = store, red = CIBC accent.
"""

import html
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
W, H = 1700, 1090
RED, INK, MUTED = "#A71F3E", "#2B2A28", "#6B675F"
FONT = "Inter, Helvetica, Arial, sans-serif"
FILL = {
    "rule": ("#DCE9E0", "#8FB59F"), "ai": ("#F7DFD2", "#D9A68B"), "human": ("#F4ECC8", "#CDBB6B"),
    "store": ("#DEE4EC", "#9DADC2"), "plain": ("#FFFFFF", "#C9C4B8"),
}
out: list[str] = []


def rect(x, y, w, h, kind="plain", rx=10, sw=1.4, dash=None):
    f, s = FILL[kind]
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{f}" stroke="{s}" stroke-width="{sw}"{d}/>')


def text(x, y, s, size=15, weight=400, fill=INK, anchor="start"):
    out.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
               f'text-anchor="{anchor}">{html.escape(s)}</text>')


def node(x, y, w, h, title, sub="", kind="plain"):
    rect(x, y, w, h, kind)
    text(x + 14, y + 22, title, 15.5, 600)
    for i, line in enumerate(sub.split("\n") if sub else []):
        text(x + 14, y + 42 + i * 17, line, 13, 400, MUTED)


def arrow(x1, y1, x2, y2, color=MUTED, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.8"{d} marker-end="url(#a)"/>')


def band(x, y, w, h, label, sub=""):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="#FBFAF7" stroke="#E2DED4" stroke-width="1.3"/>')
    out.append(f'<rect x="{x}" y="{y}" width="8" height="{h}" rx="4" fill="{RED}"/>')
    text(x + 24, y + 30, label, 18, 700, RED)
    if sub:
        text(x + 24 + len(label) * 12.2 + 12, y + 30, sub, 13.5, 400, MUTED)


out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
out.append('<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
           f'<path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker></defs>')
out.append(f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>')
text(40, 42, "back-on-track.ai: architecture of the build", 26, 700, INK)
text(40, 66, "Four layers on the real Maple Bank data, one use case in depth (next best action). Runs with one command: docker compose up --build.",
     14.5, 400, MUTED)

# legend
lx = 1000
for i, (k, lab) in enumerate([("rule", "rules / code"), ("ai", "model / language model"), ("human", "a person decides"), ("store", "store")]):
    off = [0, 120, 320, 470][i]
    rect(lx + off, 28, 16, 16, k, 4)
    text(lx + off + 22, 41, lab, 12.5, 400, MUTED)

# sources
node(40, 86, 1620, 56, "Sources: Maple Bank release, 31 tables from five customer-key systems",
     "CRM, Cards, Lending, Core banking (CIF), Collections  |  contacts, promises, notes (760k), transcripts (25k), bureau, ops events, 19 policy documents", "store")
arrow(850, 142, 850, 170)

# layer 1
band(40, 170, 1620, 156, "LAYER 1  Data product factory", "pipeline/ (dbt + DuckDB), identity/")
xs = [64, 468, 872, 1276]
node(xs[0], 214, 372, 96, "Bronze", "raw Parquet, one file per table,\nlanded in about a minute", "store")
node(xs[1], 214, 372, 96, "Silver: 39 typed models", "dates in three formats, CIF zero padding,\nmistyped CRM IDs repaired", "rule")
node(xs[2], 214, 372, 96, "Identity resolution", "exact keys, scored matching (99.96% precise),\nsteward review queue for the unsure", "rule")
node(xs[3], 214, 360, 96, "Gold C360 (the hub)", "1,001,072 golden customers, match confidence,\n11 contract tests, atomic publish", "store")
for a in range(3):
    arrow(xs[a] + 372 if a < 3 else 0, 262, xs[a + 1] - 2, 262)

# columns
CY = 372
band(40, CY, 530, 490, "LAYER 2  Insight and NLP", "Ask")
band(594, CY, 490, 490, "LAYER 3  Feature store", "features/")
band(1108, CY, 552, 490, "LAYER 4  Next best action", "decisioning/, models/")
for cx in (305, 839, 1384):
    arrow(cx, 326, cx, CY + 2)

# layer 2 nodes
y = CY + 46
l2 = [
    ("Refusal rules", "personal data, protected traits, marketing, writes, forecasts", "rule"),
    ("Certified metric compiler", "25 metrics, breakdowns, filters, periods; SQL shown", "rule"),
    ("Optional language model", "picks a metric from a closed list; words policy\nanswers from quoted sections; offline by default", "ai"),
    ("SQL guard", "read-only, allowlist, role row filters, groups under 10 hidden", "rule"),
    ("Policy retrieval", "BM25, authority precedence, no citation means no answer", "rule"),
    ("Answer", "numbers + the SQL or sources + caveats, or a refusal", "plain"),
]
heights = [56, 56, 70, 56, 56, 56]
for (t, s, k), h in zip(l2, heights, strict=True):
    node(60, y, 490, h, t, s, k)
    y += h + 10

# layer 3 nodes
y = CY + 46
l3 = [
    ("Registry: one definition per feature", "70 features with owner, source, refresh, version", "rule", 62),
    ("SQL features", "contact, promise, bureau, salary, card, account history", "rule", 56),
    ("Text and voice features", "hardship, dispute, complaint, delay reason from notes, transcripts\nand recordings (speech to text); no speaker acoustics", "rule", 72),
    ("Offline (training) and online (live)", "one dbt macro, evaluated as of the promise\nor as of now; parity check: 0 mismatches in 1,000", "store", 72),
    ("Fairness inputs", "no protected attribute reaches a feature", "rule", 56),
]
for t, s, k, h in l3:
    node(614, y, 450, h, t, s, k)
    y += h + 10

# layer 4 nodes
y = CY + 46
l4 = [
    ("1  Policy gate (before any model)", "consent, hours, Sundays, holidays, do-not-call, 7-day cap,\ncease, insolvency, dispute, hardship latch", "rule", 68),
    ("2  Promise-break risk", "LightGBM + bank v2.1 blend, AUC 0.772 vs 0.694,\nSHAP reason codes", "ai", 66),
    ("3  Treatment ladder, 4  Capacity allocator", "first match wins; priority = risk x capped amount - cost;\nchannel and agent capacity", "rule", 66),
    ("5  Plain-English explanation", "rules applied, model estimate, what changed, freshness, alternatives", "rule", 52),
    ("6  A person reviews", "agent approves, edits or overrides (reason needed);\nteam lead approves batches; specialist confirms hardship", "human", 66),
    ("Hardship workbench", "plan simulator, review board, missed offers, override audit", "human", 52),
]
for t, s, k, h in l4:
    node(1128, y, 512, h, t, s, k)
    y += h + 8

# arrows between columns
arrow(1064, 596, 1128, 596, MUTED)

# governance band
band(40, 884, 1620, 176, "GOVERNANCE", "across every layer")
gov = [
    ("Audit log", "append-only (SQLite triggers);\nevery customer-affecting write"),
    ("Hardship latch", "raised by rules or agents,\nlowered only by a person with a reason"),
    ("Fairness audit", "proxy test (above 0.65 a group is dropped\nand reviewed); outcome tests by group"),
    ("Protected attributes", "kept out of features, rules, prompts\nand models; one auditor view reads them"),
    ("Monitoring and contract", "model evaluation, data quality report,\nfreshness rule 11, benchmark 0.994 (dev)"),
]
for i, (t, s) in enumerate(gov):
    node(64 + i * 318, 920, 304, 110, t, s, "rule" if i != 0 else "store")

out.append("</svg>")
svg = HERE / "architecture.svg"
svg.write_text("\n".join(out), encoding="utf-8")
page = HERE / "_page.html"
page.write_text(f'<!doctype html><html><head><meta charset="utf-8"><style>@page{{size:{W}px {H}px;margin:0}}'
                f'html,body{{margin:0;padding:0;background:#fff}}</style></head><body>{svg.read_text()}</body></html>')
chrome = ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars"]
subprocess.run([*chrome, f"--screenshot={HERE / 'architecture.png'}", f"--window-size={W},{H}", page.as_uri()], check=True,
               capture_output=True)
subprocess.run([*chrome, f"--print-to-pdf={HERE / 'architecture.pdf'}", "--no-pdf-header-footer", page.as_uri()], check=True,
               capture_output=True)
page.unlink()
print("wrote", [p.name for p in sorted(HERE.glob("architecture.*"))])
