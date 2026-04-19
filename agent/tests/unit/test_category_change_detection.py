"""
Unit tests for Batch D — category change detection and reset cascade.

Gap B: when ``identificar_y_resolver_elementos`` resolves a ``categoria_slug``
different from the one previously stored in ``mode_context``, the tool MUST
return a full reset cascade in ``_state_update`` and set
``_transition_to="PRE_EXPEDIENTE_DISCOVERY"``.

Covers:
- AC-3.1: all 4 tariff-dependent fields reset when slug changes
- AC-3.2: ``previous_categoria_slug`` field exists in ``ModeContextData`` with default ``None``
- AC-3.3: ``_transition_to="PRE_EXPEDIENTE_DISCOVERY"`` in ``_state_update`` on category change
- AC-3.5: no reset triggered when slug matches stored slug (happy-path continuity)
- Audit trail: ``previous_categoria_slug`` in ``_state_update`` equals the OLD slug value

Follows the Strict TDD pattern established in Batches A–C:
- RED → GREEN → TRIANGULATE → REFACTOR for every task pair.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_config(
    *,
    previous_categoria_slug: str | None = None,
    categoria_slug: str | None = None,
    precio_comunicado: bool = False,
    tarifa_calculada: dict | None = None,
    imagenes_enviadas_codigos: list | None = None,
    element_codes: list | None = None,
) -> MagicMock:
    """
    Build a minimal RunnableConfig mock whose ``get_tool_state`` returns
    the given mode_context shape.

    ``get_tool_state`` is called by ``identificar_y_resolver_elementos``
    via ``agent/tools/tool_helpers.py``.
    """
    mode_context: dict[str, Any] = {}
    if previous_categoria_slug is not None:
        mode_context["previous_categoria_slug"] = previous_categoria_slug
    if categoria_slug is not None:
        mode_context["categoria_slug"] = categoria_slug
    if precio_comunicado:
        mode_context["precio_comunicado"] = precio_comunicado
    if tarifa_calculada is not None:
        mode_context["tarifa_calculada"] = tarifa_calculada
    if imagenes_enviadas_codigos is not None:
        mode_context["imagenes_enviadas_codigos"] = imagenes_enviadas_codigos
    if element_codes is not None:
        mode_context["element_codes"] = element_codes

    state_dict = {
        "client_type": "particular",
        "mode_context": mode_context,
    }
    return state_dict


def _extract_state_update(result: dict) -> dict:
    """Return the ``_state_update`` sub-dict from a tool result (or empty dict)."""
    return result.get("_state_update", {})


def _extract_shared_context(result: dict) -> dict:
    """Return ``_state_update.shared_context`` (or empty dict)."""
    return _extract_state_update(result).get("shared_context", {})


# ---------------------------------------------------------------------------
# D1 — AC-3.2: previous_categoria_slug field exists in ModeContextData
# ---------------------------------------------------------------------------


class TestPreviousCategoriaSlugFieldExists:
    """
    AC-3.2: ``previous_categoria_slug`` MUST exist as an optional field in
    ``ModeContextData`` with a default of ``None``.

    This is a structural test — it verifies the schema, not runtime behavior.
    """

    def test_mode_context_data_has_previous_categoria_slug(self):
        """
        GIVEN a fresh ModeContextData TypedDict (total=False)
        WHEN inspected for key presence in __annotations__
        THEN 'previous_categoria_slug' MUST be in its annotations.

        This ensures the state schema was updated before any runtime code
        starts writing to the field (backward-compat pydantic default=None).
        """
        from agent.state.conversation_state import ModeContextData

        assert "previous_categoria_slug" in ModeContextData.__annotations__, (
            "ModeContextData must declare 'previous_categoria_slug' field (AC-3.2). "
            "Add: previous_categoria_slug: str | None to ModeContextData."
        )

    def test_previous_categoria_slug_allows_none(self):
        """
        GIVEN ModeContextData is a TypedDict(total=False)
        WHEN we instantiate with no keys
        THEN 'previous_categoria_slug' is absent (not required) — total=False semantics.

        This is the backward-compat guarantee: existing Redis checkpoints that
        lack this key will deserialize without error.
        """
        from agent.state.conversation_state import ModeContextData

        # total=False means no key is required — construction with no args is valid
        mc: ModeContextData = {}
        assert "previous_categoria_slug" not in mc, (
            "ModeContextData is total=False — previous_categoria_slug must NOT be "
            "required. Existing Redis checkpoints should continue to deserialize."
        )


# ---------------------------------------------------------------------------
# D3 — AC-3.1 / AC-3.3: reset cascade when slug changes
# ---------------------------------------------------------------------------


class TestCategoryChangeTriggersResetCascade:
    """
    AC-3.1: when ``identificar_y_resolver_elementos`` returns a ``categoria_slug``
    different from the one stored in ``mode_context``, ALL 4 tariff-dependent
    fields MUST be reset in ``_state_update``.

    AC-3.3: ``_transition_to`` MUST equal ``"PRE_EXPEDIENTE_DISCOVERY"``.

    Reviewer risk note (from Batch C apply-progress): ``element_codes`` is the
    field most likely to be forgotten in the reset. We test it explicitly.
    """

    async def test_all_reset_fields_present_on_category_change(self):
        """
        GIVEN mode_context has categoria_slug='motos-part' with tariff state
        WHEN identificar_y_resolver_elementos resolves 'coches-part' (new slug)
        THEN _state_update.shared_context MUST include:
            - precio_comunicado=False
            - tarifa_calculada=None
            - imagenes_enviadas_codigos=[]
            - element_codes=[]  (easy-to-forget field per reviewer note)
        AND _state_update._transition_to MUST equal 'PRE_EXPEDIENTE_DISCOVERY'.
        """
        from agent.tools.element_tools import identificar_y_resolver_elementos

        state = _make_tool_config(
            previous_categoria_slug="motos-part",
            categoria_slug="motos-part",
            precio_comunicado=True,
            tarifa_calculada={"precio_final": 350},
            imagenes_enviadas_codigos=["LUNA_DEL"],
            element_codes=["LUNA_DEL"],
        )

        dummy_match = {
            "matches": [
                ({"code": "LUNA_DEL", "name": "Luna delantera", "id": "abc"}, 0.95)
            ],
            "unmatched_terms": [],
            "ambiguous_candidates": [],
            "quantities": {},
        }

        with (
            patch("agent.tools.element_tools.get_tool_state", return_value=state),
            patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value="cat-uuid-coches",
            ),
            patch(
                "agent.tools.element_tools.get_element_service"
            ) as mock_elem_svc_factory,
            patch(
                "agent.tools.element_tools.get_tarifa_service"
            ) as mock_tarifa_svc_factory,
        ):
            # Element service returns one element, no variants
            elem_svc = AsyncMock()
            elem_svc.get_elements_by_category = AsyncMock(
                return_value=[{"code": "LUNA_DEL", "name": "Luna delantera", "id": "abc"}]
            )
            elem_svc.match_elements_with_unmatched = AsyncMock(return_value=dummy_match)
            elem_svc.get_element_variants = AsyncMock(return_value=[])
            elem_svc.get_element_with_images = AsyncMock(return_value=None)
            elem_svc.get_element_warnings = AsyncMock(return_value=[])
            mock_elem_svc_factory.return_value = elem_svc

            tarifa_svc = AsyncMock()
            tarifa_svc.get_category_data = AsyncMock(return_value=None)
            mock_tarifa_svc_factory.return_value = tarifa_svc

            # Call the tool with the NEW slug (coches-part vs stored motos-part)
            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "coches-part", "descripcion": "luna delantera"},
                config=None,
            )

        state_update = _extract_state_update(result)
        shared = _extract_shared_context(result)

        # AC-3.3: transition to DISCOVERY
        assert state_update.get("_transition_to") == "PRE_EXPEDIENTE_DISCOVERY", (
            "On category change, _state_update._transition_to MUST be "
            "'PRE_EXPEDIENTE_DISCOVERY' (AC-3.3). "
            f"Got: {state_update.get('_transition_to')!r}"
        )

        # AC-3.1: all 4 tariff-dependent fields reset
        assert shared.get("precio_comunicado") is False, (
            "precio_comunicado MUST be reset to False on category change (AC-3.1). "
            f"Got: {shared.get('precio_comunicado')!r}"
        )
        assert shared.get("tarifa_calculada") is None, (
            "tarifa_calculada MUST be reset to None on category change (AC-3.1). "
            f"Got: {shared.get('tarifa_calculada')!r}"
        )
        assert shared.get("imagenes_enviadas_codigos") == [], (
            "imagenes_enviadas_codigos MUST be reset to [] on category change (AC-3.1). "
            f"Got: {shared.get('imagenes_enviadas_codigos')!r}"
        )
        assert shared.get("element_codes") == [], (
            "element_codes MUST be reset to [] on category change (AC-3.1). "
            "This field is easy to forget — reviewer flagged it explicitly. "
            f"Got: {shared.get('element_codes')!r}"
        )

    async def test_category_change_from_aseicars_to_motos(self):
        """
        TRIANGULATE: category change with a different slug pair (aseicars→motos)
        to prevent 'Fake It' (hardcoded coches-part slug check).

        GIVEN mode_context has categoria_slug='aseicars-part'
        WHEN identificar_y_resolver_elementos resolves 'motos-part'
        THEN same reset cascade MUST fire.
        """
        from agent.tools.element_tools import identificar_y_resolver_elementos

        state = _make_tool_config(
            previous_categoria_slug="aseicars-part",
            categoria_slug="aseicars-part",
            precio_comunicado=True,
            element_codes=["SOLAR_PANEL"],
        )

        dummy_match = {
            "matches": [
                ({"code": "ESCAPE", "name": "Escape", "id": "xyz"}, 0.90)
            ],
            "unmatched_terms": [],
            "ambiguous_candidates": [],
            "quantities": {},
        }

        with (
            patch("agent.tools.element_tools.get_tool_state", return_value=state),
            patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value="cat-uuid-motos",
            ),
            patch(
                "agent.tools.element_tools.get_element_service"
            ) as mock_elem_svc_factory,
            patch(
                "agent.tools.element_tools.get_tarifa_service"
            ) as mock_tarifa_svc_factory,
        ):
            elem_svc = AsyncMock()
            elem_svc.get_elements_by_category = AsyncMock(
                return_value=[{"code": "ESCAPE", "name": "Escape", "id": "xyz"}]
            )
            elem_svc.match_elements_with_unmatched = AsyncMock(return_value=dummy_match)
            elem_svc.get_element_variants = AsyncMock(return_value=[])
            elem_svc.get_element_with_images = AsyncMock(return_value=None)
            elem_svc.get_element_warnings = AsyncMock(return_value=[])
            mock_elem_svc_factory.return_value = elem_svc

            tarifa_svc = AsyncMock()
            tarifa_svc.get_category_data = AsyncMock(return_value=None)
            mock_tarifa_svc_factory.return_value = tarifa_svc

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"},
                config=None,
            )

        state_update = _extract_state_update(result)
        shared = _extract_shared_context(result)

        assert state_update.get("_transition_to") == "PRE_EXPEDIENTE_DISCOVERY", (
            "Reset cascade must fire for any category change, not just coches→motos."
        )
        assert shared.get("precio_comunicado") is False
        assert shared.get("element_codes") == [], (
            "element_codes reset must fire for aseicars→motos change too."
        )


# ---------------------------------------------------------------------------
# D4 — AC-3.5: no reset when slug matches stored slug
# ---------------------------------------------------------------------------


class TestNoResetWhenSlugUnchanged:
    """
    AC-3.5: when the incoming ``categoria_slug`` matches the stored value,
    NO reset cascade MUST be triggered.

    This is the 'happy path continuity' test — adding a new element to an
    existing session must NOT wipe pricing state.
    """

    async def test_no_reset_when_slug_unchanged(self):
        """
        GIVEN mode_context has categoria_slug='motos-part' and tariff state
        WHEN identificar_y_resolver_elementos resolves the SAME 'motos-part'
        THEN _state_update MUST NOT contain _transition_to='PRE_EXPEDIENTE_DISCOVERY'
        AND tarifa_calculada / element_codes are NOT reset to empty.
        """
        from agent.tools.element_tools import identificar_y_resolver_elementos

        state = _make_tool_config(
            previous_categoria_slug="motos-part",
            categoria_slug="motos-part",
            precio_comunicado=True,
            tarifa_calculada={"precio_final": 350},
            element_codes=["LUNA_DEL"],
        )

        dummy_match = {
            "matches": [
                ({"code": "ESCAPE", "name": "Escape", "id": "esc-001"}, 0.92)
            ],
            "unmatched_terms": [],
            "ambiguous_candidates": [],
            "quantities": {},
        }

        with (
            patch("agent.tools.element_tools.get_tool_state", return_value=state),
            patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value="cat-uuid-motos",
            ),
            patch(
                "agent.tools.element_tools.get_element_service"
            ) as mock_elem_svc_factory,
            patch(
                "agent.tools.element_tools.get_tarifa_service"
            ) as mock_tarifa_svc_factory,
        ):
            elem_svc = AsyncMock()
            elem_svc.get_elements_by_category = AsyncMock(
                return_value=[{"code": "ESCAPE", "name": "Escape", "id": "esc-001"}]
            )
            elem_svc.match_elements_with_unmatched = AsyncMock(return_value=dummy_match)
            elem_svc.get_element_variants = AsyncMock(return_value=[])
            elem_svc.get_element_with_images = AsyncMock(return_value=None)
            elem_svc.get_element_warnings = AsyncMock(return_value=[])
            mock_elem_svc_factory.return_value = elem_svc

            tarifa_svc = AsyncMock()
            tarifa_svc.get_category_data = AsyncMock(return_value=None)
            mock_tarifa_svc_factory.return_value = tarifa_svc

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"},
                config=None,
            )

        state_update = _extract_state_update(result)

        assert state_update.get("_transition_to") != "PRE_EXPEDIENTE_DISCOVERY", (
            "When slug did not change, _transition_to must NOT be 'PRE_EXPEDIENTE_DISCOVERY'. "
            "Re-adding elements in same category must NOT trigger a reset. AC-3.5. "
            f"Got: {state_update.get('_transition_to')!r}"
        )


# ---------------------------------------------------------------------------
# D5 — AC-3.5 edge: no reset when previous_categoria_slug is None (first ID)
# ---------------------------------------------------------------------------


class TestNoResetOnFirstIdentification:
    """
    AC-3.5 edge case: when ``previous_categoria_slug`` is ``None`` (first
    identification in the conversation), there is no previous category to
    compare against, so NO reset cascade MUST fire.
    """

    async def test_no_reset_when_no_prior_slug_stored(self):
        """
        GIVEN mode_context has no previous_categoria_slug (None / absent)
        WHEN identificar_y_resolver_elementos resolves 'motos-part'
        THEN _state_update MUST NOT contain _transition_to='PRE_EXPEDIENTE_DISCOVERY'.

        This is the first-identification path — no category comparison possible.
        """
        from agent.tools.element_tools import identificar_y_resolver_elementos

        # previous_categoria_slug is deliberately absent (first ID)
        state = _make_tool_config(
            # previous_categoria_slug not set → defaults to None / absent
            categoria_slug=None,
        )

        dummy_match = {
            "matches": [
                ({"code": "ESCAPE", "name": "Escape", "id": "esc-001"}, 0.92)
            ],
            "unmatched_terms": [],
            "ambiguous_candidates": [],
            "quantities": {},
        }

        with (
            patch("agent.tools.element_tools.get_tool_state", return_value=state),
            patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value="cat-uuid-motos",
            ),
            patch(
                "agent.tools.element_tools.get_element_service"
            ) as mock_elem_svc_factory,
            patch(
                "agent.tools.element_tools.get_tarifa_service"
            ) as mock_tarifa_svc_factory,
        ):
            elem_svc = AsyncMock()
            elem_svc.get_elements_by_category = AsyncMock(
                return_value=[{"code": "ESCAPE", "name": "Escape", "id": "esc-001"}]
            )
            elem_svc.match_elements_with_unmatched = AsyncMock(return_value=dummy_match)
            elem_svc.get_element_variants = AsyncMock(return_value=[])
            elem_svc.get_element_with_images = AsyncMock(return_value=None)
            elem_svc.get_element_warnings = AsyncMock(return_value=[])
            mock_elem_svc_factory.return_value = elem_svc

            tarifa_svc = AsyncMock()
            tarifa_svc.get_category_data = AsyncMock(return_value=None)
            mock_tarifa_svc_factory.return_value = tarifa_svc

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"},
                config=None,
            )

        state_update = _extract_state_update(result)

        assert state_update.get("_transition_to") != "PRE_EXPEDIENTE_DISCOVERY", (
            "First identification (no prior slug) must NOT trigger reset. "
            "previous_categoria_slug=None means there is nothing to compare against. "
            f"Got _transition_to={state_update.get('_transition_to')!r}"
        )

    async def test_no_reset_when_prior_slug_explicitly_none(self):
        """
        TRIANGULATE: same as above but previous_categoria_slug is explicitly
        stored as None (not absent).

        GIVEN mode_context has previous_categoria_slug=None (explicit)
        WHEN identificar_y_resolver_elementos resolves 'motos-part'
        THEN NO reset MUST fire.
        """
        from agent.tools.element_tools import identificar_y_resolver_elementos

        state = _make_tool_config(
            previous_categoria_slug=None,
            categoria_slug=None,
        )

        dummy_match = {
            "matches": [({"code": "ESCAPE", "name": "Escape", "id": "esc-001"}, 0.92)],
            "unmatched_terms": [],
            "ambiguous_candidates": [],
            "quantities": {},
        }

        with (
            patch("agent.tools.element_tools.get_tool_state", return_value=state),
            patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value="cat-uuid-motos",
            ),
            patch(
                "agent.tools.element_tools.get_element_service"
            ) as mock_elem_svc_factory,
            patch(
                "agent.tools.element_tools.get_tarifa_service"
            ) as mock_tarifa_svc_factory,
        ):
            elem_svc = AsyncMock()
            elem_svc.get_elements_by_category = AsyncMock(
                return_value=[{"code": "ESCAPE", "name": "Escape", "id": "esc-001"}]
            )
            elem_svc.match_elements_with_unmatched = AsyncMock(return_value=dummy_match)
            elem_svc.get_element_variants = AsyncMock(return_value=[])
            elem_svc.get_element_with_images = AsyncMock(return_value=None)
            elem_svc.get_element_warnings = AsyncMock(return_value=[])
            mock_elem_svc_factory.return_value = elem_svc

            tarifa_svc = AsyncMock()
            tarifa_svc.get_category_data = AsyncMock(return_value=None)
            mock_tarifa_svc_factory.return_value = tarifa_svc

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"},
                config=None,
            )

        state_update = _extract_state_update(result)

        assert state_update.get("_transition_to") != "PRE_EXPEDIENTE_DISCOVERY", (
            "Explicit None for previous_categoria_slug must behave same as absent: "
            "no reset on first identification."
        )


# ---------------------------------------------------------------------------
# D7 — Audit trail: previous_categoria_slug in _state_update = old slug
# ---------------------------------------------------------------------------


class TestPreviousCategoriaSlugAuditTrail:
    """
    Audit trail requirement: when a category change is detected, the
    ``_state_update.shared_context.previous_categoria_slug`` MUST be set to
    the OLD slug value so that the next stored state has a record of what
    was changed from.

    This is the AC-3.1 audit requirement from the spec.
    """

    async def test_previous_slug_set_to_old_value_in_state_update(self):
        """
        GIVEN mode_context has previous_categoria_slug='motos-part'
        WHEN category changes to 'coches-part'
        THEN _state_update.shared_context.previous_categoria_slug MUST equal 'motos-part'
        AND _state_update.shared_context.categoria_slug MUST equal 'coches-part'.
        """
        from agent.tools.element_tools import identificar_y_resolver_elementos

        state = _make_tool_config(
            previous_categoria_slug="motos-part",
            categoria_slug="motos-part",
            precio_comunicado=True,
            element_codes=["LUNA_DEL"],
        )

        dummy_match = {
            "matches": [
                ({"code": "LUNA_DEL", "name": "Luna delantera", "id": "abc"}, 0.95)
            ],
            "unmatched_terms": [],
            "ambiguous_candidates": [],
            "quantities": {},
        }

        with (
            patch("agent.tools.element_tools.get_tool_state", return_value=state),
            patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value="cat-uuid-coches",
            ),
            patch(
                "agent.tools.element_tools.get_element_service"
            ) as mock_elem_svc_factory,
            patch(
                "agent.tools.element_tools.get_tarifa_service"
            ) as mock_tarifa_svc_factory,
        ):
            elem_svc = AsyncMock()
            elem_svc.get_elements_by_category = AsyncMock(
                return_value=[{"code": "LUNA_DEL", "name": "Luna delantera", "id": "abc"}]
            )
            elem_svc.match_elements_with_unmatched = AsyncMock(return_value=dummy_match)
            elem_svc.get_element_variants = AsyncMock(return_value=[])
            elem_svc.get_element_with_images = AsyncMock(return_value=None)
            elem_svc.get_element_warnings = AsyncMock(return_value=[])
            mock_elem_svc_factory.return_value = elem_svc

            tarifa_svc = AsyncMock()
            tarifa_svc.get_category_data = AsyncMock(return_value=None)
            mock_tarifa_svc_factory.return_value = tarifa_svc

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "coches-part", "descripcion": "luna delantera"},
                config=None,
            )

        shared = _extract_shared_context(result)

        assert shared.get("previous_categoria_slug") == "motos-part", (
            "Audit trail: previous_categoria_slug in _state_update must be set to "
            "the OLD slug value ('motos-part') so state history is preserved. "
            f"Got: {shared.get('previous_categoria_slug')!r}"
        )
        assert shared.get("categoria_slug") == "coches-part", (
            "Audit trail: categoria_slug in _state_update must be set to "
            "the NEW slug ('coches-part'). "
            f"Got: {shared.get('categoria_slug')!r}"
        )

    async def test_previous_slug_audit_trail_for_different_pair(self):
        """
        TRIANGULATE: different old/new pair to prevent hardcoded slug values.

        GIVEN previous='aseicars-part', new='motos-part'
        THEN previous_categoria_slug in _state_update = 'aseicars-part'
        AND categoria_slug in _state_update = 'motos-part'.
        """
        from agent.tools.element_tools import identificar_y_resolver_elementos

        state = _make_tool_config(
            previous_categoria_slug="aseicars-part",
            categoria_slug="aseicars-part",
            element_codes=["SOLAR_PANEL"],
        )

        dummy_match = {
            "matches": [({"code": "ESCAPE", "name": "Escape", "id": "esc-001"}, 0.90)],
            "unmatched_terms": [],
            "ambiguous_candidates": [],
            "quantities": {},
        }

        with (
            patch("agent.tools.element_tools.get_tool_state", return_value=state),
            patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value="cat-uuid-motos",
            ),
            patch(
                "agent.tools.element_tools.get_element_service"
            ) as mock_elem_svc_factory,
            patch(
                "agent.tools.element_tools.get_tarifa_service"
            ) as mock_tarifa_svc_factory,
        ):
            elem_svc = AsyncMock()
            elem_svc.get_elements_by_category = AsyncMock(
                return_value=[{"code": "ESCAPE", "name": "Escape", "id": "esc-001"}]
            )
            elem_svc.match_elements_with_unmatched = AsyncMock(return_value=dummy_match)
            elem_svc.get_element_variants = AsyncMock(return_value=[])
            elem_svc.get_element_with_images = AsyncMock(return_value=None)
            elem_svc.get_element_warnings = AsyncMock(return_value=[])
            mock_elem_svc_factory.return_value = elem_svc

            tarifa_svc = AsyncMock()
            tarifa_svc.get_category_data = AsyncMock(return_value=None)
            mock_tarifa_svc_factory.return_value = tarifa_svc

            result = await identificar_y_resolver_elementos.ainvoke(
                {"categoria_vehiculo": "motos-part", "descripcion": "escape"},
                config=None,
            )

        shared = _extract_shared_context(result)

        assert shared.get("previous_categoria_slug") == "aseicars-part", (
            "Audit trail must work for any slug pair, not just motos→coches."
        )
        assert shared.get("categoria_slug") == "motos-part"
