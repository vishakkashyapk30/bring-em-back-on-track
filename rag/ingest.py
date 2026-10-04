"""Build the interaction search index (data/search.duckdb): redacted notes, transcripts and voice speech-to-text,
with a BM25 inverted index. See rag/search_index.py and docs/interaction_search.md.

The policy documents are indexed separately (rag/index.py); this is for what was said and written about customers.
Run: `python -m rag.ingest` (also the `rag-index` jobs task). The file is a rebuildable artefact, not committed.
"""

from __future__ import annotations

import json
import logging

from rag import search_index


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    print(json.dumps(search_index.build(), indent=2, default=str))


if __name__ == "__main__":
    main()
