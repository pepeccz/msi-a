"""
Configuration module - Central access point for environment variables.

CRITICAL: Access ALL environment variables through this module.
NEVER use os.getenv() directly in application code.
"""

__all__ = [
    "Settings",
    "get_settings",
    "QUANTITY_PATTERNS",
    "NEGATION_PATTERNS",
]

from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Project
    PROJECT_NAME: str = Field(
        default="MSI Automotive", description="Project name displayed in UI and logs"
    )
    AGENT_NAME: str = Field(default="MSI-a", description="Name of the AI agent")
    ENVIRONMENT: str = Field(
        default="development",
        description="Environment: development, staging, production",
    )

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://msia:changeme@postgres:5432/msia_db",
        description="PostgreSQL connection string with asyncpg driver",
    )
    POSTGRES_DB: str = Field(default="msia_db")
    POSTGRES_USER: str = Field(default="msia")
    POSTGRES_PASSWORD: str = Field(default="changeme")
    POSTGRES_HOST: str = Field(default="postgres")
    POSTGRES_PORT: int = Field(default=5432)

    # Redis
    REDIS_URL: str = Field(
        default="redis://redis:6379/0", description="Redis connection string"
    )
    REDIS_PASSWORD: str = Field(
        default="",
        description="Redis password for authentication (required in production)",
    )
    USE_REDIS_STREAMS: bool = Field(
        default=True,
        description="Use Redis Streams instead of Pub/Sub for message delivery",
    )

    # Checkpoint TTL by conversation mode (minutes)
    CHECKPOINT_TTL_DEFAULT_MINUTES: int = Field(
        default=1440,
        description="Default checkpoint TTL in minutes (24h) — applies when no mode matches",
    )
    CHECKPOINT_TTL_CONSULTA_MINUTES: int = Field(
        default=60,
        description="Consulta mode checkpoint TTL in minutes (1h) — short-lived educational queries",
    )
    CHECKPOINT_TTL_PRESUPUESTO_MINUTES: int = Field(
        default=240,
        description="Presupuesto mode checkpoint TTL in minutes (4h) — active pricing sessions",
    )
    CHECKPOINT_TTL_EXPEDIENTE_MINUTES: int = Field(
        default=10080,
        description="Expediente mode checkpoint TTL in minutes (7d) — formal case collection",
    )
    CHECKPOINT_TTL_ESCALATION_MINUTES: int = Field(
        default=120,
        description="Escalation mode checkpoint TTL in minutes (2h) — human handoff sessions",
    )

    # Chatwoot
    CHATWOOT_API_URL: str = Field(default="https://app.chatwoot.com")
    CHATWOOT_API_TOKEN: str = Field(default="placeholder")
    CHATWOOT_ACCOUNT_ID: str = Field(default="12345")
    CHATWOOT_INBOX_ID: str = Field(default="67890")
    CHATWOOT_TEAM_GROUP_ID: int | None = Field(
        default=None,
        description="Chatwoot team ID for assignment on escalation (None = disabled)",
    )
    CHATWOOT_WEBHOOK_TOKEN: str = Field(
        default="chatwoot_webhook_token_placeholder",
        description="Secret token for Chatwoot webhook URL authentication",
    )
    CHATWOOT_STORAGE_DOMAIN: str = Field(
        default="",
        description="Domain for Chatwoot active_storage URLs (e.g., chats.autohomologacion.net)",
    )
    CHATWOOT_IMAGE_SEND_DELAY_SECONDS: float = Field(
        default=5.0,
        ge=0.0,
        description=(
            "Unified delay in seconds between consecutive images and before "
            "the post-image text message in batched sends to preserve "
            "WhatsApp delivery ordering"
        ),
    )

    # OpenRouter (Unified LLM API)
    OPENROUTER_API_KEY: str = Field(default="sk-or-placeholder")
    LLM_MODEL: str = Field(
        default="deepseek/deepseek-chat",
        description="AI model for conversations (OpenRouter format). DeepSeek recommended for better reasoning and lower cost.",
    )
    SITE_URL: str = Field(
        default="https://msiautomotive.es",
        description="Site URL for OpenRouter rankings",
    )
    SITE_NAME: str = Field(
        default="MSI Automotive", description="Site name for OpenRouter rankings"
    )

    # Application Settings
    TIMEZONE: str = Field(default="Europe/Madrid")
    LOG_LEVEL: str = Field(default="INFO")
    MESSAGE_BATCH_WINDOW_SECONDS: int = Field(
        default=30, ge=0, le=120, description="Message batching window in seconds"
    )

    # Image Storage
    IMAGE_UPLOAD_DIR: str = Field(
        default="./uploads/images", description="Directory for storing uploaded images"
    )
    IMAGE_BASE_URL: str = Field(
        default="/images", description="Base URL path for serving images"
    )
    IMAGE_MAX_SIZE_MB: int = Field(default=10, description="Maximum upload size in MB")

    # Case Images Storage
    CASE_IMAGES_DIR: str = Field(
        default="./uploads/case_images",
        description="Directory for storing case/expediente images",
    )
    CASE_IMAGES_BASE_URL: str = Field(
        default="/case-images", description="Base URL path for serving case images"
    )
    CASE_IMAGES_MAX_SIZE_MB: int = Field(
        default=15, description="Maximum case image size in MB"
    )

    # Image Security
    MAX_IMAGES_PER_CASE: int = Field(
        default=50, description="Maximum number of images allowed per case/expediente"
    )
    IMAGE_UPLOAD_RATE_LIMIT: int = Field(
        default=10, description="Maximum image uploads per minute per user"
    )

    # API Base URL (for generating absolute URLs for external services like Chatwoot)
    API_BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Public base URL of the API server (for generating absolute image URLs)",
    )

    # Admin Panel Authentication
    ADMIN_USERNAME: str = Field(default="admin", description="Admin panel username")
    ADMIN_PASSWORD: str = Field(
        default="", description="Admin panel password in plain text (DEPRECATED)"
    )
    ADMIN_PASSWORD_HASH: str = Field(
        default="", description="Bcrypt hash of admin password"
    )
    ADMIN_JWT_SECRET: str = Field(
        default="",
        description="JWT secret key for admin panel authentication (min 32 chars)",
    )

    # CORS Origins for API
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000,http://localhost:8001,http://api:8000",
        description="Comma-separated list of allowed origins for CORS",
    )

    # RAG System - Qdrant
    QDRANT_URL: str = Field(
        default="http://qdrant:6333", description="Qdrant vector database URL"
    )
    QDRANT_API_KEY: str | None = Field(
        default=None, description="Qdrant API key (optional, for cloud deployments)"
    )
    QDRANT_COLLECTION_NAME: str = Field(
        default="msi_regulatory_docs",
        description="Name of the Qdrant collection for regulatory documents",
    )

    # RAG System - Ollama Embeddings
    OLLAMA_BASE_URL: str = Field(
        default="http://ollama:11434", description="Ollama server URL for embeddings"
    )
    EMBEDDING_MODEL: str = Field(
        default="nomic-embed-text", description="Embedding model name in Ollama"
    )
    EMBEDDING_DIMENSION: int = Field(
        default=768, description="Embedding vector dimension"
    )

    # RAG System - Re-ranking
    BGE_RERANKER_MODEL: str = Field(
        default="BAAI/bge-reranker-large",
        description="BGE re-ranker model for result re-ranking",
    )

    # RAG System - Query Parameters
    RAG_TOP_K: int = Field(
        default=30,
        description="Number of initial results to retrieve from vector search",
    )
    RAG_RERANK_TOP_K: int = Field(
        default=8, description="Number of results after re-ranking"
    )
    RAG_CHUNK_SIZE: int = Field(
        default=800, description="Target chunk size in characters"
    )
    RAG_CHUNK_OVERLAP: int = Field(
        default=200, description="Chunk overlap in characters"
    )
    RAG_CACHE_TTL: int = Field(
        default=3600, description="Query result cache TTL in seconds"
    )

    # RAG System - Document Storage
    DOCUMENT_UPLOAD_DIR: str = Field(
        default="/app/uploads/documents",
        description="Directory for storing uploaded regulatory documents",
    )
    DOCUMENT_MAX_SIZE_MB: int = Field(
        default=50, description="Maximum document upload size in MB"
    )

    # RAG System - LLM Fallback
    RAG_LLM_FALLBACK_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Local Ollama model for LLM fallback (lightweight)",
    )

    # ==========================================================================
    # LLM Timeout & Retry Defense
    # ==========================================================================

    LLM_REQUEST_TIMEOUT_SECONDS: int = Field(
        default=120,
        description="HTTP timeout for individual LLM API calls (seconds)",
    )
    LLM_MAX_RETRIES: int = Field(
        default=2,
        description="Max retries for failed LLM API calls",
    )
    AGENT_TURN_TIMEOUT_SECONDS: int = Field(
        default=300,
        description="Max time for a single agent turn including all tool loops (seconds)",
    )
    AGENT_GRAPH_TIMEOUT_SECONDS: int = Field(
        default=600,
        description="Max time for full graph invocation including mode chaining (seconds)",
    )

    # ==========================================================================
    # Hybrid LLM Architecture - Local Model Routing
    # ==========================================================================

    # Enable/disable hybrid architecture
    USE_HYBRID_LLM: bool = Field(
        default=True,
        description="Enable hybrid LLM architecture (local + cloud models)",
    )

    # Tier 1: Fast local models for simple tasks
    LOCAL_FAST_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Fast local model for classification and extraction tasks",
    )

    # Tier 2: Capable local models for moderate tasks
    LOCAL_CAPABLE_MODEL: str = Field(
        default="llama3:8b",
        description="Capable local model for RAG and moderate complexity tasks",
    )

    # Vehicle Classification
    USE_LOCAL_VEHICLE_CLASSIFICATION: bool = Field(
        default=True, description="Use local model for vehicle type classification"
    )
    VEHICLE_CLASSIFICATION_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Model for vehicle classification (local recommended)",
    )

    # Document Processing
    USE_LOCAL_SECTION_MAPPING: bool = Field(
        default=True,
        description="Use local model for document section mapping extraction",
    )
    SECTION_MAPPING_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Model for section mapping extraction (local recommended)",
    )

    # RAG Query Routing
    USE_LOCAL_FOR_SIMPLE_RAG: bool = Field(
        default=True, description="Use local model for simple factual RAG queries"
    )
    RAG_PRIMARY_MODEL: str = Field(
        default="llama3:8b", description="Primary local model for simple RAG queries"
    )

    ENABLE_LLM_VARIANT_INTERPRETATION: bool = Field(
        default=True,
        description="Enable LLM-led variant interpretation for multi-unit elements",
    )

    # Constraint Validation (anti-hallucination second pass)
    USE_LLM_CONSTRAINT_VALIDATION: bool = Field(
        default=True,
        description="Use LLM to confirm regex constraint matches (reduces false positives)",
    )
    CONSTRAINT_VALIDATION_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Model for constraint validation (local Tier 1 only, NEVER cloud)",
    )

    # ==========================================================================
    # Photo Completion Wait (confirmar_fotos_elemento two-phase poll)
    # ==========================================================================

    PHOTO_COMPLETION_WAIT_SECONDS: int = Field(
        default=10,
        ge=4,
        le=20,
        description=(
            "Phase-1 wait in seconds before checking element image count. "
            "WhatsApp image delivery typically takes 5-15s, so this must be "
            "at least 4s. Increase if users see false 'no photos' messages."
        ),
    )
    PHOTO_COMPLETION_RETRY_WAIT_SECONDS: int = Field(
        default=6,
        ge=2,
        le=15,
        description=(
            "Phase-2 wait in seconds before the single retry check. "
            "Applied only when Phase-1 found 0 images. The total maximum "
            "wait is PHOTO_COMPLETION_WAIT_SECONDS + PHOTO_COMPLETION_RETRY_WAIT_SECONDS."
        ),
    )

    # ==========================================================================
    # Agent Hardening — Feature Flags & KPI Thresholds
    # ==========================================================================
    # All flags default to False/conservative for safe deployment.
    # Enable incrementally after baseline measurement.

    # Feature flags (all OFF by default → no behavioral change on deploy)
    ENABLE_STATE_CONTRACT_ENFORCEMENT: bool = Field(
        default=False,
        description=(
            "When True, validate mode_context and state updates against "
            "canonical key sets and log unknown keys at WARNING level (monitoring only). "
            "Keys are NEVER deleted regardless of this flag — enforcement is warn-only "
            "per Agent Architecture Refactor REQ-P1-3 (T1.3). "
            "When False, log unknown keys at DEBUG level only (no-op)."
        ),
    )
    ENABLE_PROMPT_BUDGET_GUARDRAIL: bool = Field(
        default=False,
        description=(
            "When True, enforce prompt token/char budgets and truncate "
            "oversized context before LLM invocation."
        ),
    )
    ENABLE_LATENCY_GATING: bool = Field(
        default=True,
        description=(
            "When True, skip optional expensive checks (e.g. auxiliary "
            "LLM constraint validation) when prior confidence is high."
        ),
    )
    ENABLE_TURN_TELEMETRY: bool = Field(
        default=False,
        description=(
            "When True, emit structured per-turn telemetry events with "
            "latency breakdown, tool counts, and LLM tier used."
        ),
    )
    ENABLE_SAME_TURN_TRANSITION_CLOSURE: bool = Field(
        default=False,
        description=(
            "When True, emit deterministic same-turn closure messages for ALL "
            "four expediente sub-mode handoffs (element→base_docs, "
            "base_docs→personal, personal→vehicle, vehicle→workshop, "
            "workshop→review). "
            "When False, only the element→base_docs closure is emitted "
            "(legacy behaviour). Safe to rollback by setting to False and "
            "restarting the agent service."
        ),
    )
    ENABLE_CANONICAL_TRANSITION_ADAPTER: bool = Field(
        default=False,
        description=(
            "When True, canonicalize expediente sub-mode transition signals "
            "from heterogeneous tool payloads into a single authoritative value. "
            "Normalizes legacy aliases (uppercase, Spanish, abbreviations) to "
            "canonical lowercase sub-modes. Safe to rollback by setting to False "
            "and restarting the agent service — no DB migration required."
        ),
    )
    EXPEDIENTE_V2_ENABLED: bool = Field(
        default=False,
        description=(
            "Master toggle for EXPEDIENTE_MODE v2 features. "
            "After agent-architecture-refactor (T1.2b), this flag gates ONLY the harmful "
            "EXPEDIENTE_TOOL_MATRIX and _is_tool_blocked() behaviors in loop_engine.py. "
            "Keep False (default) to disable the tool matrix that causes Bug #1 spiral loops. "
            "Useful V2 behaviors (element state service, collection context, intent classifier, "
            "image assignment) are now controlled by separate granular flags below. "
            "Original v2 features: 7-state per-element state machine (TASK-05), "
            "automatic '📍 Paso X/6' progress prefix (TASK-06), and "
            "anti-repetition guard (TASK-07). "
            "State is stored in mode_context only — no DB migration required. "
            "Safe to rollback by setting to False and restarting the agent service."
        ),
    )
    # ── Granular V2 feature flags (agent-architecture-refactor T1.2a) ─────────
    # These flags were split out of EXPEDIENTE_V2_ENABLED so that useful V2 behaviors
    # can be preserved independently when EXPEDIENTE_V2_ENABLED=False (to disable
    # the harmful tool matrix). All default to True to preserve existing behavior.
    # See AD-2 in design doc and REQ-P1-2 in delta spec.
    USE_ELEMENT_STATE_SERVICE: bool = Field(
        default=True,
        description=(
            "When True, the ElementStateService (7-state per-element state machine) is "
            "enabled in expediente mode. Replaces the EXPEDIENTE_V2_ENABLED guard in "
            "element_state_service.py and expediente_mode.py._get_element_state_svc(). "
            "Defaults to True to preserve element state tracking behavior. "
            "Can be set to False independently of EXPEDIENTE_V2_ENABLED. "
            "Safe to rollback by setting to False and restarting the agent service."
        ),
    )
    USE_V2_COLLECTION_CONTEXT: bool = Field(
        default=True,
        description=(
            "When True, the V2 collection context block ({COLLECTION_CONTEXT}) is "
            "injected into the system prompt and pre-populated by collect_element_data.py. "
            "Replaces the EXPEDIENTE_V2_ENABLED guard in loader.py and "
            "collect_element_data.py. Defaults to True. "
            "Safe to rollback by setting to False and restarting the agent service."
        ),
    )
    USE_INTENT_CLASSIFIER: bool = Field(
        default=True,
        description=(
            "When True, the IntentClassifier singleton is initialized in expediente_mode.py "
            "via _get_intent_classifier_svc(). Replaces the EXPEDIENTE_V2_ENABLED guard "
            "in that method. Defaults to True. "
            "Safe to rollback by setting to False and restarting the agent service."
        ),
    )
    USE_V2_IMAGE_ASSIGNMENT: bool = Field(
        default=True,
        description=(
            "When True, V2 image assignment logic in image_handling.py is active "
            "(DB-based case image lookup rather than ContextVar snapshot). "
            "Replaces the EXPEDIENTE_V2_ENABLED guard in image_handling.py. "
            "Defaults to True. "
            "Safe to rollback by setting to False and restarting the agent service."
        ),
    )
    # ── End granular V2 feature flags ─────────────────────────────────────────
    EXPEDIENTE_STRICT_FIELD_MAPPING: bool = Field(
        default=False,
        description=(
            "Expediente strict field mapping: return ambiguous status instead of "
            "auto-assigning on substring collision. When False (default), the first "
            "fuzzy match is used automatically. When True, ambiguous hits are returned "
            "as 'ambiguous' so the caller can surface the ambiguity to the user."
        ),
    )
    EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED: bool = Field(
        default=False,
        description=(
            "When True, enables the certainty-envelope guardrail system for EXPEDIENTE_MODE. "
            "This gates sub-mode transitions and LLM claim types based on what tools have "
            "actually confirmed in the current turn, preventing hallucinated completions. "
            "Requires EXPEDIENTE_V2_ENABLED=True for full effect. "
            "Safe to rollback by setting to False and restarting the agent service — "
            "no DB migration required; envelope state lives in mode_context only."
        ),
    )

    # Prompt budget limits
    PROMPT_MAX_TOKENS_ESTIMATE: int = Field(
        default=4000,
        ge=500,
        le=16000,
        description="Estimated max tokens for assembled system prompt.",
    )
    PROMPT_CONTEXT_MAX_CHARS: int = Field(
        default=8000,
        ge=1000,
        le=32000,
        description="Max characters for dynamic mode_context injected into prompt.",
    )

    # Latency thresholds
    TURN_LATENCY_P95_THRESHOLD_MS: int = Field(
        default=3000,
        ge=500,
        le=30000,
        description="P95 turn latency threshold in milliseconds for alerts.",
    )

    # Per-mode tool iteration limits
    MAX_TOOL_ITERATIONS_CONSULTA: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max LLM→tool loop iterations in CONSULTA_MODE.",
    )
    MAX_TOOL_ITERATIONS_PRESUPUESTO: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Max LLM→tool loop iterations in PRESUPUESTO_MODE.",
    )
    MAX_TOOL_ITERATIONS_EXPEDIENTE: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Max LLM→tool loop iterations in EXPEDIENTE_MODE.",
    )

    # Error/fallback rate thresholds (for alerting, not enforcement)
    FALLBACK_RATE_THRESHOLD: float = Field(
        default=0.03,
        ge=0.0,
        le=1.0,
        description="Max acceptable fallback rate (3%). Alert if exceeded.",
    )
    ERROR_RATE_THRESHOLD: float = Field(
        default=0.005,
        ge=0.0,
        le=1.0,
        description="Max acceptable error rate (0.5%). Alert if exceeded.",
    )

    # LLM Metrics
    ENABLE_LLM_METRICS: bool = Field(
        default=True, description="Enable LLM usage metrics tracking"
    )
    LLM_METRICS_RETENTION_DAYS: int = Field(
        default=90, description="Days to retain LLM metrics data"
    )

    # Token Pricing (EUR per million tokens)
    # DeepSeek: €0.14 input, €0.28 output (much cheaper than GPT-4o-mini)
    TOKEN_PRICE_INPUT: Decimal = Field(
        default=Decimal("0.14"), description="Price per million input tokens in EUR"
    )
    TOKEN_PRICE_OUTPUT: Decimal = Field(
        default=Decimal("0.28"), description="Price per million output tokens in EUR"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


# =============================================================================
# Data-Driven Patterns for Element Matching (NOT in Settings - constant config)
# =============================================================================

# Spanish number words for quantity extraction
QUANTITY_PATTERNS: dict[str, int | str] = {
    # Written numbers (Spanish)
    "uno": 1,
    "un": 1,
    "una": 1,
    "dos": 2,
    "par": 2,
    "pareja": 2,
    "doble": 2,
    "ambos": 2,
    "ambas": 2,
    "tres": 3,
    "triple": 3,
    "cuatro": 4,
    "cuadruple": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    # Regex pattern for digit extraction (e.g., "2 escapes", "3 faros")
    "digit_pattern": r"(\d+)\s+(\w+)",
}

# Negation patterns for element exclusion
NEGATION_PATTERNS: dict[str, list[str]] = {
    # "all except" patterns - user wants everything minus specified elements
    "all_except": [
        r"todo\s+(?:menos|excepto|sin)\s+",
        r"todos?\s+los?\s+elementos?\s+(?:menos|excepto|sin)\s+",
        r"completo\s+(?:menos|excepto|sin)\s+",
        r"todo\s+(?:el\s+)?(?:kit|pack|paquete)\s+(?:menos|excepto|sin)\s+",
    ],
    # Specific exclusion patterns - user explicitly excludes certain elements
    "specific_exclude": [
        r"(?:sin|excepto|menos|salvo|quitando|eliminando)\s+(?:el|la|los|las)?\s*",
        r"no\s+(?:quiero|necesito|incluir)\s+(?:el|la|los|las)?\s*",
        r"(?:el|la|los|las)\s+\w+\s+no\b",
    ],
    # Keywords that indicate negation context
    "keywords": ["sin", "excepto", "menos", "salvo", "quitando", "eliminando", "no"],
}


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()
