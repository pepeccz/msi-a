"""
Unit tests for agent/prompts/lexical_triggers.py

Covers spec Capability 1: Lexical triggers module
- PROCEED_PHRASES is a tuple, len >= 20
- PROCEED_PHRASES contains all 21 required phrases
- IDENTIFY_PHRASES is a tuple, len >= 8
- IDENTIFY_PHRASES contains all 8 required phrases
- All entries are lowercase strings
- is_proceed("quiero homologar") → True
- is_proceed("") → False
- is_proceed("hola") → False
"""
from __future__ import annotations

import pytest


# All 21 required PROCEED phrases from spec REQ-1.5
REQUIRED_PROCEED_PHRASES = [
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
]

# All 8 required IDENTIFY phrases from spec REQ-1.6
REQUIRED_IDENTIFY_PHRASES = [
    "qué es",
    "cómo funciona",
    "explícame",
    "quiero saber sobre",
    "¿puedo homologar",
    "cuéntame",
    "me han dicho que tengo que homologar",
    "¿qué documentación necesito?",
]


class TestProceedPhrases:
    """PROCEED_PHRASES structural invariants."""

    def test_proceed_phrases_is_tuple(self):
        """PROCEED_PHRASES must be a tuple — frozen/immutable."""
        from agent.prompts.lexical_triggers import PROCEED_PHRASES

        assert isinstance(PROCEED_PHRASES, tuple), (
            f"PROCEED_PHRASES must be a tuple, got {type(PROCEED_PHRASES).__name__}"
        )

    def test_proceed_phrases_min_size(self):
        """PROCEED_PHRASES must contain at least 20 entries per spec."""
        from agent.prompts.lexical_triggers import PROCEED_PHRASES

        assert len(PROCEED_PHRASES) >= 20, (
            f"PROCEED_PHRASES must have at least 20 entries, got {len(PROCEED_PHRASES)}"
        )

    def test_proceed_phrases_contains_required_phrases(self):
        """All 21 required phrases from spec REQ-1.5 must be present."""
        from agent.prompts.lexical_triggers import PROCEED_PHRASES

        missing = [p for p in REQUIRED_PROCEED_PHRASES if p not in PROCEED_PHRASES]
        assert not missing, (
            f"PROCEED_PHRASES missing required phrases: {missing}"
        )

    def test_proceed_phrases_all_lowercase(self):
        """All entries must be normalized lowercase strings."""
        from agent.prompts.lexical_triggers import PROCEED_PHRASES

        non_lower = [p for p in PROCEED_PHRASES if p != p.lower()]
        assert not non_lower, (
            f"PROCEED_PHRASES entries must be lowercase. Non-lowercase: {non_lower}"
        )


class TestIdentifyPhrases:
    """IDENTIFY_PHRASES structural invariants."""

    def test_identify_phrases_is_tuple(self):
        """IDENTIFY_PHRASES must be a tuple — frozen/immutable."""
        from agent.prompts.lexical_triggers import IDENTIFY_PHRASES

        assert isinstance(IDENTIFY_PHRASES, tuple), (
            f"IDENTIFY_PHRASES must be a tuple, got {type(IDENTIFY_PHRASES).__name__}"
        )

    def test_identify_phrases_min_size(self):
        """IDENTIFY_PHRASES must contain at least 8 entries per spec."""
        from agent.prompts.lexical_triggers import IDENTIFY_PHRASES

        assert len(IDENTIFY_PHRASES) >= 8, (
            f"IDENTIFY_PHRASES must have at least 8 entries, got {len(IDENTIFY_PHRASES)}"
        )

    def test_identify_phrases_contains_required_phrases(self):
        """All 8 required phrases from spec REQ-1.6 must be present."""
        from agent.prompts.lexical_triggers import IDENTIFY_PHRASES

        missing = [p for p in REQUIRED_IDENTIFY_PHRASES if p not in IDENTIFY_PHRASES]
        assert not missing, (
            f"IDENTIFY_PHRASES missing required phrases: {missing}"
        )

    def test_identify_phrases_all_lowercase(self):
        """All entries must be normalized lowercase strings."""
        from agent.prompts.lexical_triggers import IDENTIFY_PHRASES

        non_lower = [p for p in IDENTIFY_PHRASES if p != p.lower()]
        assert not non_lower, (
            f"IDENTIFY_PHRASES entries must be lowercase. Non-lowercase: {non_lower}"
        )


class TestIsProceedFunction:
    """is_proceed() pure utility function."""

    def test_is_proceed_true_for_known_phrase(self):
        """is_proceed('quiero homologar') must return True."""
        from agent.prompts.lexical_triggers import is_proceed

        assert is_proceed("quiero homologar") is True

    def test_is_proceed_case_insensitive(self):
        """is_proceed must be case-insensitive."""
        from agent.prompts.lexical_triggers import is_proceed

        assert is_proceed("QUIERO HOMOLOGAR el escape") is True

    def test_is_proceed_false_for_empty(self):
        """is_proceed('') must return False."""
        from agent.prompts.lexical_triggers import is_proceed

        assert is_proceed("") is False

    def test_is_proceed_false_for_unrelated(self):
        """is_proceed('hola') must return False."""
        from agent.prompts.lexical_triggers import is_proceed

        assert is_proceed("hola") is False
