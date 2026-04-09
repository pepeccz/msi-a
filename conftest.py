"""
Root conftest — runs before any test collection.

Stubs out heavy infrastructure modules (Redis checkpointer, LangGraph graph)
so that pure-utility unit tests in agent/tests/unit/ can be collected and run
without a live Redis or Postgres instance.
"""

import sys
import types


def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


_heavy = [
    "langgraph.checkpoint.redis",
    "langgraph.checkpoint.redis.aio",
]
for _n in _heavy:
    if _n not in sys.modules:
        _stub(_n)

# Provide stub symbols that the agent state/checkpointer module expects.
# AsyncRedisSaver must be a real class because checkpointer.py subclasses it.
class _AsyncRedisSaverStub:  # noqa: N801
    """Stub base class — only used during unit test collection."""
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass  # pragma: no cover


_aio = sys.modules["langgraph.checkpoint.redis.aio"]
_aio.AsyncRedisSaver = _AsyncRedisSaverStub  # type: ignore[attr-defined]
