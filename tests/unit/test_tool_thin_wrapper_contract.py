"""
Tool Thin-Wrapper Contract Verification — Wave 4 (T4.3).

Verifies structural contracts for all 27 agent tools:
1. Function body is ≤ 30 lines (thin wrapper, no business logic inline).
2. ``args_schema`` is set on the LangChain tool object (not None).
3. The tool has a docstring with an ``Args`` section (or explicit note that
   the tool takes no arguments).

These are static/structural checks that run without any database, Redis,
or LLM dependencies.
"""

from __future__ import annotations

import inspect
import textwrap
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Collect all 27 tools
# ---------------------------------------------------------------------------

# Import individually to avoid triggering heavy service-layer initialisation
# from __init__.py's combined list.

from agent.tools.tarifa_tools import (
    listar_categorias,
    listar_tarifas,
    obtener_servicios_adicionales,
)
from agent.tools.element_tools import (
    listar_elementos,
    identificar_y_resolver_elementos,
    seleccionar_variante_por_respuesta,
    calcular_tarifa_con_elementos,
    obtener_documentacion_elemento,
)
from agent.tools.case_tools import (
    iniciar_expediente,
    obtener_estado_expediente,
    actualizar_datos_expediente,
    actualizar_datos_taller,
    consulta_durante_expediente,
    cancelar_expediente,
    editar_expediente,
    finalizar_expediente,
)
from agent.tools.element_data_tools import (
    obtener_campos_elemento,
    guardar_datos_elemento,
    confirmar_fotos_elemento,
    completar_elemento_actual,
    obtener_progreso_elementos,
    confirmar_documentacion_base,
    reenviar_imagenes_elemento,
)
from agent.tools.vehicle_tools import identificar_tipo_vehiculo
from agent.tools.image_tools import enviar_imagenes_ejemplo
from agent.tools.shared_tools import escalar_a_humano
from agent.tools.transition_tools import confirmar_presupuesto

ALL_27_TOOLS = [
    # tarifa_tools (3)
    listar_categorias,
    listar_tarifas,
    obtener_servicios_adicionales,
    # element_tools (5)
    listar_elementos,
    identificar_y_resolver_elementos,
    seleccionar_variante_por_respuesta,
    calcular_tarifa_con_elementos,
    obtener_documentacion_elemento,
    # case_tools (8)
    iniciar_expediente,
    obtener_estado_expediente,
    actualizar_datos_expediente,
    actualizar_datos_taller,
    consulta_durante_expediente,
    cancelar_expediente,
    editar_expediente,
    finalizar_expediente,
    # element_data_tools (7)
    obtener_campos_elemento,
    guardar_datos_elemento,
    confirmar_fotos_elemento,
    completar_elemento_actual,
    obtener_progreso_elementos,
    confirmar_documentacion_base,
    reenviar_imagenes_elemento,
    # vehicle_tools (1)
    identificar_tipo_vehiculo,
    # image_tools (1)
    enviar_imagenes_ejemplo,
    # shared_tools (1)
    escalar_a_humano,
    # transition_tools (1)
    confirmar_presupuesto,
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Maximum allowed non-blank, non-comment lines in a tool function body.
# This enforces the thin-wrapper contract: business logic must live in services.
MAX_BODY_LINES = 30

# Minimum acceptable line threshold before flagging 0-line bodies as suspicious.
MIN_BODY_LINES = 1


def _count_code_lines(fn: Any) -> int:
    """Count non-blank, non-comment lines in the function source.

    Decorators and the ``def`` line are excluded — only the body is counted.
    """
    try:
        raw_source = inspect.getsource(fn)
    except (TypeError, OSError):
        # Built-in or C extension — not applicable
        return 0

    # Dedent so indentation doesn't confuse us
    lines = textwrap.dedent(raw_source).splitlines()

    # Skip decorators and the ``def`` / ``async def`` line itself
    in_body = False
    body_lines = []
    for line in lines:
        stripped = line.strip()
        if not in_body:
            if stripped.startswith("def ") or stripped.startswith("async def "):
                in_body = True
            continue
        body_lines.append(stripped)

    # Remove blank lines and pure comment lines
    code_lines = [
        l for l in body_lines if l and not l.startswith("#")
    ]
    return len(code_lines)


def _get_tool_name(tool_obj: Any) -> str:
    """Return a human-readable name for a LangChain tool object."""
    # LangChain StructuredTool stores the name in .name
    return getattr(tool_obj, "name", repr(tool_obj))


def _get_underlying_fn(tool_obj: Any) -> Any:
    """Return the underlying Python function from a LangChain tool wrapper."""
    # StructuredTool wraps the coroutine in .coroutine or .func
    for attr in ("coroutine", "func"):
        fn = getattr(tool_obj, attr, None)
        if fn is not None:
            return fn
    return tool_obj


def _get_docstring(tool_obj: Any) -> str:
    """Return the docstring of the tool's underlying function."""
    fn = _get_underlying_fn(tool_obj)
    return inspect.getdoc(fn) or ""


# ---------------------------------------------------------------------------
# Parametrised tests
# ---------------------------------------------------------------------------

TOOL_IDS = [_get_tool_name(t) for t in ALL_27_TOOLS]


@pytest.mark.parametrize("tool_obj", ALL_27_TOOLS, ids=TOOL_IDS)
def test_tool_count_is_27() -> None:
    """Sanity check: the ALL_27_TOOLS list has exactly 27 entries."""
    assert len(ALL_27_TOOLS) == 27, (
        f"Expected 27 tools, found {len(ALL_27_TOOLS)}.  "
        "Update ALL_27_TOOLS if a tool was added or removed."
    )


# Deduplicate the count test (it doesn't need parametrisation)
def test_tool_list_size() -> None:
    """Verify the catalogue has exactly 27 tools (no duplicates)."""
    names = [_get_tool_name(t) for t in ALL_27_TOOLS]
    assert len(names) == 27, f"Found {len(names)} tools, expected 27"
    assert len(set(names)) == len(names), (
        f"Duplicate tool names detected: {[n for n in names if names.count(n) > 1]}"
    )


@pytest.mark.parametrize("tool_obj", ALL_27_TOOLS, ids=TOOL_IDS)
def test_args_schema_is_set(tool_obj: Any) -> None:
    """Every tool must declare args_schema (not None).

    An unset args_schema means LangChain cannot validate inputs and the LLM
    receives no structured parameter description — both are correctness bugs.
    """
    schema = getattr(tool_obj, "args_schema", None)
    tool_name = _get_tool_name(tool_obj)
    assert schema is not None, (
        f"Tool '{tool_name}' has args_schema=None.  "
        "Pass a Pydantic BaseModel as args_schema= in @tool()."
    )


@pytest.mark.parametrize("tool_obj", ALL_27_TOOLS, ids=TOOL_IDS)
def test_tool_has_docstring(tool_obj: Any) -> None:
    """Every tool must have a docstring (used by the LLM for reasoning).

    An empty or missing docstring means the LLM has no description of the
    tool's purpose, parameters, or when to use it.
    """
    doc = _get_docstring(tool_obj)
    tool_name = _get_tool_name(tool_obj)
    assert doc, f"Tool '{tool_name}' has no docstring."
    assert len(doc.strip()) >= 20, (
        f"Tool '{tool_name}' docstring is too short ({len(doc.strip())} chars).  "
        "Provide a meaningful description."
    )


@pytest.mark.parametrize("tool_obj", ALL_27_TOOLS, ids=TOOL_IDS)
def test_tool_body_is_thin_wrapper(tool_obj: Any) -> None:
    """Every tool function body must be ≤ 30 non-blank, non-comment lines.

    Tools are thin wrappers: they read state, call a service, and return.
    Business logic belongs in agent/services/, not in the tool body.

    Tools that exceed this limit likely have inlined logic that should be
    extracted to a service.
    """
    fn = _get_underlying_fn(tool_obj)
    line_count = _count_code_lines(fn)
    tool_name = _get_tool_name(tool_obj)
    assert line_count <= MAX_BODY_LINES, (
        f"Tool '{tool_name}' body has {line_count} code lines "
        f"(max {MAX_BODY_LINES}).  "
        "Extract business logic to agent/services/ to keep tools thin."
    )
    assert line_count >= MIN_BODY_LINES, (
        f"Tool '{tool_name}' body appears empty ({line_count} lines).  "
        "Check that getsource() is resolving the correct function."
    )


@pytest.mark.parametrize("tool_obj", ALL_27_TOOLS, ids=TOOL_IDS)
def test_tool_docstring_has_args_or_no_args_note(tool_obj: Any) -> None:
    """Tools with parameters must document them in the docstring.

    The LLM uses docstrings to understand how to call tools.  Tools with
    parameters must include an ``Args:`` section (or a comment noting that
    the tool takes no user-visible args).

    Tools that take no parameters (empty Pydantic schema) are exempt.
    """
    tool_name = _get_tool_name(tool_obj)
    doc = _get_docstring(tool_obj)

    # Check if the tool has any user-visible parameters via its schema
    schema = getattr(tool_obj, "args_schema", None)
    if schema is None:
        return  # Already caught by test_args_schema_is_set

    schema_fields = getattr(schema, "model_fields", {})
    if not schema_fields:
        # No parameters — no Args section required
        return

    # Tools with parameters must have an Args section in their docstring
    has_args_section = "Args:" in doc or "args:" in doc.lower()
    assert has_args_section, (
        f"Tool '{tool_name}' has {len(schema_fields)} parameter(s) "
        f"({list(schema_fields.keys())}) but no 'Args:' section in its docstring.  "
        "Add an Args section so the LLM understands how to call this tool."
    )
