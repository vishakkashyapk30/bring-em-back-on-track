"""Suite wiring: loads the implementation binding and turns 'not bound' into SKIP.

Binding selection
-----------------
    SPEC_ADAPTER=module.path:factory   # factory() -> SpecAdapter (see adapter.py)

* SPEC_ADAPTER unset           -> every test that needs the system SKIPS.
* operation raises NotImplementedError (anywhere in setup or call) -> that test SKIPS.
* SPEC_ADAPTER set but cannot be imported -> tests ERROR loudly (misconfiguration).
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

ENV_VAR = "SPEC_ADAPTER"

CAPABILITY_IDS = (
    "H1", "H2", "H3", "H4", "H5",
    "S1", "S2", "S3", "S4", "S5", "S6", "S7",
    "A1", "A2", "A3",
)
TOPIC_MARKERS = {
    "policy_gate": "Contact policy gate (V1 §6 UC1 Phase 1 step 1)",
    "hardship": "Hardship flag latch, eligibility, simulator",
    "identity": "Identity resolution and golden record (V1 §3)",
    "contract": "Data contract and quality rules (V1 Part 3)",
    "sql_guard": "NL questions, semantic layer, SQL guard and refusals (V1 §4)",
    "features": "Feature store parity and point-in-time (V1 §5)",
    "nba": "Next best action (V1 §6 UC1)",
    "explanation": "Explain every decision (Brief ground rules)",
    "fairness": "No protected attributes in decisions (Brief ground rules)",
    "hitl": "Human in the loop (Brief ground rules)",
    "rbac": "Role-based access control (V1 §10)",
    "audit": "Append-only audit log (V1 §10)",
    "summary": "Post-call summary (V1 §6 UC2)",
    "assist": "Agent assist and policy answers (V1 §6 UC3)",
    "demo": "Demo storyline (NI §8)",
    "governance": "Governance guarantees (V1 §10)",
}


def pytest_configure(config):
    for level, text in (
        ("unit", "single rule or calculation from the docs"),
        ("integration", "behaviour across layers"),
        ("system", "end-to-end persona journeys"),
    ):
        config.addinivalue_line("markers", f"{level}: {text}")
    for cap in CAPABILITY_IDS:
        config.addinivalue_line("markers", f"{cap.lower()}: novel capability {cap} (V1 §7 / novel_ideas.md)")
    for name, text in TOPIC_MARKERS.items():
        config.addinivalue_line("markers", f"{name}: {text}")


def pytest_collection_modifyitems(config, items):
    """Apply the level marker from the directory a test lives in."""
    suite_root = Path(__file__).resolve().parent
    for item in items:
        try:
            rel = Path(str(item.fspath)).resolve().relative_to(suite_root)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in ("unit", "integration", "system"):
            item.add_marker(getattr(pytest.mark, rel.parts[0]))


# --- NotImplementedError -> SKIP, in setup and in the test body -------------------------
def _skip_reason(exc: BaseException) -> str:
    msg = str(exc) or exc.__class__.__name__
    return f"Binding does not implement this yet: {msg}"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    try:
        return (yield)
    except NotImplementedError as exc:
        pytest.skip(_skip_reason(exc))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    try:
        return (yield)
    except NotImplementedError as exc:
        pytest.skip(_skip_reason(exc))


# --- Binding loader ----------------------------------------------------------------------
def _load_factory(spec: str):
    if ":" not in spec:
        raise pytest.UsageError(f"{ENV_VAR} must look like 'module.path:factory', got {spec!r}")
    module_name, attr = spec.split(":", 1)
    # Allow a binding that sits next to the suite (output/adapter_impl.py).
    here = Path(__file__).resolve().parent.parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    module = importlib.import_module(module_name)
    return getattr(module, attr)


@pytest.fixture(scope="session")
def _binding():
    spec = os.environ.get(ENV_VAR, "").strip()
    if not spec:
        pytest.skip(f"No binding: set {ENV_VAR}=module:factory to run the specification tests")
    factory = _load_factory(spec)
    return factory()


@pytest.fixture
def adapter(_binding):
    """The in-process adapter, reset to an empty state for every test."""
    _binding.reset()
    return _binding


@pytest.fixture
def system(adapter):
    """The system client for journey tests."""
    return adapter.system_client()


@pytest.fixture
def agent_user():
    from tests_spec.adapter import UserContext

    return UserContext(user_id="agent-001", role="agent", team_id="team-a")


@pytest.fixture
def analyst_user():
    from tests_spec.adapter import UserContext

    return UserContext(user_id="analyst-001", role="analyst")


@pytest.fixture
def team_lead_user():
    from tests_spec.adapter import UserContext

    return UserContext(user_id="lead-001", role="team_lead", team_id="team-a")
