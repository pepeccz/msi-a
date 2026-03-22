"""
conftest.py for tests/agent/

Pre-patches missing optional dependencies that are not installed in the
local test environment. Must run BEFORE any test file imports from agent.*
because agent/__init__.py triggers a deep import chain that requires
structlog and langgraph.checkpoint.redis.
"""

import sys
import types
from unittest.mock import MagicMock


def _install_stub(name: str) -> None:
    """Install a MagicMock stub for *name* if not already installed."""
    if name not in sys.modules:
        stub = MagicMock()
        stub.__name__ = name
        sys.modules[name] = stub


# ---------------------------------------------------------------------------
# Stub structlog — not installed in local test env.
# agent/__init__.py → agent.graph.conversation_graph → import structlog
# ---------------------------------------------------------------------------
if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog

# ---------------------------------------------------------------------------
# Stub langgraph.checkpoint.redis — not installed locally.
# agent/state/__init__.py → checkpointer.py → langgraph.checkpoint.redis.aio
# ---------------------------------------------------------------------------
for _redis_mod_name in (
    "langgraph.checkpoint.redis",
    "langgraph.checkpoint.redis.aio",
):
    if _redis_mod_name not in sys.modules:
        _redis_stub = types.ModuleType(_redis_mod_name)
        _redis_stub.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_redis_mod_name] = _redis_stub
