"""Example binding skeleton: binds nothing, so every test SKIPS with a clear reason.

Copy this to ``adapter_impl.py``, then override operations one by one:

    SPEC_ADAPTER=examples.null_adapter:make_adapter uv run --no-project --with pytest pytest tests_spec -q
"""

from tests_spec.adapter import SpecAdapterBase


class NullAdapter(SpecAdapterBase):
    """Override e.g. ``policy_gate`` here and map it onto the real implementation."""


def make_adapter() -> NullAdapter:
    return NullAdapter()
