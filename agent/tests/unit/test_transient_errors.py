"""
Unit tests for agent.fallback.transient_errors.is_transient_error().

Strict TDD — RED first: module doesn't exist yet.
"""
from __future__ import annotations

import pytest


# These imports will fail (RED) until task 0.2 creates the module.
from agent.fallback.transient_errors import is_transient_error


# ---------------------------------------------------------------------------
# Transient error classes — should return True
# ---------------------------------------------------------------------------

class TestTransientErrors:
    """is_transient_error must return True for infrastructure / network errors."""

    def test_httpx_timeout_is_transient(self):
        import httpx
        exc = httpx.TimeoutException("timeout")
        assert is_transient_error(exc) is True

    def test_httpx_connect_error_is_transient(self):
        import httpx
        exc = httpx.ConnectError("connection refused")
        assert is_transient_error(exc) is True

    def test_httpx_remote_protocol_error_is_transient(self):
        import httpx
        exc = httpx.RemoteProtocolError("protocol error")
        assert is_transient_error(exc) is True

    def test_connection_error_is_transient(self):
        exc = ConnectionError("network down")
        assert is_transient_error(exc) is True

    def test_timeout_error_is_transient(self):
        exc = TimeoutError("timed out")
        assert is_transient_error(exc) is True


# ---------------------------------------------------------------------------
# Business / non-transient error classes — should return False
# ---------------------------------------------------------------------------

class TestBusinessErrors:
    """is_transient_error must return False for domain / business errors."""

    def test_value_error_is_not_transient(self):
        exc = ValueError("invalid value")
        assert is_transient_error(exc) is False

    def test_runtime_error_is_not_transient(self):
        exc = RuntimeError("something went wrong")
        assert is_transient_error(exc) is False

    def test_type_error_is_not_transient(self):
        exc = TypeError("wrong type")
        assert is_transient_error(exc) is False

    def test_key_error_is_not_transient(self):
        exc = KeyError("missing_key")
        assert is_transient_error(exc) is False

    def test_exception_is_not_transient(self):
        exc = Exception("generic business error")
        assert is_transient_error(exc) is False
