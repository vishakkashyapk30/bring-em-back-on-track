"""Section-level corpus for policy answers: the release's reference documents (current versions only) plus the
QA checklist items. Each section keeps doc_id, section id, doc_type, version, language and authority rank.

The corpus is small (19 documents), so retrieval is an in-process BM25 (rag/retrieve.py); LanceDB + embeddings
(`uv sync --extra rag`) can replace it without changing callers.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache

import duckdb

from common.config import get_settings
from rag.precedence import AUTHORITY, rank

HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
SECTION_ID = re.compile(r"(§\s?[\d.]+|Q\d+|Step \d+|Item \d+)", re.I)


@dataclass(frozen=True)
class Section:
    doc_id: str
    section: str
    title: str
    text: str
    doc_type: str
    version: str
    language: str
    authority: int  # lower = higher authority (rag/precedence.py)
    products: tuple[str, ...] = ()   # reference_documents.applies_to_products; empty = all
    provinces: tuple[str, ...] = ()  # reference_documents.applies_to_provinces; empty or "ALL" = all


def _split(doc_id: str, md: str, meta: dict) -> list[Section]:
    out, cur_title, cur_lines = [], "", []

    def flush() -> None:
        body = "\n".join(line for line in cur_lines if line).strip()
        if body:
            m = SECTION_ID.search(cur_title)
            sec = m.group(1).replace(" ", "") if m else (cur_title[:40] or "intro")
            out.append(Section(doc_id, sec, cur_title, body, meta["doc_type"], meta["version"], meta["language"],
                               rank(meta["doc_type"]), meta.get("products", ()), meta.get("provinces", ())))

    # FAQ style: "**Q1. question?** answer" paragraphs become one section each
    md = re.sub(r"\*\*(Q\d+)\.\s*", lambda m: f"\n## {m.group(1)} ", md)
    for line in md.splitlines():
        if line.startswith(">"):  # synthetic-document disclaimer
            continue
        # table rows (e.g. hardship programme terms): one section per data row, id = first cell
        if line.startswith("|") and not re.match(r"^\|\s*-", line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and cells[0] and cells[0].lower() not in ("programme", "program", "province", "item"):
                flush()
                cur_title, cur_lines = cells[0], [" ; ".join(cells)]
                flush()
                cur_title, cur_lines = "", []
            continue
        h = HEADING.match(line)
        if h and len(h.group(1)) >= 2:
            flush()
            cur_title, cur_lines = h.group(2).strip(), []
        elif not h:
            cur_lines.append(line.strip())
    flush()
    return out


@lru_cache
def load_sections() -> tuple[Section, ...]:
    s = get_settings()
    root = s.raw_dir / "maple_collections_release" / "files"
    con = duckdb.connect(str(s.warehouse_path), read_only=True)
    docs = con.sql("""SELECT doc_id, doc_type, version, language, file_path, applies_to_products, applies_to_provinces
                      FROM silver.reference_documents WHERE superseded_by IS NULL""").fetchall()
    sections: list[Section] = []
    for doc_id, doc_type, version, language, path, products, provinces in docs:
        p = root / path
        if p.exists():
            meta = {"doc_type": doc_type, "version": version, "language": language,
                    "products": _as_tuple(products), "provinces": _as_tuple(provinces)}
            sections += _split(doc_id, p.read_text(), meta)
    for item_no, code, desc, criteria in con.sql(
            "SELECT item_no, item_code, item_name, pass_criteria FROM silver.qa_checklist").fetchall():
        sections.append(Section("qa_checklist", f"item {item_no}", f"QA {code}", f"{desc}. Pass: {criteria}",
                                "procedure", "current", "EN", rank("procedure")))
    con.close()
    return tuple(sections)


def _as_tuple(v: object) -> tuple[str, ...]:
    """applies_to_* arrive as JSON text ('["card", "loc"]') or as a list."""
    if v is None or v == "":
        return ()
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            v = [x.strip() for x in v.split(",")]
    return tuple(str(x) for x in v)  # type: ignore[union-attr]


def sections_from_documents(docs: Iterable[Mapping]) -> tuple[Section, ...]:
    """Sections from in-memory reference documents (doc_id, text, doc_type, version, language, superseded_by,
    applies_to_products, applies_to_provinces, optional section), with the same rules as load_sections: current
    versions only, and only document types that have a place in the precedence order (rag/precedence.py), so text
    such as an agent note is never an answer source. Used to run retrieval over a supplied corpus
    (rag.retrieve.use_sections)."""
    out: list[Section] = []
    for d in docs:
        if d.get("superseded_by") or rank(d.get("doc_type") or "") >= len(AUTHORITY):
            continue
        meta = {"doc_type": d["doc_type"], "version": str(d.get("version") or ""),
                "language": d.get("language") or "EN", "products": _as_tuple(d.get("applies_to_products")),
                "provinces": _as_tuple(d.get("applies_to_provinces"))}
        if d.get("section"):
            out.append(Section(d["doc_id"], str(d["section"]), str(d.get("title") or d["section"]), d["text"],
                               meta["doc_type"], meta["version"], meta["language"], rank(meta["doc_type"]),
                               meta["products"], meta["provinces"]))
        else:
            out += _split(d["doc_id"], d["text"], meta)
    return tuple(out)
