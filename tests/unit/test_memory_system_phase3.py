"""
Tests for Phase 3 of memory system refactor (refactor-memory-system).

Covers:
- WS3: User profile Store — load, save, merge, round-trip
- WS3: Profile load in preprocess_node (via store injection)
- WS3: Profile save in maybe_summarize (periodic)
"""

import pytest
from langgraph.store.memory import InMemoryStore

from agent.graph.user_profile_store import (
    NS_USERS,
    PROFILE_KEY,
    load_user_profile,
    save_user_profile,
)


# ---------------------------------------------------------------------------
# load_user_profile / save_user_profile
# ---------------------------------------------------------------------------


class TestLoadUserProfile:
    """Tests for loading user profile from Store."""

    @pytest.mark.asyncio
    async def test_profile_found(self):
        store = InMemoryStore()
        await store.aput(
            (NS_USERS, "+34612345678"),
            PROFILE_KEY,
            {"user_name": "Carlos", "client_type": "particular"},
        )

        profile = await load_user_profile(store, "+34612345678")
        assert profile is not None
        assert profile["user_name"] == "Carlos"
        assert profile["client_type"] == "particular"

    @pytest.mark.asyncio
    async def test_profile_not_found(self):
        store = InMemoryStore()
        profile = await load_user_profile(store, "+34999999999")
        assert profile is None

    @pytest.mark.asyncio
    async def test_no_store(self):
        profile = await load_user_profile(None, "+34612345678")
        assert profile is None

    @pytest.mark.asyncio
    async def test_no_phone(self):
        store = InMemoryStore()
        profile = await load_user_profile(store, "")
        assert profile is None


class TestSaveUserProfile:
    """Tests for saving user profile to Store."""

    @pytest.mark.asyncio
    async def test_save_basic_identity(self):
        store = InMemoryStore()
        state = {
            "user_name": "María",
            "client_type": "professional",
            "user_id": "uuid-123",
            "user_phone": "+34612345678",
            "mode_context": {},
        }
        await save_user_profile(store, "+34612345678", state)

        profile = await load_user_profile(store, "+34612345678")
        assert profile is not None
        assert profile["user_name"] == "María"
        assert profile["client_type"] == "professional"
        assert profile["user_id"] == "uuid-123"
        assert "first_seen" in profile
        assert "last_seen" in profile

    @pytest.mark.asyncio
    async def test_save_merges_with_existing(self):
        store = InMemoryStore()

        # First save
        await save_user_profile(store, "+34612345678", {
            "user_name": "Carlos",
            "client_type": "particular",
            "mode_context": {},
        })

        # Second save with different data
        await save_user_profile(store, "+34612345678", {
            "user_name": "Carlos López",
            "mode_context": {},
        })

        profile = await load_user_profile(store, "+34612345678")
        assert profile["user_name"] == "Carlos López"  # Updated
        assert profile["client_type"] == "particular"  # Preserved from first save

    @pytest.mark.asyncio
    async def test_save_quote_history(self):
        store = InMemoryStore()
        state = {
            "user_name": "Carlos",
            "user_phone": "+34612345678",
            "mode_context": {
                "tarifa_calculada": {"datos": {"price": 410}},
                "precio_comunicado": True,
                "element_codes": ["ESCAPE", "SUSPENSION"],
            },
        }
        await save_user_profile(store, "+34612345678", state)

        profile = await load_user_profile(store, "+34612345678")
        assert len(profile["past_quotes"]) == 1
        assert profile["past_quotes"][0]["price"] == 410
        assert profile["past_quotes"][0]["elements"] == ["ESCAPE", "SUSPENSION"]

    @pytest.mark.asyncio
    async def test_quote_history_capped_at_5(self):
        store = InMemoryStore()
        for i in range(7):
            state = {
                "mode_context": {
                    "tarifa_calculada": {"datos": {"price": 100 + i}},
                    "precio_comunicado": True,
                    "element_codes": [f"ELEMENT_{i}"],
                },
            }
            await save_user_profile(store, "+34612345678", state)

        profile = await load_user_profile(store, "+34612345678")
        assert len(profile["past_quotes"]) == 5
        # Should keep the LAST 5
        assert profile["past_quotes"][0]["price"] == 102

    @pytest.mark.asyncio
    async def test_save_expediente_history(self):
        store = InMemoryStore()
        state = {
            "user_name": "Carlos",
            "mode_context": {
                "case_id": "case-abc",
                "element_codes": ["ESCAPE"],
            },
        }
        await save_user_profile(store, "+34612345678", state)

        profile = await load_user_profile(store, "+34612345678")
        assert len(profile["past_expedientes"]) == 1
        assert profile["past_expedientes"][0]["case_id"] == "case-abc"

    @pytest.mark.asyncio
    async def test_no_duplicate_expediente(self):
        """Same case_id should not be added twice."""
        store = InMemoryStore()
        state = {
            "mode_context": {
                "case_id": "case-abc",
                "element_codes": ["ESCAPE"],
            },
        }
        await save_user_profile(store, "+34612345678", state)
        await save_user_profile(store, "+34612345678", state)

        profile = await load_user_profile(store, "+34612345678")
        assert len(profile["past_expedientes"]) == 1

    @pytest.mark.asyncio
    async def test_no_store_noop(self):
        """No error when store is None."""
        await save_user_profile(None, "+34612345678", {"user_name": "Test"})

    @pytest.mark.asyncio
    async def test_no_phone_noop(self):
        """No error when phone is empty."""
        store = InMemoryStore()
        await save_user_profile(store, "", {"user_name": "Test"})


# ---------------------------------------------------------------------------
# Round-trip: save then load across "conversations"
# ---------------------------------------------------------------------------


class TestStoreRoundTrip:
    """Test cross-thread profile persistence."""

    @pytest.mark.asyncio
    async def test_profile_survives_across_threads(self):
        """User profile saved in thread A is available in thread B."""
        store = InMemoryStore()

        # Thread A: user provides data
        await save_user_profile(store, "+34612345678", {
            "user_name": "Carlos",
            "client_type": "particular",
            "mode_context": {
                "tarifa_calculada": {"datos": {"price": 410}},
                "precio_comunicado": True,
                "element_codes": ["ESCAPE"],
            },
        })

        # Thread B: new conversation, load profile
        profile = await load_user_profile(store, "+34612345678")
        assert profile is not None
        assert profile["user_name"] == "Carlos"
        assert len(profile["past_quotes"]) == 1
        assert profile["past_quotes"][0]["price"] == 410

    @pytest.mark.asyncio
    async def test_different_users_isolated(self):
        """Different phone numbers have separate profiles."""
        store = InMemoryStore()

        await save_user_profile(store, "+34111111111", {"user_name": "Carlos", "mode_context": {}})
        await save_user_profile(store, "+34222222222", {"user_name": "María", "mode_context": {}})

        p1 = await load_user_profile(store, "+34111111111")
        p2 = await load_user_profile(store, "+34222222222")

        assert p1["user_name"] == "Carlos"
        assert p2["user_name"] == "María"
