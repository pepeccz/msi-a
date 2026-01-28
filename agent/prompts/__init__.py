"""
MSI-a Dynamic Prompt System.

This package provides modular, phase-aware prompts to optimize token usage.

Key components:
- loader.py: Assembles prompts dynamically based on FSM state
- state_summary.py: Generates real-time context summaries
- core/: Always-included prompt modules (~2,200 tokens)
- phases/: Phase-specific modules (~300-1,500 tokens each)

Usage:
    from agent.prompts.loader import assemble_system_prompt
    from agent.prompts.state_summary import generate_state_summary
    
    prompt = assemble_system_prompt(
        fsm_state=state.get("fsm_state"),
        state_summary=generate_state_summary(fsm_state),
        client_context="..."
    )

Estimated savings: 40-60% tokens per LLM call compared to legacy system.md
"""

from agent.prompts.loader import (
    assemble_system_prompt,
    clear_cache,
    get_prompt_stats,
    load_core_modules,
    load_phase_module,
)
from agent.prompts.state_summary import (
    generate_minimal_summary,
    generate_state_summary,
    generate_state_summary_v2,
)

__all__ = [
    "assemble_system_prompt",
    "clear_cache",
    "generate_minimal_summary",
    "generate_state_summary",
    "generate_state_summary_v2",
    "get_prompt_stats",
    "load_core_modules",
    "load_phase_module",
]
