"""Relative and absolute time phrases -> date ranges, anchored on the question's as_of_date (default: the
snapshot date 2026-09-28). Ranges are inclusive dates; `end` never goes past as_of."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"], 1)}
MON = "(" + "|".join(list(MONTHS) + [m[:3] for m in MONTHS] + ["sept"]) + ")"


@dataclass
class TimeRange:
    start: date | None
    end: date | None
    label: str
    previous: TimeRange | None = None   # for "compared with the N days before"


def _month(name: str) -> int:
    name = name.lower()
    return MONTHS.get(name) or next(v for k, v in MONTHS.items() if k.startswith(name[:3]))


def _month_end(y: int, m: int) -> date:
    return (date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1))


def parse(q: str, as_of: date) -> TimeRange | None:
    t = q.lower()

    def clip(d: date) -> date:
        return min(d, as_of)

    # between 10 Sep and 20 Sep 2026 (each end names its month; the year may follow either or only the second)
    m = re.search(rf"between (\d{{1,2}}) {MON}\w*(?: (\d{{4}}))? and (\d{{1,2}}) {MON}\w* (\d{{4}})", t)
    if m:
        y2 = int(m.group(6))
        start = date(int(m.group(3) or y2), _month(m.group(2)), int(m.group(1)))
        end = date(y2, _month(m.group(5)), int(m.group(4)))
        return TimeRange(start, clip(end), f"{start.day} {start:%b}-{end.day} {end:%b}")
    # between 15 and 22 September 2026 [compared with the 8 days before]
    m = re.search(rf"between (\d{{1,2}}) and (\d{{1,2}}) {MON}\w* (\d{{4}})", t)
    if m:
        mo, y = _month(m.group(3)), int(m.group(4))
        start, end = date(y, mo, int(m.group(1))), date(y, mo, int(m.group(2)))
        tr = TimeRange(start, end, f"{start.day}-{end.day} {end:%b}")
        pm = re.search(r"(\d+) days before", t)
        if pm or "before" in t or "previous" in t:
            n = int(pm.group(1)) if pm else (end - start).days + 1
            ps, pe = start - timedelta(days=n), start - timedelta(days=1)
            label = f"{ps.day}-{pe.day} {pe:%b}" if ps.month == pe.month else f"{ps.day} {ps:%b}-{pe.day} {pe:%b}"
            tr.previous = TimeRange(ps, pe, label)
        return tr
    # two named months compared: "June 2026 with May 2026", "June versus May 2026"
    if re.search(r"compar|versus|\bvs\b|\bwith\b.*\b20\d\d", t):
        found = re.findall(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)"
                           r"(?: (20\d\d))?", t)
        if len(found) >= 2 and found[0][0] != found[1][0]:
            y2 = int(next((y for _, y in reversed(found) if y), as_of.year))
            y1 = int(found[0][1] or y2)

            def span(name: str, y: int) -> TimeRange:
                mo = _month(name)
                return TimeRange(date(y, mo, 1), clip(_month_end(y, mo)), f"{name.title()} {y}")

            cur = span(found[0][0], y1)
            cur.previous = span(found[1][0], int(found[1][1] or y2))
            return cur
    # July-September 2026 / July to September 2026
    m = re.search(rf"{MON}\w*\s*(?:-|–|to|through)\s*{MON}\w* (\d{{4}})", t)
    if m:
        y = int(m.group(3))
        start, end = date(y, _month(m.group(1)), 1), _month_end(y, _month(m.group(2)))
        return TimeRange(start, clip(end), f"{m.group(1).title()}-{m.group(2).title()} {y}")
    # the 12 months to 28 September 2026 / last 12 months
    m = re.search(rf"(\d+) months? (?:to|until|ending) (\d{{1,2}}) {MON}\w* (\d{{4}})", t)
    if m:
        end = date(int(m.group(4)), _month(m.group(3)), int(m.group(2)))
        n = int(m.group(1))
        start = date(end.year - (n // 12), end.month, end.day) if n % 12 == 0 else end - timedelta(days=30 * n)
        return TimeRange(start + timedelta(days=1), end, f"{n} months to {end:%d %b %Y}")
    m = re.search(r"last (\d+) (day|week|month)s?", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = n * {"day": 1, "week": 7, "month": 30}[unit]
        return TimeRange(as_of - timedelta(days=days - 1), as_of, f"last {n} {unit}s")
    # a single day (on 25 September 2026) or a day range (23-24 September 2026)
    m = re.search(rf"\b(\d{{1,2}})\s*(?:-|–|to)\s*(\d{{1,2}}) {MON}\w* (\d{{4}})", t)
    if m:
        mo, y = _month(m.group(3)), int(m.group(4))
        start, end = date(y, mo, int(m.group(1))), date(y, mo, int(m.group(2)))
        return TimeRange(start, clip(end), f"{start.day}-{end.day} {end:%b %Y}")
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)? {MON}\w* (\d{{4}})", t)
    if m:
        mo, y = _month(m.group(2)), int(m.group(3))
        d = date(y, mo, int(m.group(1)))
        return TimeRange(d, clip(d), f"{d.day} {d:%b %Y}")
    # September 2026 / in August 2026
    m = re.search(rf"\b{MON}\w* (\d{{4}})", t)
    if m:
        y, mo = int(m.group(2)), _month(m.group(1))
        return TimeRange(date(y, mo, 1), clip(_month_end(y, mo)), f"{m.group(1).title()} {y}")
    m = re.search(r"\b(in|during|since|opened in|for) (20\d\d)\b", t)
    if m:
        y = int(m.group(2))
        return TimeRange(date(y, 1, 1), clip(date(y, 12, 31)), str(y))
    if "last month" in t:
        first = date(as_of.year, as_of.month, 1)
        prev_end = first - timedelta(days=1)
        return TimeRange(date(prev_end.year, prev_end.month, 1), prev_end, "last month")
    if "this month" in t:
        return TimeRange(date(as_of.year, as_of.month, 1), as_of, "this month")
    if "this week" in t:
        return TimeRange(as_of - timedelta(days=as_of.weekday()), as_of + timedelta(days=6 - as_of.weekday()), "this week")
    if "last week" in t:
        start = as_of - timedelta(days=as_of.weekday() + 7)
        return TimeRange(start, start + timedelta(days=6), "last week")
    if "yesterday" in t:
        return TimeRange(as_of - timedelta(days=1), as_of - timedelta(days=1), "yesterday")
    return None
