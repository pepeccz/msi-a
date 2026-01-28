"""
Tests for agent/nodes/process_message.py

Tests cover:
- Normal message flow
- Panic button handling
- Escalation creation
- Conversation history upsert
- Parallel I/O execution

These tests validate the refactored process_incoming_message_node
which was optimized in 2026-01 to:
- Remove redundant Chatwoot atencion_automatica check
- Parallelize independent I/O operations
- Optimize conversation history upsert
"""

import pytest
import uuid
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch, MagicMock

from agent.nodes.process_message import (
    process_incoming_message_node,
    handle_panic_button,
    upsert_conversation_history,
    create_escalation_if_needed,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def base_state():
    """Create a base conversation state for testing."""
    return {
        "conversation_id": "12345",
        "user_message": "Hola, necesito homologar mi moto",
        "messages": [],
        "total_message_count": 0,
        "user_phone": "+34612345678",
        "user_id": str(uuid.uuid4()),
    }


@pytest.fixture
def state_with_messages():
    """Create state with existing messages (not first interaction)."""
    return {
        "conversation_id": "12345",
        "user_message": "Quiero homologar un escape",
        "messages": [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "¡Hola! ¿En qué puedo ayudarte?"},
        ],
        "total_message_count": 2,
        "user_phone": "+34612345678",
        "user_id": str(uuid.uuid4()),
    }


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_chatwoot_client():
    """Create a mock Chatwoot client."""
    client = AsyncMock()
    client.update_conversation_attributes = AsyncMock(return_value=True)
    client.send_message = AsyncMock(return_value={"id": 123})
    client.add_labels = AsyncMock(return_value=True)
    client.add_private_note = AsyncMock(return_value=True)
    return client


# =============================================================================
# TESTS: process_incoming_message_node
# =============================================================================


class TestProcessIncomingMessageNode:
    """Tests for the main process_incoming_message_node function."""

    async def test_normal_flow_adds_message(self, base_state):
        """Normal message should be added to history."""
        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value="true"),  # Agent enabled
        ), patch(
            "agent.nodes.process_message.upsert_conversation_history",
            AsyncMock(return_value=None),
        ):
            result = await process_incoming_message_node(base_state)

            # Verify message was added
            assert len(result["messages"]) == 1
            assert result["messages"][0]["role"] == "user"
            assert result["messages"][0]["content"] == base_state["user_message"]

            # Verify other state updates
            assert result["total_message_count"] == 1
            assert result["agent_disabled"] is False
            assert result["last_node"] == "process_incoming_message"

    async def test_first_interaction_sets_greeting_state(self, base_state):
        """First message should set current_state to 'greeting' and created_at."""
        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value="true"),
        ), patch(
            "agent.nodes.process_message.upsert_conversation_history",
            AsyncMock(return_value=None),
        ):
            result = await process_incoming_message_node(base_state)

            assert result["is_first_interaction"] is True
            assert result["current_state"] == "greeting"
            assert "created_at" in result
            assert isinstance(result["created_at"], datetime)

    async def test_subsequent_message_not_first_interaction(self, state_with_messages):
        """Subsequent messages should not be marked as first interaction."""
        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value="true"),
        ), patch(
            "agent.nodes.process_message.upsert_conversation_history",
            AsyncMock(return_value=None),
        ):
            result = await process_incoming_message_node(state_with_messages)

            assert result["is_first_interaction"] is False
            assert "current_state" not in result  # Only set on first interaction
            assert "created_at" not in result

    async def test_panic_button_returns_early(self, base_state):
        """When agent disabled, should return without adding message."""
        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value="false"),  # Agent DISABLED
        ), patch(
            "agent.nodes.process_message.upsert_conversation_history",
            AsyncMock(return_value=None),
        ), patch(
            "agent.nodes.process_message.handle_panic_button",
            AsyncMock(return_value={
                "messages": [],
                "agent_disabled": True,
                "last_node": "agent_disabled_response",
            }),
        ) as mock_panic:
            result = await process_incoming_message_node(base_state)

            # Verify panic button handler was called
            mock_panic.assert_called_once()

            # Verify result matches panic button response
            assert result["agent_disabled"] is True
            assert result["last_node"] == "agent_disabled_response"

    async def test_parallel_io_execution(self, base_state):
        """Verify asyncio.gather is used for parallel I/O."""
        gather_called = False

        async def mock_gather(*coros):
            nonlocal gather_called
            gather_called = True
            results = []
            for coro in coros:
                results.append(await coro)
            return results

        with patch(
            "agent.nodes.process_message.asyncio.gather",
            side_effect=mock_gather,
        ), patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value="true"),
        ), patch(
            "agent.nodes.process_message.upsert_conversation_history",
            AsyncMock(return_value=None),
        ):
            await process_incoming_message_node(base_state)

            # asyncio.gather should have been called
            assert gather_called is True

    async def test_clears_pending_images(self, base_state):
        """Should clear pending_images to prevent duplicates."""
        base_state["pending_images"] = [{"url": "http://example.com/img.jpg"}]

        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value="true"),
        ), patch(
            "agent.nodes.process_message.upsert_conversation_history",
            AsyncMock(return_value=None),
        ):
            result = await process_incoming_message_node(base_state)

            assert result["pending_images"] == []

    async def test_handles_empty_user_message(self, base_state):
        """Should handle empty or None user message gracefully."""
        base_state["user_message"] = ""

        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value="true"),
        ), patch(
            "agent.nodes.process_message.upsert_conversation_history",
            AsyncMock(return_value=None),
        ):
            result = await process_incoming_message_node(base_state)

            assert result["messages"][0]["content"] == ""


# =============================================================================
# TESTS: handle_panic_button
# =============================================================================


class TestHandlePanicButton:
    """Tests for panic button handling."""

    async def test_sends_disabled_message(self, base_state):
        """Should publish auto-response message via Redis."""
        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value=None),  # No custom message
        ), patch(
            "agent.nodes.process_message.publish_to_channel",
            AsyncMock(return_value=None),
        ) as mock_publish, patch(
            "agent.nodes.process_message.create_escalation_if_needed",
            AsyncMock(return_value=None),
        ):
            result = await handle_panic_button(
                conversation_id="12345",
                state=base_state,
                messages=[],
            )

            # Verify publish was called with correct channel
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] == "outgoing_messages"
            assert call_args[0][1]["conversation_id"] == "12345"
            assert "message" in call_args[0][1]

    async def test_creates_escalation(self, base_state):
        """Should call create_escalation_if_needed."""
        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value=None),
        ), patch(
            "agent.nodes.process_message.publish_to_channel",
            AsyncMock(return_value=None),
        ), patch(
            "agent.nodes.process_message.create_escalation_if_needed",
            AsyncMock(return_value=None),
        ) as mock_escalation:
            await handle_panic_button(
                conversation_id="12345",
                state=base_state,
                messages=[],
            )

            mock_escalation.assert_called_once_with("12345", base_state)

    async def test_uses_custom_disabled_message(self, base_state):
        """Should use custom message from settings if available."""
        custom_message = "Mensaje personalizado de mantenimiento"

        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value=custom_message),
        ), patch(
            "agent.nodes.process_message.publish_to_channel",
            AsyncMock(return_value=None),
        ) as mock_publish, patch(
            "agent.nodes.process_message.create_escalation_if_needed",
            AsyncMock(return_value=None),
        ):
            await handle_panic_button(
                conversation_id="12345",
                state=base_state,
                messages=[],
            )

            # Verify custom message was used
            call_args = mock_publish.call_args
            assert call_args[0][1]["message"] == custom_message

    async def test_returns_correct_state_updates(self, base_state):
        """Should return correct state updates for panic button."""
        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value=None),
        ), patch(
            "agent.nodes.process_message.publish_to_channel",
            AsyncMock(return_value=None),
        ), patch(
            "agent.nodes.process_message.create_escalation_if_needed",
            AsyncMock(return_value=None),
        ):
            result = await handle_panic_button(
                conversation_id="12345",
                state=base_state,
                messages=[{"role": "user", "content": "test"}],
            )

            assert result["agent_disabled"] is True
            assert result["pending_images"] == []
            assert result["last_node"] == "agent_disabled_response"
            assert "updated_at" in result
            # Messages should NOT include the new message
            assert result["messages"] == [{"role": "user", "content": "test"}]


# =============================================================================
# TESTS: upsert_conversation_history
# =============================================================================


class TestUpsertConversationHistory:
    """Tests for conversation history upsert using ON CONFLICT DO UPDATE."""

    async def test_executes_upsert_statement(self, mock_db_session):
        """Should execute upsert statement with ON CONFLICT."""
        mock_db_session.execute = AsyncMock(return_value=MagicMock())

        with patch(
            "agent.nodes.process_message.get_async_session",
            return_value=mock_db_session,
        ):
            await upsert_conversation_history(
                conversation_id="12345",
                user_id=str(uuid.uuid4()),
            )

            # Verify execute was called (upsert statement)
            mock_db_session.execute.assert_called_once()
            # Verify commit was called
            mock_db_session.commit.assert_called_once()

    async def test_handles_db_error_gracefully(self, mock_db_session):
        """Should log error but not raise exception."""
        mock_db_session.execute = AsyncMock(
            side_effect=Exception("Database connection error")
        )

        with patch(
            "agent.nodes.process_message.get_async_session",
            return_value=mock_db_session,
        ), patch(
            "agent.nodes.process_message.logger"
        ) as mock_logger:
            # Should not raise
            await upsert_conversation_history(
                conversation_id="12345",
                user_id=str(uuid.uuid4()),
            )

            # Should log error
            mock_logger.error.assert_called_once()

    async def test_handles_none_user_id(self, mock_db_session):
        """Should handle None user_id gracefully."""
        mock_db_session.execute = AsyncMock(return_value=MagicMock())

        with patch(
            "agent.nodes.process_message.get_async_session",
            return_value=mock_db_session,
        ):
            # Should not raise with None user_id
            await upsert_conversation_history(
                conversation_id="12345",
                user_id=None,
            )

            mock_db_session.execute.assert_called_once()
            mock_db_session.commit.assert_called_once()


# =============================================================================
# TESTS: create_escalation_if_needed
# =============================================================================


class TestCreateEscalationIfNeeded:
    """Tests for escalation creation."""

    async def test_creates_escalation_when_none_exists(
        self, base_state, mock_db_session, mock_chatwoot_client
    ):
        """Should create new escalation when none exists."""
        # Mock: no existing escalation
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "agent.nodes.process_message.get_async_session",
            return_value=mock_db_session,
        ), patch(
            "agent.nodes.process_message.ChatwootClient",
            return_value=mock_chatwoot_client,
        ):
            await create_escalation_if_needed("12345", base_state)

            # Verify escalation was added
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called()

    async def test_skips_if_escalation_exists(
        self, base_state, mock_db_session, mock_chatwoot_client
    ):
        """Should not create duplicate escalation."""
        # Mock: existing escalation found
        existing_escalation = MagicMock()
        existing_escalation.id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=existing_escalation)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "agent.nodes.process_message.get_async_session",
            return_value=mock_db_session,
        ):
            await create_escalation_if_needed("12345", base_state)

            # Verify NO new escalation was added
            mock_db_session.add.assert_not_called()

    async def test_updates_chatwoot_on_escalation(
        self, base_state, mock_db_session, mock_chatwoot_client
    ):
        """Should disable bot and notify user in Chatwoot."""
        # Mock: no existing escalation
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock escalation with ID for refresh
        mock_escalation = MagicMock()
        mock_escalation.id = uuid.uuid4()
        mock_db_session.refresh = AsyncMock()

        with patch(
            "agent.nodes.process_message.get_async_session",
            return_value=mock_db_session,
        ), patch(
            "agent.nodes.process_message.ChatwootClient",
            return_value=mock_chatwoot_client,
        ):
            await create_escalation_if_needed("12345", base_state)

            # Verify Chatwoot was updated
            mock_chatwoot_client.update_conversation_attributes.assert_called_once()
            call_args = mock_chatwoot_client.update_conversation_attributes.call_args
            assert call_args[1]["attributes"]["atencion_automatica"] is False

            # Verify message was sent
            mock_chatwoot_client.send_message.assert_called_once()

    async def test_handles_chatwoot_error_gracefully(
        self, base_state, mock_db_session, mock_chatwoot_client
    ):
        """Should continue even if Chatwoot update fails."""
        # Mock: no existing escalation
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock Chatwoot failure
        mock_chatwoot_client.update_conversation_attributes = AsyncMock(
            side_effect=Exception("Chatwoot API error")
        )

        with patch(
            "agent.nodes.process_message.get_async_session",
            return_value=mock_db_session,
        ), patch(
            "agent.nodes.process_message.ChatwootClient",
            return_value=mock_chatwoot_client,
        ), patch(
            "agent.nodes.process_message.logger"
        ) as mock_logger:
            # Should not raise
            await create_escalation_if_needed("12345", base_state)

            # Escalation should still be created
            mock_db_session.add.assert_called_once()

            # Error should be logged
            mock_logger.error.assert_called()


# =============================================================================
# TESTS: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_invalid_conversation_id_format(self, base_state):
        """Should handle non-integer conversation_id in escalation."""
        base_state["conversation_id"] = "not-an-integer"

        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value="true"),
        ), patch(
            "agent.nodes.process_message.upsert_conversation_history",
            AsyncMock(return_value=None),
        ):
            # Should not raise
            result = await process_incoming_message_node(base_state)
            assert result is not None

    async def test_missing_state_fields(self):
        """Should handle missing optional state fields."""
        minimal_state = {
            "conversation_id": "12345",
        }

        with patch(
            "agent.nodes.process_message.get_cached_setting",
            AsyncMock(return_value="true"),
        ), patch(
            "agent.nodes.process_message.upsert_conversation_history",
            AsyncMock(return_value=None),
        ):
            result = await process_incoming_message_node(minimal_state)

            # Should use defaults
            assert result["messages"][0]["content"] == ""
            assert result["total_message_count"] == 1
