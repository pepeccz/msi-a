"""
MSI-a — Transient error classifier.

Extracted from ``agent.modes.base_mode._is_transient_error`` so that both
``BaseModeNode`` and the expediente sub-node factory can import from a single
source of truth (ADR-012).

Design note:
    Transient errors are *infrastructure* failures (network, LLM API) that
    LangGraph's built-in ``RetryPolicy`` (Tier 1) is designed to handle.
    They must NOT be absorbed by ``FallbackHandler`` (Tier 2 / Tier 3), which
    is designed for business/conversational errors only.
"""

from __future__ import annotations


def is_transient_error(exc: BaseException) -> bool:
    """
    Return True if *exc* is a transient infrastructure error.

    Transient errors should propagate to LangGraph's RetryPolicy (Tier 1)
    rather than being handled by FallbackHandler (Tier 2), which is
    designed for business/conversational errors only (ADR-012).

    Args:
        exc: The exception to classify.

    Returns:
        True for network / LLM API errors that LangGraph should retry.
        False for all other errors (business errors, validation, etc.).
    """
    import httpx

    TRANSIENT: tuple[type[BaseException], ...] = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        ConnectionError,
        TimeoutError,
    )
    try:
        from openai import APIConnectionError, APITimeoutError, InternalServerError

        TRANSIENT = (*TRANSIENT, APIConnectionError, APITimeoutError, InternalServerError)
    except ImportError:  # pragma: no cover — openai package optional in test env
        pass

    return isinstance(exc, TRANSIENT)
