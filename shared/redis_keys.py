"""
Centralized Redis key builder utility.

This module provides a standardized way to generate Redis keys across the
application, ensuring consistency and preventing typos.
"""


class RedisKeys:
    """Centralized Redis key builder for consistent key naming."""

    # Authentication
    @staticmethod
    def jwt_blacklist(jti: str) -> str:
        """JWT token blacklist key."""
        return f"jwt_blacklist:{jti}"

    @staticmethod
    def idempotency_chatwoot(message_id: int) -> str:
        """Chatwoot message idempotency key."""
        return f"idempotency:chatwoot:{message_id}"

    # Element cache
    @staticmethod
    def elements_by_category(category_id: str, active: bool = True) -> str:
        """Elements filtered by category and active status."""
        return f"elements:category:{category_id}:active={active}"

    @staticmethod
    def elements_base_by_category(category_id: str, active: bool = True) -> str:
        """Base elements (no parent) filtered by category."""
        return f"elements:base:category:{category_id}:active={active}"

    @staticmethod
    def element_details(element_id: str, inherited: bool = True) -> str:
        """Element details with or without inherited data."""
        return f"element:details:{element_id}:inherited={inherited}"

    @staticmethod
    def tier_elements(tier_id: str) -> str:
        """Elements included in a tier."""
        return f"tier_elements:{tier_id}"

    # Tariff cache
    @staticmethod
    def tariff_by_category(category_slug: str) -> str:
        """Tariff data by category slug."""
        return f"tariffs:{category_slug}"

    @staticmethod
    def tariffs_supported(client_type: str) -> str:
        """Supported tariffs for client type (particular/professional)."""
        return f"tariffs:supported:{client_type}"

    @staticmethod
    def tariffs_categories_all() -> str:
        """All tariff categories."""
        return "tariffs:categories:all"

    @staticmethod
    def tariffs_categories_by_client(client_type: str) -> str:
        """Tariff categories for client type."""
        return f"tariffs:categories:{client_type}"

    # Prompt cache
    @staticmethod
    def prompt_calculator(category_slug: str) -> str:
        """Calculator prompt for category."""
        return f"prompt:calculator:{category_slug}"

    # RAG cache
    @staticmethod
    def rag_query(query_hash: str) -> str:
        """RAG query result cache."""
        return f"rag:query:{query_hash}"

    @staticmethod
    def rag_embedding(content_hash: str) -> str:
        """Embedding cache for content."""
        return f"emb:{content_hash}"

    # Settings cache
    @staticmethod
    def setting(key: str) -> str:
        """System setting cache."""
        return f"setting:{key}"

    # Pattern helpers for bulk operations
    @staticmethod
    def tariffs_pattern() -> str:
        """Pattern to match all tariff cache keys."""
        return "tariffs:*"

    @staticmethod
    def prompt_pattern() -> str:
        """Pattern to match all prompt cache keys."""
        return "prompt:*"

    @staticmethod
    def element_pattern() -> str:
        """Pattern to match all element cache keys."""
        return "element:*"

    @staticmethod
    def elements_pattern() -> str:
        """Pattern to match all elements list cache keys."""
        return "elements:*"
