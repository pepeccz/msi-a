"""
Backward compatibility alias — PresupuestoModeNode and _apply_tool_flags
have been merged into PreExpedienteModeNode in pre_expediente_mode.py.

This module is kept to avoid breaking imports from:
- agent/services/expediente_guards.py
- agent/modes/submodos/collect_element_data.py
- agent/modes/expediente_mode.py
"""

from agent.modes.pre_expediente_mode import (
    PreExpedienteModeNode as PresupuestoModeNode,
    _apply_tool_flags,
)

__all__ = ["PresupuestoModeNode", "_apply_tool_flags"]
