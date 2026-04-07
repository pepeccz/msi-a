"""
Tests for ExpedienteState TypedDict and boundary mapping functions.

TDD Phase 1: State schema and bidirectional mapping.

Covers tasks:
- T-01 [RED] / T-02 [GREEN]: ExpedienteState TypedDict with ~40 keys
- T-03 [RED] / T-04 [GREEN]: parent_to_expediente() and expediente_to_parent_updates()
"""

from __future__ import annotations

import operator
from typing import Any, get_type_hints

import pytest


# ---------------------------------------------------------------------------
# T-01 / T-02: ExpedienteState TypedDict
# ---------------------------------------------------------------------------


class TestExpedienteStateSchema:
    """ExpedienteState TypedDict declares all ~40 required keys with correct reducers."""

    def test_module_importable(self) -> None:
        """agent.modes.expediente_state is importable (file exists)."""
        from agent.modes.expediente_state import ExpedienteState  # noqa: F401

    def test_all_required_keys_present(self) -> None:
        """All ~40 expediente-relevant keys are declared in ExpedienteState."""
        from agent.modes.expediente_state import ExpedienteState

        hints = get_type_hints(ExpedienteState, include_extras=True)

        required_keys = {
            # Identity (read-only from parent)
            "conversation_id",
            "user_id",
            "user_phone",
            "user_name",
            "client_type",
            # Routing
            "expediente_sub_mode",
            "user_message",
            "incoming_attachments",
            # Case identity
            "case_id",
            "category_id",
            "categoria_slug",
            "element_codes",
            "element_display_names",
            "tariff_tier_id",
            "tariff_amount",
            # Element collection
            "current_element_index",
            "current_element_code",
            "element_phase",
            "element_data_status",
            "element_data_all_collected",
            "current_element_field_keys",
            "element_states",
            "v2_collection_context",
            # Sub-mode data
            "base_docs_received",
            "base_doc_descriptions",
            "personal_data",
            "vehicle_data",
            "taller_propio",
            "taller_data",
            # Transition / continuity
            "expediente_transition_marker",
            "just_transitioned_from",
            "editing_from_review",
            "_review_fallback_count",
            "review_blocked_reason",
            # Coordinator signals
            "case_instructions",
            "expediente_intro_message",
            "expediente_intro_sent",
            "_guard_photo_fired_this_turn",
            "pending_recovery_case",
            "expediente_completed",
            "expediente_cancelled",
            # FSM compatibility
            "_fsm_state_init",
            # Inherited from PRESUPUESTO
            "tarifa_calculada",
            "precio_comunicado",
            "imagenes_enviadas",
            "vehiculo",
            "elementos_confirmados",
            # Output
            "ai_response",
            "pending_images",
            "messages",
        }

        missing = required_keys - set(hints.keys())
        assert not missing, f"ExpedienteState is missing keys: {sorted(missing)}"

    def test_messages_uses_operator_add_reducer(self) -> None:
        """messages field uses operator.add reducer (append-only)."""
        from agent.modes.expediente_state import ExpedienteState

        hints = get_type_hints(ExpedienteState, include_extras=True)
        messages_hint = hints["messages"]

        # Should be Annotated[..., operator.add]
        assert hasattr(messages_hint, "__metadata__"), (
            "messages must be Annotated with a reducer"
        )
        # The metadata should contain operator.add
        assert operator.add in messages_hint.__metadata__, (
            f"messages reducer must be operator.add, got {messages_hint.__metadata__}"
        )

    def test_tombstone_keys_are_declared_as_plain_fields(self) -> None:
        """
        Keys that previously needed tombstones in mode_context are declared as
        plain fields in ExpedienteState.

        Within the subgraph, ALL fields without reducers overwrite by default —
        so no special tombstone annotation is needed. This test verifies the keys
        ARE declared (not missing).

        These keys include: expediente_intro_message, case_instructions,
        _fsm_state_init, _review_fallback_count, pending_recovery_case,
        current_element_field_keys.
        """
        from agent.modes.expediente_state import ExpedienteState

        # These keys MUST be declared (existence check)
        tombstone_keys = {
            "expediente_intro_message",
            "case_instructions",
            "_fsm_state_init",
            "_review_fallback_count",
            "pending_recovery_case",
            "current_element_field_keys",
        }

        hints = get_type_hints(ExpedienteState, include_extras=True)

        for key in tombstone_keys:
            assert key in hints, (
                f"Key {key!r} not found in ExpedienteState — "
                "tombstone keys must still be declared in the schema"
            )

    def test_total_false(self) -> None:
        """ExpedienteState is total=False (all fields optional)."""
        from agent.modes.expediente_state import ExpedienteState

        assert not ExpedienteState.__required_keys__, (
            "ExpedienteState should have total=False (no required keys)"
        )

    def test_standard_keys_are_declared(self) -> None:
        """
        Standard keys (case_id, element_states, categoria_slug) are declared
        as plain fields with default overwrite semantics.
        """
        from agent.modes.expediente_state import ExpedienteState

        standard_keys = ["case_id", "element_states", "categoria_slug"]
        hints = get_type_hints(ExpedienteState, include_extras=True)

        for key in standard_keys:
            assert key in hints, f"Key {key!r} missing from ExpedienteState"

    def test_messages_reducer_triangulation(self) -> None:
        """
        Triangulation: messages is Annotated and ai_response is NOT Annotated.

        This verifies the annotated vs. plain split is correct.
        """
        from agent.modes.expediente_state import ExpedienteState

        hints = get_type_hints(ExpedienteState, include_extras=True)

        # messages MUST be Annotated (has __metadata__)
        messages_hint = hints["messages"]
        assert hasattr(messages_hint, "__metadata__"), "messages must be Annotated"

        # ai_response must NOT be Annotated (no reducer needed)
        ai_hint = hints["ai_response"]
        assert not hasattr(ai_hint, "__metadata__"), (
            "ai_response should be a plain field (no reducer annotation)"
        )


# ---------------------------------------------------------------------------
# T-03 / T-04: Boundary mapping functions
# ---------------------------------------------------------------------------


def _make_full_parent_state() -> dict[str, Any]:
    """Build a representative ConversationState dict with all expediente keys."""
    return {
        # Parent top-level identity
        "conversation_id": "conv-abc-123",
        "user_id": "user-uuid-456",
        "user_phone": "+34600111222",
        "user_name": "Juan García",
        "client_type": "particular",
        "user_message": "Hola, quiero saber el estado",
        "incoming_attachments": [
            {"type": "image", "url": "https://example.com/img.jpg"}
        ],
        # mode_context: all expediente-mode keys
        "mode_context": {
            # Case identity
            "case_id": "case-uuid-789",
            "category_id": "cat-uuid-abc",
            "categoria_slug": "motos-part",
            "element_codes": ["ESCAPE", "MANILLAR"],
            "element_display_names": {"ESCAPE": "Escape deportivo"},
            "tariff_tier_id": "tier-uuid-def",
            "tariff_amount": 410.0,
            # Element collection
            "current_element_index": 1,
            "current_element_code": "MANILLAR",
            "element_phase": "photos",
            "element_data_status": {"ESCAPE": "photos_done"},
            "element_data_all_collected": False,
            "current_element_field_keys": [{"field": "marca"}],
            "element_states": {"ESCAPE": {"phase": "complete"}},
            "v2_collection_context": {"version": 2},
            # Sub-mode data
            "base_docs_received": False,
            "base_doc_descriptions": ["ficha técnica"],
            "personal_data": {"nombre": "Juan García", "dni": None},
            "vehicle_data": {"marca": "Honda", "modelo": "CB500F"},
            "taller_propio": None,
            "taller_data": None,
            # Transition / continuity
            "expediente_transition_marker": {"from": "PRESUPUESTO"},
            "just_transitioned_from": "PRESUPUESTO_MODE",
            "editing_from_review": False,
            "_review_fallback_count": 0,
            "review_blocked_reason": None,
            # Coordinator signals
            "case_instructions": "Recopilar fotos de escape",
            "expediente_intro_message": None,
            "expediente_intro_sent": False,
            "_guard_photo_fired_this_turn": False,
            "pending_recovery_case": None,
            "expediente_completed": False,
            "expediente_cancelled": False,
            # FSM compatibility
            "_fsm_state_init": {"step": "collect_element_data"},
            # Inherited from PRESUPUESTO
            "tarifa_calculada": {"price": 410.0},
            "precio_comunicado": True,
            "imagenes_enviadas": False,
            "vehiculo": {"marca": "Honda", "modelo": "CB500F"},
            "elementos_confirmados": [{"code": "ESCAPE", "qty": 1}],
            # Sub-mode routing
            "expediente_sub_mode": "collect_element_data",
        },
        "current_mode": "EXPEDIENTE_MODE",
    }


class TestParentToExpediente:
    """parent_to_expediente() extracts all expediente keys from ConversationState."""

    def test_function_importable(self) -> None:
        from agent.modes.expediente_state import parent_to_expediente  # noqa: F401

    def test_extracts_top_level_identity_keys(self) -> None:
        """Top-level identity keys (conversation_id, user_phone, etc.) are mapped."""
        from agent.modes.expediente_state import parent_to_expediente

        parent = _make_full_parent_state()
        exp = parent_to_expediente(parent)

        assert exp["conversation_id"] == "conv-abc-123"
        assert exp["user_id"] == "user-uuid-456"
        assert exp["user_phone"] == "+34600111222"
        assert exp["user_name"] == "Juan García"
        assert exp["client_type"] == "particular"

    def test_extracts_user_message_and_attachments(self) -> None:
        """Transient turn data (user_message, incoming_attachments) is mapped."""
        from agent.modes.expediente_state import parent_to_expediente

        parent = _make_full_parent_state()
        exp = parent_to_expediente(parent)

        assert exp["user_message"] == "Hola, quiero saber el estado"
        assert exp["incoming_attachments"] == [
            {"type": "image", "url": "https://example.com/img.jpg"}
        ]

    def test_extracts_mode_context_case_keys(self) -> None:
        """Case identity keys from mode_context are mapped."""
        from agent.modes.expediente_state import parent_to_expediente

        parent = _make_full_parent_state()
        exp = parent_to_expediente(parent)

        assert exp["case_id"] == "case-uuid-789"
        assert exp["categoria_slug"] == "motos-part"
        assert exp["element_codes"] == ["ESCAPE", "MANILLAR"]
        assert exp["tariff_amount"] == 410.0

    def test_extracts_inherited_presupuesto_keys(self) -> None:
        """Keys inherited from PRESUPUESTO (tarifa_calculada, vehiculo, etc.) are mapped."""
        from agent.modes.expediente_state import parent_to_expediente

        parent = _make_full_parent_state()
        exp = parent_to_expediente(parent)

        assert exp["tarifa_calculada"] == {"price": 410.0}
        assert exp["precio_comunicado"] is True
        assert exp["vehiculo"] == {"marca": "Honda", "modelo": "CB500F"}
        assert exp["elementos_confirmados"] == [{"code": "ESCAPE", "qty": 1}]

    def test_messages_initialized_empty(self) -> None:
        """messages is initialized to [] — subgraph starts fresh each turn."""
        from agent.modes.expediente_state import parent_to_expediente

        parent = _make_full_parent_state()
        exp = parent_to_expediente(parent)

        assert exp.get("messages", []) == []

    def test_works_with_minimal_parent_state(self) -> None:
        """parent_to_expediente handles a minimal state dict without raising."""
        from agent.modes.expediente_state import parent_to_expediente

        minimal = {
            "conversation_id": "conv-minimal",
            "user_phone": "+34600000001",
            "mode_context": {},
        }
        exp = parent_to_expediente(minimal)
        # Must not raise; identity fields present
        assert exp["conversation_id"] == "conv-minimal"
        assert exp["user_phone"] == "+34600000001"


class TestExpedienteToParentUpdates:
    """expediente_to_parent_updates() converts subgraph output back to parent update dict."""

    def test_function_importable(self) -> None:
        from agent.modes.expediente_state import expediente_to_parent_updates  # noqa: F401

    def test_produces_ai_response_key(self) -> None:
        """The dict returned contains 'ai_response'."""
        from agent.modes.expediente_state import expediente_to_parent_updates

        exp_state: dict[str, Any] = {
            "ai_response": "Hola, continuamos con el expediente.",
            "case_id": "case-uuid-789",
            "expediente_sub_mode": "collect_element_data",
        }
        updates = expediente_to_parent_updates(exp_state)

        assert "ai_response" in updates
        assert updates["ai_response"] == "Hola, continuamos con el expediente."

    def test_produces_mode_context_key(self) -> None:
        """The dict returned contains 'mode_context' for parent merge."""
        from agent.modes.expediente_state import expediente_to_parent_updates

        exp_state: dict[str, Any] = {
            "ai_response": "Procesando...",
            "case_id": "case-uuid-789",
            "expediente_sub_mode": "collect_base_docs",
            "element_codes": ["ESCAPE"],
        }
        updates = expediente_to_parent_updates(exp_state)

        assert "mode_context" in updates
        mc = updates["mode_context"]
        assert isinstance(mc, dict)
        assert mc.get("case_id") == "case-uuid-789"
        assert mc.get("expediente_sub_mode") == "collect_base_docs"

    def test_pending_images_propagated(self) -> None:
        """pending_images is passed through to parent updates."""
        from agent.modes.expediente_state import expediente_to_parent_updates

        exp_state: dict[str, Any] = {
            "ai_response": "Enviando imágenes...",
            "pending_images": {"scope": "ESCAPE", "request_id": "req-123"},
        }
        updates = expediente_to_parent_updates(exp_state)

        assert updates.get("pending_images") == {
            "scope": "ESCAPE",
            "request_id": "req-123",
        }


class TestRoundTrip:
    """Round-trip: parent_to_expediente → expediente_to_parent_updates preserves all keys."""

    def test_case_id_preserved_in_round_trip(self) -> None:
        """case_id survives the full round-trip (parent → exp → parent_updates)."""
        from agent.modes.expediente_state import (
            expediente_to_parent_updates,
            parent_to_expediente,
        )

        parent = _make_full_parent_state()
        exp = parent_to_expediente(parent)
        # Simulate node writing ai_response
        exp["ai_response"] = "Respuesta del agente."
        updates = expediente_to_parent_updates(exp)

        assert updates["mode_context"].get("case_id") == "case-uuid-789"

    def test_all_mode_context_keys_survive_round_trip(self) -> None:
        """All mode_context keys survive the full round-trip."""
        from agent.modes.expediente_state import (
            expediente_to_parent_updates,
            parent_to_expediente,
        )

        parent = _make_full_parent_state()
        original_mc = dict(parent["mode_context"])

        exp = parent_to_expediente(parent)
        exp["ai_response"] = "Respuesta."
        updates = expediente_to_parent_updates(exp)

        returned_mc = updates["mode_context"]

        # Every key from original mode_context should be in the returned mc
        for key, value in original_mc.items():
            assert key in returned_mc, (
                f"Key {key!r} lost during round-trip. "
                f"Returned keys: {sorted(returned_mc.keys())}"
            )
            assert returned_mc[key] == value, (
                f"Key {key!r} changed during round-trip. "
                f"Expected {value!r}, got {returned_mc[key]!r}"
            )

    def test_unknown_key_not_lost(self) -> None:
        """An undeclared runtime key present in mode_context is preserved."""
        from agent.modes.expediente_state import (
            expediente_to_parent_updates,
            parent_to_expediente,
        )

        parent = _make_full_parent_state()
        # Inject an unknown runtime key
        parent["mode_context"]["_undeclared_future_key"] = "some_value"

        exp = parent_to_expediente(parent)
        exp["ai_response"] = "Test."
        updates = expediente_to_parent_updates(exp)

        assert updates["mode_context"].get("_undeclared_future_key") == "some_value", (
            "Unknown runtime keys must not be silently dropped"
        )
