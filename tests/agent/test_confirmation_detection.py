"""
Tests for affirmative confirmation detection.

Ensures that hybrid detection (regex + fuzzy matching + emojis) avoids false 
positives while detecting genuine Spanish confirmations (both formal and colloquial),
including common typos and visual confirmations.
"""

import pytest
from agent.nodes.conversational_agent import (
    is_affirmative_confirmation,
    check_user_confirmation,
    levenshtein_distance,
)


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
        "dlae",      # typo of "dale" (distance 2: transpose + substitute)
        "dael",      # typo of "dale" (distance 2: transpose)
        "vael",      # typo of "vale" (distance 2)
        "sii",       # typo of "si" (distance 1)
        "oks",       # typo of "ok" (distance 1)
        "perecto",   # typo of "perfecto" (distance 1)
        "adelant",   # typo of "adelante" (distance 1)
        "calro",     # typo of "claro" (distance 2)
    ])
    def test_fuzzy_matching_typos(self, message: str):
        """Common typos should be detected via fuzzy matching."""
        assert is_affirmative_confirmation(message) is True

    @pytest.mark.parametrize("message", [
        "👍",
        "✅",
        "👌",
        "✓",
        "☑️",
        "💯",
        "🆗",
        "si 👍",
        "👍 dale",
    ])
    def test_confirmation_emojis(self, message: str):
        """Confirmation emojis should be detected."""
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
        "cancelar",
        "olvídalo",
        "mejor no",
    ])
    def test_negative_responses(self, message: str):
        """Negative responses should NOT match."""
        assert is_affirmative_confirmation(message) is False

    @pytest.mark.parametrize("message", [
        "👎",
        "❌",
        "🚫",
        "⛔",
        "no 👎",
        "❌ espera",
    ])
    def test_rejection_emojis(self, message: str):
        """Rejection emojis should NOT match as confirmation."""
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


class TestCheckUserConfirmation:
    """Test cases for the 3-state confirmation checker."""

    @pytest.mark.parametrize("message,expected", [
        # Confirmed cases
        ("dale", "confirmed"),
        ("dlae", "confirmed"),  # fuzzy match
        ("sí", "confirmed"),
        ("👍", "confirmed"),
        ("ok", "confirmed"),
        ("oks", "confirmed"),  # fuzzy
        ("vale", "confirmed"),
        ("vael", "confirmed"),  # fuzzy
        ("adelante", "confirmed"),
        ("claro", "confirmed"),
        ("si 👍", "confirmed"),
        
        # Rejected cases
        ("no", "rejected"),
        ("nop", "rejected"),
        ("espera", "rejected"),
        ("espérate", "rejected"),
        ("déjame pensarlo", "rejected"),
        ("necesito tiempo", "rejected"),
        ("cancela", "rejected"),
        ("olvídalo", "rejected"),
        ("mejor no", "rejected"),
        ("todavía no", "rejected"),
        ("ahora no", "rejected"),
        ("👎", "rejected"),
        ("❌", "rejected"),
        ("no gracias 👎", "rejected"),
        
        # Uncertain cases
        ("¿cuánto cuesta?", "uncertain"),
        ("¿de verdad?", "uncertain"),
        ("bueno pero necesito más info primero", "uncertain"),
        ("hmmm", "uncertain"),
        ("a ver", "uncertain"),
        ("", "uncertain"),
        ("   ", "uncertain"),
        ("algo random sin sentido claro", "uncertain"),
    ])
    def test_three_state_detection(self, message: str, expected: str):
        """Test 3-state confirmation detection."""
        assert check_user_confirmation(message) == expected


class TestLevenshteinDistance:
    """Test Levenshtein distance calculation."""

    @pytest.mark.parametrize("s1,s2,expected", [
        ("dale", "dale", 0),
        ("dale", "dlae", 2),
        ("dale", "dael", 2),
        ("vale", "vael", 2),
        ("si", "sii", 1),
        ("ok", "oks", 1),
        ("perfecto", "perecto", 1),
        ("claro", "calro", 2),
        ("", "abc", 3),
        ("abc", "", 3),
        ("kitten", "sitting", 3),
    ])
    def test_distance_calculation(self, s1: str, s2: str, expected: int):
        """Test Levenshtein distance calculation."""
        assert levenshtein_distance(s1, s2) == expected
