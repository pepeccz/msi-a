"""Lexical triggers for intent detection in PRE_EXPEDIENTE. Import-only.

Single source of truth for PROCEED and IDENTIFY phrase lists used both
in prompt template substitution ({{LEXICAL_PROCEED_PHRASES}}) and in
code-side intent gates.
"""
from __future__ import annotations

PROCEED_PHRASES: tuple[str, ...] = (
    "quiero homologar",
    "voy a homologar",
    "vengo a homologar",
    "necesito homologar",
    "me gustaría homologar",
    "querría homologar",
    "tengo que homologar",
    "legalizar",
    "regularizar",
    "cuánto cuesta",
    "cuánto sale",
    "cuánto vale",
    "qué precio",
    "qué vale",
    "dame presupuesto",
    "dame el presupuesto",
    "quiero presupuesto",
    "pásame presupuesto",
    "precio de",
    "precio del",
    "precio para",
)

IDENTIFY_PHRASES: tuple[str, ...] = (
    "qué es",
    "cómo funciona",
    "explícame",
    "quiero saber sobre",
    "¿puedo homologar",
    "cuéntame",
    "me han dicho que tengo que homologar",
    "¿qué documentación necesito?",
)


def is_proceed(message: str) -> bool:
    """Case-insensitive substring match against PROCEED_PHRASES.

    Pure utility — returns True if any PROCEED phrase appears in the message.
    Returns False for empty input.
    """
    if not message:
        return False
    low = message.lower()
    return any(p in low for p in PROCEED_PHRASES)
