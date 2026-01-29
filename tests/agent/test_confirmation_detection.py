"""
Tests for affirmative confirmation detection.

Ensures that word-boundary based regex avoids false positives while
detecting genuine Spanish confirmations (both formal and colloquial).
"""

import pytest
from agent.nodes.conversational_agent import is_affirmative_confirmation


class TestConfirmationDetection:
    """Test cases for is_affirmative_confirmation()."""

    # =================================================================
    # POSITIVE CASES - Should be detected as confirmations
    # =================================================================

    @pytest.mark.parametrize("message", [
        "sí",
        "si",
        "yes",
        "dale",
        "vale",
        "ok",
        "okey",
        "okay",
        "adelante",
        "claro",
        "perfecto",
        "venga",
        "hazlo",
        "abrelo",
        "ábrelo",
        "procede",
        "sigue",
        "continua",
        "continúa",
        "por supuesto",
        "correcto",
        "de acuerdo",
        "genial",
        "bueno",
        "va",
        "vamos",
        "eso",
    ])
    def test_affirmative_single_word(self, message: str):
        """Single-word affirmative confirmations should match."""
        assert is_affirmative_confirmation(message) is True

    @pytest.mark.parametrize("message", [
        "Sí",
        "SI",
        "DALE",
        "Vale",
        "OK",
        "Perfecto",
        "Adelante",
    ])
    def test_affirmative_case_insensitive(self, message: str):
        """Confirmations should be case-insensitive."""
        assert is_affirmative_confirmation(message) is True

    @pytest.mark.parametrize("message", [
        "sí, gracias",
        "dale pues",
        "vale, adelante",
        "ok perfecto",
        "claro que sí",
    ])
    def test_affirmative_short_phrases(self, message: str):
        """Short phrases with confirmation words should match."""
        assert is_affirmative_confirmation(message) is True

    @pytest.mark.parametrize("message", [
        " sí ",
        "  dale  ",
        "\tvale\t",
        "ok\n",
    ])
    def test_affirmative_with_whitespace(self, message: str):
        """Confirmations with surrounding whitespace should match."""
        assert is_affirmative_confirmation(message) is True

    # =================================================================
    # NEGATIVE CASES - Should NOT be detected as confirmations
    # =================================================================

    @pytest.mark.parametrize("message", [
        "¿vale la pena?",
        "vale la pena",
        "¿eso cuánto cuesta?",
        "genial pero cuánto?",
        "genial, ¿pero cuánto cuesta?",
        "¿sí?",
        "¿dale, y cuánto es?",
        "ok ¿pero cuánto?",
    ])
    def test_questions_should_not_match(self, message: str):
        """Messages containing questions should NOT match."""
        assert is_affirmative_confirmation(message) is False

    @pytest.mark.parametrize("message", [
        "no",
        "no gracias",
        "no, vale la pena",
        "ni hablar",
        "espera",
        "déjame pensar",
    ])
    def test_negative_responses(self, message: str):
        """Negative responses should NOT match."""
        assert is_affirmative_confirmation(message) is False

    @pytest.mark.parametrize("message", [
        "esta es una frase muy larga que tiene más de cinco palabras",
        "me gustaría saber más información antes de decidir",
        "necesito pensarlo un poco más, dame un momento",
    ])
    def test_long_messages_should_not_match(self, message: str):
        """Messages longer than MAX_CONFIRMATION_MESSAGE_WORDS should NOT match."""
        assert is_affirmative_confirmation(message) is False

    @pytest.mark.parametrize("message", [
        "hola",
        "qué tal",
        "buenos días",
        "precio",
        "información",
    ])
    def test_unrelated_messages(self, message: str):
        """Unrelated messages should NOT match."""
        assert is_affirmative_confirmation(message) is False

    @pytest.mark.parametrize("message", [
        # Edge case: "vale" as part of larger word (shouldn't happen in Spanish, but test anyway)
        "valemos mucho",
        # Edge case: Confirmation word in middle of phrase without clear affirmation
        "no sé si vale",
        "puede que siga",
    ])
    def test_confirmation_word_not_standalone(self, message: str):
        """Confirmation words that aren't standalone affirmations should NOT match."""
        assert is_affirmative_confirmation(message) is False

    # =================================================================
    # EDGE CASES
    # =================================================================

    def test_empty_string(self):
        """Empty string should NOT match."""
        assert is_affirmative_confirmation("") is False

    def test_whitespace_only(self):
        """Whitespace-only string should NOT match."""
        assert is_affirmative_confirmation("   ") is False

    @pytest.mark.parametrize("message", [
        "sí, pero necesito saber más detalles antes de decidir si me interesa o no",
    ])
    def test_affirmative_word_in_long_non_confirmation(self, message: str):
        """Long messages with confirmation words should NOT match (length check)."""
        assert is_affirmative_confirmation(message) is False
