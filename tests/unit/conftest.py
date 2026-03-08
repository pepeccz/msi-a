"""
conftest.py for tests/unit/

Pre-patches missing optional dependencies that are not installed in the
test environment (e.g. phonenumbers, which is only used at runtime in
api/models/chatwoot_webhook.py). This prevents ImportError during
pytest collection of tests that import from agent.main or api.services.
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


# Stub out phonenumbers — not installed in test env
_install_stub("phonenumbers")
_install_stub("phonenumbers.phonenumberutil")
