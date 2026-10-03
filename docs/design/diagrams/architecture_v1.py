#!/usr/bin/env python3
"""Generate the one-page architecture diagram (architecture_v1.svg / .pdf / .png).

Hand-laid out so every layer, tool, AI step and human review point has a fixed place:
  - Layer 1 across the top, ending in the Gold C360 "hub" bar
  - Layers 2, 3 and 4 hang off the hub, left to right
  - Layer 4 has three lanes (use case 1, 2, 3)
  - Governance band across the bottom

Run:  python3 architecture_v1.py
Needs Chrome (puppeteer's chrome-headless-shell) for the PDF/PNG export and the layout self-check.
"""
import glob
import html
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
W, H = 1700, 1038
FONT = "Cabin, Lato, Arial, sans-serif"
FS_T = 18.5    # node title
FS_S = 14.5    # node sub-line
BG = "#FFFFFF"
INK = "#34332F"
MUTED = "#6D6A62"
NOVEL = "#8C6F8E"   # dusty plum outline for novel capabilities

# light, low-contrast fills with a slightly darker hairline of the same hue
COL = {
    "ai":    dict(fill="#F7DFD2", stroke="#DCAF97", sw=1.3),   # apricot
    "human": dict(fill="#F4ECC8", stroke="#D3C47F", sw=1.3),   # straw
    "rule":  dict(fill="#DCE9E0", stroke="#98BBA6", sw=1.3),   # sage
    "store": dict(fill="#DEE4EC", stroke="#9DADC2", sw=1.3),   # slate
    "plain": dict(fill="#FFFFFF", stroke="#CFCABF", sw=1.3),
}

nodes = {}   # id -> dict
edges = []
panels = []
texts = []   # free text labels


def node(id, kind, x, y, w, h, lines, shape=None, dashed=False, bold_first=True, badge=None):
    nodes[id] = dict(id=id, kind=kind, x=x, y=y, w=w, h=h, lines=lines,
                     shape=shape or ("cyl" if kind == "store" else "rect"),
                     dashed=dashed, bold_first=bold_first, badge=badge)


def panel(x, y, w, h, title, tools, num=None, fill="#F4F2EB", stroke="#E4E0D3"):
    panels.append(dict(x=x, y=y, w=w, h=h, title=title, tools=tools, fill=fill, stroke=stroke, num=num))


def label(x, y, s, anchor="start", size=14, color="#5A564C", bold=False, rot=None):
    texts.append(dict(x=x, y=y, s=s, anchor=anchor, size=size, color=color, bold=bold, rot=rot))


def edge(pts, frm=None, to=None, dotted=False, both=False, color="#3D3A33", width=1.9, arrow=True):
    edges.append(dict(pts=pts, frm=frm, to=to, dotted=dotted, both=both, color=color, width=width, arrow=arrow))


def cx(n):
    return nodes[n]["x"] + nodes[n]["w"] / 2


def cy(n):
    return nodes[n]["y"] + nodes[n]["h"] / 2


def L(n):  # left middle
    return (nodes[n]["x"], cy(n))


def R(n):
    return (nodes[n]["x"] + nodes[n]["w"], cy(n))


def T(n, dx=0):
    return (cx(n) + dx, nodes[n]["y"])


def B(n, dx=0):
    return (cx(n) + dx, nodes[n]["y"] + nodes[n]["h"])


# ------------------------------------------------------------------ legend
LEG_Y = 4

# ------------------------------------------------------------------ Layer 1 (top)
P1_Y, P1_H = 34, 272
panel(8, P1_Y, 1684, P1_H, "Data Product Factory", "DuckDB · dbt · Splink · Claude", num="1")

R1Y, R1H = 86, 66
node("src", "store", 20, R1Y, 320, R1H, ["31 source tables", "cards · loans · deposits · CRM"])
node("bronze", "plain", 410, R1Y, 170, R1H, ["Raw files", "kept as received"])
node("silver", "plain", 640, R1Y, 230, R1H, ["Cleaned records", "current rows, fixed types"])
node("ident", "plain", 930, R1Y, 270, R1H, ["Identity match", "customers + employers"])
node("adj", "ai", 1270, R1Y, 200, R1H, ["LLM adjudicator"])
node("stew", "human", 1520, R1Y, 160, R1H, ["Data steward"])
edge([R("src"), L("bronze")], "src", "bronze")
edge([R("bronze"), L("silver")], "bronze", "silver")
edge([R("silver"), L("ident")], "silver", "ident")
edge([R("ident"), L("adj")], "ident", "adj")
edge([R("adj"), L("stew")], "adj", "stew")
label(1235, R1Y + R1H / 2 - 8, "unsure", anchor="middle", size=13)
label(1235, R1Y + R1H / 2 + 24, "pairs", anchor="middle", size=13)

R2Y, R2H = 180, 46
node("tele", "rule", 20, R2Y, 370, R2H, ["Data-health watch"], badge="S3")
node("map", "ai", 410, R2Y, 190, R2H, ["Mapping fixes"])
node("eng", "human", 640, R2Y, 230, R2H, ["Engineer reviews"])
node("dq", "rule", 1270, R2Y, 200, R2H, ["Quality gate"])
edge([T("tele", -100), (cx("tele") - 100, R1Y + R1H)], "tele", "src", dotted=True)
edge([R("map"), L("eng")], "map", "eng")
edge([T("eng"), B("silver")], "eng", "silver")

GOLD_Y, GOLD_H = 258, 38
node("gold", "store", 20, GOLD_Y, 1660, GOLD_H, ["Gold C360: one trusted view of every customer"], shape="bar")
edge([B("ident", 0), (cx("ident"), GOLD_Y)], "ident", "gold")
label(cx("ident") + 10, 210, "confident match", size=13)
edge([B("stew"), (cx("stew"), GOLD_Y)], "stew", "gold")
label(cx("stew") - 10, 210, "confirmed", anchor="end", size=13)
edge([B("dq"), (cx("dq"), GOLD_Y)], "dq", "gold", dotted=True)

# ------------------------------------------------------------------ Row C panels
RC_Y, RC_H = 350, 680
P2X, P2W = 8, 350
P3X, P3W = 374, 440
P4X, P4W = 830, 862
panel(P2X, RC_Y, P2W, RC_H, "Insight and NLP", "MetricFlow · sqlglot · Claude · LanceDB", num="2")
panel(P3X, RC_Y, P3W, RC_H, "Feature Store", "dbt · Parquet · DuckDB", num="3")
panel(P4X, RC_Y, P4W, RC_H, "Models and Decisioning", "LightGBM · TreeSHAP · EconML · Claude · Streamlit", num="4")
HUB_B = P1_Y + P1_H
edge([(183, HUB_B), (183, RC_Y)])
label(191, 336, "read-only", size=13)
edge([(594, HUB_B), (594, RC_Y)])
label(602, 336, "tables + text", size=13)
edge([(950, HUB_B), (950, RC_Y)])
label(958, 336, "customer context", size=13)
edge([(1620, RC_Y), (1620, HUB_B)])
label(1610, 336, "decisions + audit written back", anchor="end", size=13)

# ------------------------------------------------------------------ Layer 2
LX, LW = 22, 322
node("tok", "ai", LX, 418, 180, 52, ["Parse question"])
node("chip", "human", 214, 418, 130, 52, ["Analyst edits"])
node("allow", "rule", LX, 498, LW, 48, ["Role allowlist"])
node("sem", "plain", LX, 576, 150, 48, ["Semantic layer"])
node("val", "rule", LX, 650, 150, 48, ["SQL guard"])
node("pre", "rule", LX, 724, 150, 48, ["Pre-flight"], badge="S5")
node("rag", "ai", 194, 576, 150, 196, ["RAG search", "policies + notes"])
node("ans", "plain", LX, 800, LW, 52, ["Answer or refusal", "SQL and sources shown"])
node("viewA", "plain", LX, 880, LW, 52, ["Analyst views", "map · radar · scorecard"], badge="S1 S2 S4 S6")
node("viewB", "plain", LX, 956, LW, 52, ["Hardship views", "offers · review board"], badge="H2 H3")
edge([B("tok"), (cx("tok"), 498)], "tok", "allow")
edge([R("tok"), L("chip")], "tok", "chip", both=True)
edge([(cx("sem"), 546), T("sem")], "allow", "sem")
edge([(cx("rag"), 546), T("rag")], "allow", "rag")
edge([B("sem"), T("val")], "sem", "val")
edge([B("val"), T("pre")], "val", "pre")
edge([B("pre"), (cx("pre"), 800)], "pre", "ans")
edge([B("rag"), (cx("rag"), 800)], "rag", "ans")
edge([L("allow"), (14, cy("allow")), (14, cy("ans")), L("ans")], "allow", "ans")
edge([B("ans"), T("viewA")], "ans", "viewA", dotted=True)
edge([B("viewA"), T("viewB")], "viewA", "viewB", dotted=True)

# ------------------------------------------------------------------ Layer 3
AX, AW = 388, 196
BX, BW = 606, 194
node("reg", "plain", AX, 418, AW, 52, ["Feature registry"])
node("sqlf", "plain", AX, 498, AW, 106, ["Features", "payday · employer", "stress · friction"])
node("ext", "ai", BX, 418, BW, 52, ["Text features"])
node("hum3", "human", BX, 498, BW, 52, ["Agent approves"])
node("gate4", "rule", AX, 650, 412, 56, ["Proxy gate", "no stand-ins for protected traits"], badge="H4")
node("off", "store", AX, 752, AW, 72, ["Offline store"])
node("on", "store", BX, 752, BW, 72, ["Online store"])
node("par", "rule", AX, 870, 412, 48, ["Nightly parity check"])
edge([B("reg"), T("sqlf")], "reg", "sqlf", dotted=True)
edge([B("sqlf"), (cx("sqlf"), 650)], "sqlf", "gate4")
edge([B("ext"), T("hum3")], "ext", "hum3")
edge([B("hum3"), (cx("hum3"), 650)], "hum3", "gate4")
label(cx("hum3") + 10, 630, "approved only", size=13)
edge([(cx("off"), 706), T("off")], "gate4", "off")
edge([R("off"), L("on")], "off", "on")
edge([(cx("on"), 870), B("on")], "par", "on", dotted=True)
edge([(cx("off"), 870), B("off")], "par", "off", dotted=True)
BUSX = 822

# ------------------------------------------------------------------ Layer 4
C = [854, 1064, 1274, 1484]
CW = 186


def lane(y, h, title):
    panels.append(dict(x=842, y=y, w=838, h=h, title=None, tools=None, fill="#FCFBF8", stroke="#E4E0D3", lane=title))


U1Y, U1H = 392, 204
lane(U1Y, U1H, "Next Best Action  (main use case)")
r1, r2, rh = 430, 524, 56
node("feat", "store", C[0], r1, CW, rh, ["Features"])
node("model", "ai", C[1], r1, CW, rh, ["Break-risk model"])
node("uplift", "ai", C[2], r1, CW, rh, ["Uplift, phase 2"], dashed=True)
node("hnba", "human", C[3], r1, CW, rh, ["Agent decides"])
node("ctx", "store", C[0], r2, CW, rh, ["Case context"])
node("gate", "rule", C[1], r2, CW, rh, ["Policy gate"])
node("lad", "rule", C[2], r2, CW, rh, ["Treatment ladder", "payday-aware"], badge="A1")
node("expl", "rule", C[3], r2, CW, rh, ["Explanation", "reasons + what-if"], badge="A2")
edge([R("feat"), L("model")], "feat", "model")
edge([R("ctx"), L("gate")], "ctx", "gate")
edge([R("gate"), L("lad")], "gate", "lad")
edge([R("lad"), L("expl")], "lad", "expl")
edge([T("expl"), B("hnba")], "expl", "hnba")
edge([B("model"), (cx("model"), r1 + rh + 19), (cx("lad") - 40, r1 + rh + 19), (cx("lad") - 40, r2)], "model", "lad")
edge([B("uplift", 40), (cx("uplift") + 40, r2)], "uplift", "lad", dotted=True)

U4Y, U4H = 614, 110
lane(U4Y, U4H, "Team-lead playbooks")
t = 654
th = 54
node("coh", "store", C[0], t, CW, th, ["Cohort features"])
node("rad", "rule", C[1], t, CW, th, ["Employer radar"], badge="S1 H5")
node("play", "rule", C[2], t, CW, th, ["Batch playbook"])
node("htl", "human", C[3], t, CW, th, ["Team lead approves"])
edge([R("coh"), L("rad")], "coh", "rad")
edge([R("rad"), L("play")], "rad", "play")
edge([R("play"), L("htl")], "play", "htl")

U2Y, U2H = 742, 110
lane(U2Y, U2H, "Post-call summary")
u2, u2h = 782, 54
node("tr", "store", C[0], u2, CW, u2h, ["Call transcript"])
node("draft", "ai", C[1], u2, CW, u2h, ["Summary draft"])
node("chk", "rule", C[2], u2, CW, u2h, ["Schema check"])
node("hsum", "human", C[3], u2, CW, u2h, ["Agent approves"])
edge([R("tr"), L("draft")], "tr", "draft")
edge([R("draft"), L("chk")], "draft", "chk")
edge([R("chk"), L("hsum")], "chk", "hsum")

U3Y, U3H = 870, 152
lane(U3Y, U3H, "Agent assist + hardship workbench")
a1, ah = 908, 44
a2, ah2 = 964, 44
node("aq", "plain", C[0], a1, CW, ah, ["Agent question"])
node("arag", "ai", C[1], a1, 396, ah, ["Policy answer"])
node("c360v", "store", C[0], a2, CW, ah2, ["Customer values"])
node("elig", "rule", C[1], a2, CW, ah2, ["Eligibility rules"])
node("sim", "rule", C[2], a2, CW, ah2, ["Plan simulator"], badge="H1")
node("hast", "human", C[3], a1, CW, a2 + ah2 - a1, ["Person decides", "approver signs off"])
edge([R("aq"), L("arag")], "aq", "arag")
edge([R("arag"), (1470, cy("arag")), (1470, cy("hast") - 20), (C[3], cy("hast") - 20)], "arag", "hast")
edge([R("c360v"), L("elig")], "c360v", "elig")
edge([R("elig"), L("sim")], "elig", "sim")
edge([R("sim"), (1470, cy("sim")), (C[3], cy("sim"))], "sim", "hast")

# L3 -> L4 bus in the gutter: one unbroken vertical line with an arrow branching off to each target
edge([R("on"), (BUSX, cy("on"))], "on", None, arrow=False)
edge([(BUSX, cy("feat")), (BUSX, cy("tr"))], None, None, arrow=False)
edge([(BUSX, cy("feat")), L("feat")], None, "feat")
edge([(BUSX, cy("coh")), L("coh")], None, "coh")
edge([(BUSX, cy("tr")), L("tr")], None, "tr")


# ------------------------------------------------------------------ SVG rendering
def esc(s):
    return html.escape(s, quote=False)


def tag(n):
    """Capability ID, small and muted, in the node's top-right corner."""
    return (f'<text x="{n["x"] + n["w"] - 9}" y="{n["y"] + 14}" text-anchor="end" font-size="11.5" font-weight="700" '
            f'letter-spacing="0.5" fill="{MUTED}">{esc(n["badge"])}</text>')


def render_node(n):
    k = COL[n["kind"]]
    x, y, w, h = n["x"], n["y"], n["w"], n["h"]
    dash = ' stroke-dasharray="6 5"' if n["dashed"] else ""
    if n.get("badge"):
        stroke = f' stroke="{NOVEL}" stroke-width="2.8"'
    else:
        stroke = f' stroke="{k["stroke"]}" stroke-width="{k["sw"]}"'
    out = []
    if n["shape"] == "cyl":
        e = 8
        d = (f"M{x},{y+e} A{w/2},{e} 0 0 1 {x+w},{y+e} V{y+h-e} A{w/2},{e} 0 0 1 {x},{y+h-e} Z")
        out.append(f'<path d="{d}" fill="{k["fill"]}"{stroke}{dash}/>')
        out.append(f'<path d="M{x},{y+e} A{w/2},{e} 0 0 0 {x+w},{y+e}" fill="none"{stroke}/>')
        ty0, ty1 = y + e, y + h
    elif n["shape"] == "bar":
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2}" fill="{k["fill"]}"{stroke}/>')
        ty0, ty1 = y, y + h
    else:
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{k["fill"]}"{stroke}{dash}/>')
        ty0, ty1 = y, y + h
    lines = n["lines"]
    if n["shape"] == "bar":
        out.append(f'<text data-node="{n["id"]}" x="{x+w/2}" y="{y+h/2+6.5}" text-anchor="middle" font-size="19" font-weight="600" '
                   f'fill="{INK}" letter-spacing="0.3">{esc(lines[0])}</text>')
        return "\n".join(out)
    offs = [0] + [21 + 18 * i for i in range(len(lines) - 1)]
    total = offs[-1] + 22
    first = (ty0 + ty1) / 2 - total / 2 + 18
    for i, s in enumerate(lines):
        title = i == 0
        size = FS_T if title else FS_S
        out.append(f'<text data-node="{n["id"]}" x="{x+w/2}" y="{first + offs[i]:.1f}" text-anchor="middle" '
                   f'font-size="{size}" font-weight="{600 if title else 400}" fill="{INK if title else MUTED}">{esc(s)}</text>')
    if n.get("badge"):
        out.append(tag(n))
    return "\n".join(out)


def render():
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">',
         '<defs>'
         '<marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0,0 L10,5 L0,10 z" fill="#3D3A33"/></marker></defs>',
         f'<rect width="{W}" height="{H}" fill="{BG}"/>']
    # legend
    lx = 12
    items = [("ai", "AI step"), ("human", "A person decides"), ("rule", "Plain rules"), ("store", "Data")]
    for kind, txt in items:
        k = COL[kind]
        o.append(f'<rect x="{lx}" y="{LEG_Y+2}" width="22" height="15" rx="4" fill="{k["fill"]}" stroke="{k["stroke"]}" stroke-width="1.3"/>')
        o.append(f'<text x="{lx+30}" y="{LEG_Y+15}" font-size="14.5" fill="{MUTED}">{esc(txt)}</text>')
        lx += 30 + len(txt) * 7.2 + 30
    o.append(f'<line x1="{lx}" y1="{LEG_Y+10}" x2="{lx+30}" y2="{LEG_Y+10}" stroke="#3D3A33" stroke-width="1.6" stroke-dasharray="3 4"/>')
    o.append(f'<text x="{lx+38}" y="{LEG_Y+15}" font-size="14.5" fill="{MUTED}">Optional or check</text>')
    # panels
    for p in panels:
        if p.get("lane"):
            o.append(f'<rect x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}" rx="12" fill="{p["fill"]}" '
                     f'stroke="{p["stroke"]}" stroke-width="1.2"/>')
            o.append(f'<text class="lbl" x="{p["x"]+16}" y="{p["y"]+23}" font-size="14.5" font-weight="600" letter-spacing="0.4" '
                     f'fill="{MUTED}">{esc(p["lane"])}</text>')
            continue
        o.append(f'<rect x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}" rx="16" fill="{p["fill"]}" '
                 f'stroke="{p["stroke"]}" stroke-width="1.2"/>')
        if p["title"]:
            o.append(f'<text class="lbl" x="{p["x"]+20}" y="{p["y"]+32}" font-size="24" font-weight="600" fill="{INK}">'
                     f'<tspan fill="#B3AD9C">{p["num"]}</tspan>   {esc(p["title"])}</text>')
            if p["w"] > 800:   # wide panel: tools on the title line
                tx, ty = p["x"] + 60 + len(p["title"]) * 11.6 + 20, p["y"] + 32
            else:
                tx, ty = p["x"] + 52, p["y"] + 54
            o.append(f'<text class="lbl" x="{tx:.0f}" y="{ty}" font-size="14.5" font-weight="700" fill="#4F4B42">{esc(p["tools"])}</text>')
    # edges (under nodes)
    for e in edges:
        pts = " ".join(f"{px:.1f},{py:.1f}" for px, py in e["pts"])
        dash = ' stroke-dasharray="3 5"' if e["dotted"] else ""
        start = ' marker-start="url(#ah)"' if e["both"] else ""
        end = ' marker-end="url(#ah)"' if e.get("arrow", True) else ""
        o.append(f'<polyline points="{pts}" fill="none" stroke="{e["color"]}" stroke-width="{e["width"]}"{dash}{start} '
                 f'{end} stroke-linejoin="round" stroke-linecap="round"/>')
    for n in nodes.values():
        o.append(render_node(n))
    for t in texts:
        rot = f' transform="rotate({t["rot"]} {t["x"]} {t["y"]})"' if t["rot"] else ""
        o.append(f'<text class="lbl" x="{t["x"]}" y="{t["y"]}" font-size="{t["size"]}" text-anchor="{t["anchor"]}" '
                 f'font-weight="400" fill="{t["color"]}"{rot}>{esc(t["s"])}</text>')
    o.append('</svg>')
    return "\n".join(o)


# ------------------------------------------------------------------ static checks
def seg_hits_rect(p, q, r, pad=2):
    x0, y0, x1, y1 = r["x"] - pad, r["y"] - pad, r["x"] + r["w"] + pad, r["y"] + r["h"] + pad
    (ax, ay), (bx, by) = p, q
    if ax == bx:  # vertical
        return x0 < ax < x1 and max(min(ay, by), y0) < min(max(ay, by), y1)
    if ay == by:  # horizontal
        return y0 < ay < y1 and max(min(ax, bx), x0) < min(max(ax, bx), x1)
    raise ValueError(f"diagonal segment {p}->{q}")


def check_static():
    problems = []
    ids = [n for n in nodes if not n.startswith("gov")]
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            A, B_ = nodes[a], nodes[b]
            if A["x"] < B_["x"] + B_["w"] and B_["x"] < A["x"] + A["w"] and A["y"] < B_["y"] + B_["h"] and B_["y"] < A["y"] + A["h"]:
                problems.append(f"nodes overlap: {a} / {b}")
    for e in edges:
        for p, q in zip(e["pts"], e["pts"][1:]):
            try:
                for nid in ids:
                    if nid in (e["frm"], e["to"]):
                        continue
                    if seg_hits_rect(p, q, nodes[nid]):
                        problems.append(f"edge {e['frm']}->{e['to']} crosses node {nid}")
            except ValueError as ex:
                problems.append(str(ex))
    # nodes inside the canvas
    for n in nodes.values():
        if n["x"] < 0 or n["y"] < 0 or n["x"] + n["w"] > W or n["y"] + n["h"] > H:
            problems.append(f"node outside canvas: {n['id']}")
    return problems


def chrome():
    for pat in ("~/.cache/puppeteer/chrome-headless-shell/*/chrome-headless-shell-linux64/chrome-headless-shell",
                "~/.cache/puppeteer/chrome/*/chrome-linux64/chrome"):
        g = glob.glob(os.path.expanduser(pat))
        if g:
            return g[0]
    return None


CHECK_JS = """
<script>
window.addEventListener('load', () => {
  const nodes = {};
  document.querySelectorAll('text[data-node]').forEach(t => {
    const id = t.getAttribute('data-node');
    const b = t.getBBox();
    const o = nodes[id] || (nodes[id] = {x0: 1e9, y0: 1e9, x1: -1e9, y1: -1e9});
    o.x0 = Math.min(o.x0, b.x); o.y0 = Math.min(o.y0, b.y);
    o.x1 = Math.max(o.x1, b.x + b.width); o.y1 = Math.max(o.y1, b.y + b.height);
  });
  const out = [];
  const shapes = JSON.parse(document.getElementById('geom').textContent);
  for (const [id, g] of Object.entries(shapes)) {
    const o = nodes[id]; if (!o) continue;
    const pad = 5;
    if (o.x0 < g.x + pad || o.x1 > g.x + g.w - pad || o.y0 < g.y + 1 || o.y1 > g.y + g.h - 1)
      out.push(id + ' text overflows: text[' + [o.x0, o.y0, o.x1, o.y1].map(v => Math.round(v)) + '] box[' + [g.x, g.y, g.x + g.w, g.y + g.h] + ']');
  }

  const edges = JSON.parse(document.getElementById('edges').textContent);
  document.querySelectorAll('text.lbl').forEach(t => {
    const b = t.getBBox(); const txt = t.textContent.slice(0, 30);
    for (const [id, g] of Object.entries(shapes)) {
      if (b.x < g.x + g.w && g.x < b.x + b.width && b.y < g.y + g.h && g.y < b.y + b.height)
        out.push('label "' + txt + '" overlaps node ' + id);
    }
    for (const pts of edges) for (let i = 0; i + 1 < pts.length; i++) {
      const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
      const x0 = Math.min(ax, bx), x1 = Math.max(ax, bx), y0 = Math.min(ay, by), y1 = Math.max(ay, by);
      if (x0 <= b.x + b.width && x1 >= b.x && y0 <= b.y + b.height && y1 >= b.y)
        out.push('label "' + txt + '" touches an edge at ' + [ax, ay, bx, by]);
    }
  });
  const pre = document.createElement('pre'); pre.id = 'result'; pre.textContent = 'RESULT:' + JSON.stringify(out);
  document.body.appendChild(pre);
});
</script>
"""


def main():
    svg = render()
    (HERE / "architecture_v1.svg").write_text(svg)
    problems = check_static()
    geom = {k: dict(x=v["x"], y=v["y"], w=v["w"], h=v["h"]) for k, v in nodes.items()}
    page = (f'<!doctype html><html><head><meta charset="utf-8"><style>@page{{size:{W}px {H}px;margin:0}}'
            f'html,body{{margin:0;padding:0;background:#fff}}svg{{display:block}}@media print{{pre{{display:none}}}}</style></head><body>{svg}'
            f'<script type="application/json" id="geom">{json.dumps(geom)}</script>'
            f'<script type="application/json" id="edges">{json.dumps([e["pts"] for e in edges])}</script>{CHECK_JS}</body></html>')
    (HERE / "_architecture_v1.html").write_text(page)
    ch = chrome()
    if not ch:
        print("Chrome not found: wrote SVG only")
        return 1
    flags = ["--no-sandbox", "--disable-gpu", "--hide-scrollbars"]
    url = f"file://{HERE}/_architecture_v1.html"
    dom = subprocess.run([ch, *flags, "--dump-dom", url], capture_output=True, text=True, timeout=120).stdout
    marker = 'id="result">RESULT:'
    if marker in dom:
        res = dom.split(marker)[1].split("</pre>")[0]
        problems += json.loads(res.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))
    else:
        problems.append("browser self-check did not run")
    subprocess.run([ch, *flags, "--no-pdf-header-footer", f"--print-to-pdf={HERE}/architecture_v1.pdf", url],
                   capture_output=True, timeout=120)
    subprocess.run([ch, *flags, f"--window-size={W},{H}", "--force-device-scale-factor=2",
                    f"--screenshot={HERE}/architecture_v1.png", url], capture_output=True, timeout=120)
    (HERE / "_architecture_v1.html").unlink()
    if problems:
        print("LAYOUT PROBLEMS:")
        for p in problems:
            print(" -", p)
        return 2
    print("layout OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
