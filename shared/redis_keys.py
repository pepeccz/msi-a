"""
Centralized Redis key builder utility.

This module provides a standardized way to generate Redis keys across the
application, ensuring consistency and preventing typos.

Key naming convention::

    <domain>:<entity>:<id>[:<qualifier>]

TTL constants are defined alongside their keys so consumers don't have to
hard-code durations.
"""


class RedisKeyTTL:
    """Default TTL values (in seconds) for keys with expiration."""

    # Authentication
    JWT_BLACKLIST = 86_400  # 24 h — matches JWT token expiry

    # Chatwoot webhook idempotency
    IDEMPOTENCY_CHATWOOT = 300  # 5 min — duplicate webhook window

    # Image delivery idempotency
    # NOTE: These TTLs only protect against duplicate sends within a single retry attempt.
    # Longer TTLs cause silent blocks when the user legitimately requests images again
    # in a new conversation turn. The LLM-level guard (imagenes_enviadas flag in
    # image_tools.py) handles the case where the LLM tries to send images twice in
    # the same turn.
    IMAGE_DELIVERY_REQUEST = 120  # 2 min — covers system retry window
    IMAGE_DELIVERY_IMAGE = (
        30  # 30 s — prevents double-send within a single retry attempt
    )
    IMAGE_DELIVERY_OUTCOME = 86_400  # 24 h — outcome audit trail


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

    # -----------------------------------------------------------------------
    # Image delivery idempotency
    #
    # Two-level idempotency prevents duplicate sends at both the request
    # level (one call to enviar_imagenes_ejemplo) and the individual image
    # level (each Chatwoot upload within a request).
    #
    # Key schema:
    #   img_delivery:req:<conversation_id>:<request_id>                  → request-level
    #   img_delivery:img:<conversation_id>:<request_id>:<image_hash>     → image-level (request-scoped)
    #   img_delivery:outcome:<conversation_id>:<request_id>              → outcome audit
    #
    # TTLs are defined in RedisKeyTTL.
    # -----------------------------------------------------------------------

    @staticmethod
    def image_delivery_request(conversation_id: str, request_id: str) -> str:
        """Request-level idempotency key for an image delivery batch.

        Prevents the same ``delivery_request_id`` (generated per tool call)
        from being processed twice for the same conversation.

        TTL: ``RedisKeyTTL.IMAGE_DELIVERY_REQUEST`` (2 min).
        """
        return f"img_delivery:req:{conversation_id}:{request_id}"

    @staticmethod
    def image_delivery_image(
        conversation_id: str, delivery_request_id: str, image_hash: str
    ) -> str:
        """Per-image idempotency key scoped to a specific delivery request.

        ``delivery_request_id`` scopes the key to the current delivery request
        so that the same image can be re-sent in a new request (e.g. after a
        Redis restart reloads stale keys from RDB).

        ``image_hash`` should be a deterministic digest of the image URL
        (e.g. SHA-256 hex[:16]) so the same image is not uploaded twice
        within a single retry attempt.

        TTL: ``RedisKeyTTL.IMAGE_DELIVERY_IMAGE`` (30 s).
        """
        return f"img_delivery:img:{conversation_id}:{delivery_request_id}:{image_hash}"

    @staticmethod
    def image_delivery_outcome(conversation_id: str, request_id: str) -> str:
        """Stores the final delivery outcome for audit/debugging.

        Value should be a JSON-encoded ``ImageDeliveryOutcome`` dict.

        TTL: ``RedisKeyTTL.IMAGE_DELIVERY_OUTCOME`` (24 h).
        """
        return f"img_delivery:outcome:{conversation_id}:{request_id}"

    @staticmethod
    def image_delivery_pattern(conversation_id: str | None = None) -> str:
        """Pattern to match all image delivery keys, optionally scoped.

        Args:
            conversation_id: If provided, only keys for this conversation.
        """
        if conversation_id:
            return f"img_delivery:*:{conversation_id}:*"
        return "img_delivery:*"
