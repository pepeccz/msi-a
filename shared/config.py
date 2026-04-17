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

    # Memory Management
    MEMORY_SUMMARIZATION_THRESHOLD: int = Field(
        default=30,
        ge=10,
        le=100,
        description="Message count before triggering structured summarization and trim",
    )
    MEMORY_MESSAGES_WINDOW: int = Field(
        default=10,
        ge=5,
        le=30,
        description="Number of recent messages to retain in checkpoint after trim",
    )

    # Garbage Collection
    GC_RETENTION_DAYS: int = Field(
        default=90,
        ge=7,
        le=365,
        description="Days to retain ConversationHistory records before GC cleanup",
    )
    GC_DRY_RUN: bool = Field(
        default=True,
        description="Run garbage collection in dry-run mode (log only, no deletes)",
    )

    # Checkpoint TTL by conversation mode (minutes)
    # REQ-P2-3: All TTLs must be ≥ 72 hours (4320 minutes) to survive planned maintenance
    # windows. CONSULTA and ESCALATION are exempt (short-lived, non-critical modes).
    CHECKPOINT_TTL_DEFAULT_MINUTES: int = Field(
        default=4320,
        description=(
            "Default checkpoint TTL in minutes (72h) — applies when no mode matches. "
            "Raised from 24h → 72h (REQ-P2-3) to cover planned maintenance windows."
        ),
    )
    CHECKPOINT_TTL_CONSULTA_MINUTES: int = Field(
        default=60,
        description="Consulta mode checkpoint TTL in minutes (1h) — short-lived educational queries",
    )
    CHECKPOINT_TTL_PRESUPUESTO_MINUTES: int = Field(
        default=4320,
        description=(
            "Presupuesto mode checkpoint TTL in minutes (72h) — active pricing sessions. "
            "Raised from 4h → 72h (REQ-P2-3) to cover planned maintenance windows."
        ),
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
    CHATWOOT_PLATFORM_TOKEN: str = Field(
        default="",
        description="Platform API token for agent lifecycle management (self-hosted only)",
    )
    WHATSAPP_TEMPLATE_CASE_ASSIGNED: str = Field(
        default="expediente_tomado",
        description="WhatsApp template name for case assignment notification",
    )
    WHATSAPP_TEMPLATE_CASE_COMPLETED: str = Field(
        default="expediente_resuelto",
        description="WhatsApp template name for case completion notification",
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

    # Ollama (used by llm_router for local model inference)
    OLLAMA_BASE_URL: str = Field(
        default="http://ollama:11434",
        description="Ollama server URL for local LLM inference",
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
        default="gemma4:e4b",
        description="Fast local model for classification and extraction tasks",
    )

    # Vehicle Classification
    USE_LOCAL_VEHICLE_CLASSIFICATION: bool = Field(
        default=True, description="Use local model for vehicle type classification"
    )
    VEHICLE_CLASSIFICATION_MODEL: str = Field(
        default="gemma4:e4b",
        description="Model for vehicle classification (local recommended)",
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
        default="gemma4:e4b",
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
    BASE_DOCS_MIN_REQUIRED_FLOOR: int = Field(
        default=4,
        ge=2,
        le=20,
        description=(
            "Absolute minimum number of base documentation images required "
            "to advance past COLLECT_BASE_DOCS, regardless of DB count. "
            "Prevents premature advancement when BaseDocumentation table "
            "has fewer records than actual photo requirements."
        ),
    )
    # BASE_DOCS_PDF_SATISFIES_MINIMUM removed — polymorphic attachment model makes
    # this unconditional: a PDF in base docs always satisfies the minimum.
    # See: docs/system/01-agente/flujo-expediente.md rule 13.

    # ==========================================================================
    # Agent Hardening — Feature Flags (Spec 2 / fix-agent-antipatterns)
    # ==========================================================================
    # All three flags default to False (safe off). Enable per-flag as
    # the guarded code paths are stabilised and verified in production.
    # See: agent/ROLLBACK_PLAYBOOK.md for rollback procedures.

    EXPEDIENTE_V2_ENABLED: bool = Field(
        default=False,
        description=(
            "Enable EXPEDIENTE_MODE V2 logic (element-state service, intent classifier, "
            "image-handling V2 paths). When False, all V2-gated code paths are bypassed "
            "and the agent runs V1 logic. Safe to toggle; no DB migration required."
        ),
    )
    ENABLE_STATE_CONTRACT_ENFORCEMENT: bool = Field(
        default=False,
        description=(
            "Enable state-contract enforcement in _validate_canonical_keys(). "
            "When False (default), unknown mode_context or state keys are logged at DEBUG "
            "level only — no data is stripped. When True, the validator would enforce "
            "stricter behaviour (currently warn-only regardless; flag reserved for future "
            "upgrade). Gated via agent.utils.feature_flags.is_flag_enabled()."
        ),
    )
    ENABLE_SAME_TURN_TRANSITION_CLOSURE: bool = Field(
        default=False,
        description=(
            "Enable deterministic same-turn closure messages on EXPEDIENTE sub-mode "
            "transitions (e.g., collect_personal → collect_vehicle). When False, the LLM "
            "authors the transition message. When True, a pre-built closure message is "
            "injected deterministically. See agent/ROLLBACK_PLAYBOOK.md."
        ),
    )

    # ==========================================================================
    # Agent Hardening — KPI Thresholds
    # ==========================================================================

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

    # ==========================================================================
    # Case Lifecycle Worker
    # ==========================================================================

    CASE_REMINDER_HOURS: float = Field(
        default=20.0,
        description="Hours of inactivity before sending a WhatsApp reminder to the user",
    )
    CASE_ABANDON_DAYS: float = Field(
        default=4.0,
        description="Days of inactivity before marking a case as abandoned",
    )
    CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES: int = Field(
        default=15,
        description="Interval in minutes between lifecycle worker scan cycles",
    )
    CASE_REMINDER_MESSAGE_TEMPLATE: str = Field(
        default=(
            "Hola {name}, tenés un expediente de homologación pendiente para {elements}. "
            "¿Querés que sigamos? Si necesitás ayuda, escribime."
        ),
        description="WhatsApp message template for inactivity reminder. Supports {name} and {elements} placeholders.",
    )

    # Token Pricing (EUR per million tokens)
    # DeepSeek: €0.14 input, €0.28 output (much cheaper than GPT-4o-mini)
    TOKEN_PRICE_INPUT: Decimal = Field(
        default=Decimal("0.14"), description="Price per million input tokens in EUR"
    )
    TOKEN_PRICE_OUTPUT: Decimal = Field(
        default=Decimal("0.28"), description="Price per million output tokens in EUR"
    )

    # ── Billing & Invoicing ──
    MONTHLY_MAINTENANCE_EUR: Decimal = Field(
        default=Decimal("50.00"),
        description="Fixed monthly maintenance charge in EUR",
    )
    INVOICE_PREFIX: str = Field(default="MSI", description="Invoice number prefix")
    IVA_RATE: Decimal = Field(
        default=Decimal("21.00"),
        description="IVA tax rate percentage (Spain)",
    )
    INVOICES_DIR: str = Field(
        default="./invoices",
        description="Directory for generated invoice PDFs",
    )
    PAYMENT_DUE_DAYS: int = Field(
        default=15,
        description="Days until invoice payment due date",
    )

    # ── Stripe (Payment Gateway) ──
    STRIPE_SECRET_KEY: str = Field(default="", description="Stripe secret API key")
    STRIPE_PUBLISHABLE_KEY: str = Field(default="", description="Stripe publishable key")
    STRIPE_WEBHOOK_SECRET: str = Field(default="", description="Stripe webhook signing secret")
    STRIPE_TAX_RATE_ID: str = Field(default="", description="Stripe TaxRate ID for IVA 21%")
    STRIPE_CUSTOMER_ID: str = Field(default="", description="Stripe customer ID for billing")

    # ── Fiscal Compliance (Spain B2B) ──
    COMPANY_NIF: str = Field(default="", description="NIF del proveedor")
    COMPANY_LEGAL_NAME: str = Field(default="", description="Razón social del proveedor")
    COMPANY_FISCAL_ADDRESS: str = Field(default="", description="Domicilio fiscal del proveedor")
    CLIENT_NIF: str = Field(default="", description="NIF del cliente")
    CLIENT_COMPANY_NAME: str = Field(default="", description="Razón social del cliente")
    CLIENT_FISCAL_ADDRESS: str = Field(default="", description="Domicilio fiscal del cliente")

    # ── Email / SMTP (Invoice Delivery) ──
    OPERATOR_EMAIL: str = Field(default="", description="Receives invoice email copies")
    SMTP_HOST: str = Field(default="", description="SMTP server hostname")
    SMTP_PORT: int = Field(default=587, description="SMTP server port")
    SMTP_USER: str = Field(default="", description="SMTP username")
    SMTP_PASSWORD: str = Field(default="", description="SMTP password")

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
