import hashlib
import json
from typing import Any


def stable_hash(obj: Any) -> str:
    """SHA-256 of a canonical JSON dump. Used for audit input/output hashes and LLM cache keys."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()
