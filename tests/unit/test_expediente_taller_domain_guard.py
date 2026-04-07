"""Unit tests for the taller domain guard — RETIRED (Phase 2 cleanup).

The Python-based taller domain guard (_TALLER_DOMAIN_GUARD_SUBMODES,
_TALLER_DOMAIN_RE, and the guard logic in expediente_mode.py) was deleted in
Phase 2 (simplify-agent-loop-engine).

The taller domain boundary is now enforced exclusively via prompt rules in:
  - agent/prompts/modes/expediente_datos_personales.md
  - agent/prompts/modes/expediente_datos_vehiculo.md

These tests previously tested the Python guard behavior and are now retired.
The test module is kept as a tombstone to document the removal.

Phase 2 deletion task: Batch 2, tasks 2.2 (taller guard) + test suite update.
"""

from __future__ import annotations

import re

import pytest

# _TALLER_DOMAIN_GUARD_SUBMODES and _TALLER_DOMAIN_RE were DELETED from
# agent/modes/submodos/_shared.py in Phase 2.  They are no longer exported
# by expediente_mode.py via the wildcard re-export.
#
# New coverage for prompt-enforced taller domain boundary:
#   agent/prompts/modes/expediente_datos_personales.md — "Dominio restringido" rule
#   agent/prompts/modes/expediente_datos_vehiculo.md   — "Dominio restringido" rule
#
# Tests verifying the DELETION are in:
#   tests/unit/test_phase2_dead_code_removal.py::TestBatch21TallerGuardNotInAll


# ---------------------------------------------------------------------------
# Tombstone — constants have been deleted, guard logic no longer exists
# ---------------------------------------------------------------------------
# All guard behavior tests below are marked xfail because the guard constants
# no longer exist.  They serve as documentation of what was removed.
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Python taller guard deleted in Phase 2 — prompt-enforced now")
class TestTallerDomainGuardConstants:
    """RETIRED: Verify _TALLER_DOMAIN_GUARD_SUBMODES and _TALLER_DOMAIN_RE are correct."""

    def test_guard_submodes_contains_collect_personal(self) -> None:
        pass  # Tombstone

    def test_guard_submodes_contains_collect_vehicle(self) -> None:
        pass  # Tombstone

    def test_guard_submodes_does_not_contain_collect_workshop(self) -> None:
        pass  # Tombstone

    def test_guard_submodes_does_not_contain_collect_base_docs(self) -> None:
        pass  # Tombstone

    def test_guard_submodes_does_not_contain_review_summary(self) -> None:
        pass  # Tombstone

    def test_taller_domain_re_is_compiled_pattern(self) -> None:
        pass  # Tombstone

    def test_taller_domain_re_has_ignorecase(self) -> None:
        pass  # Tombstone


@pytest.mark.skip(reason="Python taller guard deleted in Phase 2 — prompt-enforced now")
def test_taller_domain_guard(*args: object, **kwargs: object) -> None:
    """RETIRED: Guard strips taller content in collect_personal/collect_vehicle only."""
    pass  # Tombstone


@pytest.mark.skip(reason="Python taller guard deleted in Phase 2 — prompt-enforced now")
def test_strip_preserves_non_taller_content() -> None:
    pass  # Tombstone


@pytest.mark.skip(reason="Python taller guard deleted in Phase 2 — prompt-enforced now")
def test_strip_result_is_non_empty_when_content_remains() -> None:
    pass  # Tombstone


@pytest.mark.skip(reason="Python taller guard deleted in Phase 2 — prompt-enforced now")
def test_case_insensitive_match_in_guard() -> None:
    pass  # Tombstone


@pytest.mark.skip(reason="Python taller guard deleted in Phase 2 — prompt-enforced now")
def test_production_bug_phrase_is_caught() -> None:
    pass  # Tombstone


@pytest.mark.skip(reason="Python taller guard deleted in Phase 2 — prompt-enforced now")
def test_production_bug_full_sentence_variation() -> None:
    pass  # Tombstone


@pytest.mark.skip(reason="Python taller guard deleted in Phase 2 — prompt-enforced now")
def test_85_eur_phrase_is_caught_in_collect_personal() -> None:
    pass  # Tombstone


@pytest.mark.skip(reason="Python taller guard deleted in Phase 2 — prompt-enforced now")
def test_85_eur_phrase_passes_in_collect_workshop() -> None:
    pass  # Tombstone
