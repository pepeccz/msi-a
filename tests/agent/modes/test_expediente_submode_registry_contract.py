"""
Regression guard: every active CollectionStep value must map to a valid
MODE_MODULES key AND the corresponding prompt file must exist on disk.

This test is a PERMANENT GUARD (expected to always PASS after the hotfix
that introduced the current MODE_MODULES naming). If it ever turns RED, it
means either a new CollectionStep member was added without a matching
MODE_MODULES entry, or a prompt file was deleted/renamed.

Requirement: R6.1 — Enum-to-registry coverage test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.utils.expediente_types import CollectionStep
from agent.prompts.loader import MODE_MODULES, PROMPTS_DIR

# Active sub-modes: exclude terminal/sentinel states that have no prompt.
_ACTIVE_STEPS = sorted(
    {s for s in CollectionStep if s not in (CollectionStep.IDLE, CollectionStep.COMPLETED)},
    key=lambda s: s.value,
)


@pytest.mark.parametrize("step", _ACTIVE_STEPS, ids=lambda s: s.value)
def test_collection_step_resolves_to_mode_modules_key(step: CollectionStep) -> None:
    """Each active CollectionStep must have a matching key in MODE_MODULES."""
    key = f"EXPEDIENTE_{step.value.upper()}"
    assert key in MODE_MODULES, (
        f"MODE_MODULES is missing entry for CollectionStep.{step.name} "
        f"(expected key: {key!r}). "
        f"Add it to agent/prompts/loader.py → MODE_MODULES."
    )


@pytest.mark.parametrize("step", _ACTIVE_STEPS, ids=lambda s: s.value)
def test_collection_step_prompt_file_exists_on_disk(step: CollectionStep) -> None:
    """Each active CollectionStep must point to a prompt file that exists on disk."""
    key = f"EXPEDIENTE_{step.value.upper()}"
    # Guard: key must be present before checking the file path.
    assert key in MODE_MODULES, (
        f"Cannot check disk path — MODE_MODULES is missing key {key!r}."
    )
    file_path = PROMPTS_DIR / MODE_MODULES[key]
    assert file_path.is_file(), (
        f"Prompt file does not exist for CollectionStep.{step.name}: {file_path}. "
        f"Create the file or fix the path in MODE_MODULES."
    )
