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
        default="MSI Automotive",
        description="Project name displayed in UI and logs"
    )
    AGENT_NAME: str = Field(
        default="MSI-a",
        description="Name of the AI agent"
    )
    ENVIRONMENT: str = Field(
        default="development",
        description="Environment: development, staging, production"
    )

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://msia:changeme@postgres:5432/msia_db",
        description="PostgreSQL connection string with asyncpg driver"
    )
    POSTGRES_DB: str = Field(default="msia_db")
    POSTGRES_USER: str = Field(default="msia")
    POSTGRES_PASSWORD: str = Field(default="changeme")
    POSTGRES_HOST: str = Field(default="postgres")
    POSTGRES_PORT: int = Field(default=5432)

    # Redis
    REDIS_URL: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection string"
    )
    REDIS_PASSWORD: str = Field(
        default="",
        description="Redis password for authentication (required in production)"
    )
    USE_REDIS_STREAMS: bool = Field(
        default=True,
        description="Use Redis Streams instead of Pub/Sub for message delivery"
    )

    # Chatwoot
    CHATWOOT_API_URL: str = Field(default="https://app.chatwoot.com")
    CHATWOOT_API_TOKEN: str = Field(default="placeholder")
    CHATWOOT_ACCOUNT_ID: str = Field(default="12345")
    CHATWOOT_INBOX_ID: str = Field(default="67890")
    CHATWOOT_TEAM_GROUP_ID: str = Field(default="group_id")
    CHATWOOT_WEBHOOK_TOKEN: str = Field(
        default="chatwoot_webhook_token_placeholder",
        description="Secret token for Chatwoot webhook URL authentication"
    )
    CHATWOOT_STORAGE_DOMAIN: str = Field(
        default="",
        description="Domain for Chatwoot active_storage URLs (e.g., chats.autohomologacion.net)"
    )

    # OpenRouter (Unified LLM API)
    OPENROUTER_API_KEY: str = Field(default="sk-or-placeholder")
    LLM_MODEL: str = Field(
        default="deepseek/deepseek-chat",
        description="AI model for conversations (OpenRouter format). DeepSeek recommended for better reasoning and lower cost."
    )
    SITE_URL: str = Field(
        default="https://msiautomotive.es",
        description="Site URL for OpenRouter rankings"
    )
    SITE_NAME: str = Field(
        default="MSI Automotive",
        description="Site name for OpenRouter rankings"
    )

    # Application Settings
    TIMEZONE: str = Field(default="Europe/Madrid")
    LOG_LEVEL: str = Field(default="INFO")
    MESSAGE_BATCH_WINDOW_SECONDS: int = Field(
        default=30,
        ge=0,
        le=120,
        description="Message batching window in seconds"
    )

    # Image Storage
    IMAGE_UPLOAD_DIR: str = Field(
        default="./uploads/images",
        description="Directory for storing uploaded images"
    )
    IMAGE_BASE_URL: str = Field(
        default="/images",
        description="Base URL path for serving images"
    )
    IMAGE_MAX_SIZE_MB: int = Field(
        default=10,
        description="Maximum upload size in MB"
    )

    # Case Images Storage
    CASE_IMAGES_DIR: str = Field(
        default="./uploads/case_images",
        description="Directory for storing case/expediente images"
    )
    CASE_IMAGES_BASE_URL: str = Field(
        default="/case-images",
        description="Base URL path for serving case images"
    )
    CASE_IMAGES_MAX_SIZE_MB: int = Field(
        default=15,
        description="Maximum case image size in MB"
    )

    # Image Security
    MAX_IMAGES_PER_CASE: int = Field(
        default=50,
        description="Maximum number of images allowed per case/expediente"
    )
    IMAGE_UPLOAD_RATE_LIMIT: int = Field(
        default=10,
        description="Maximum image uploads per minute per user"
    )

    # API Base URL (for generating absolute URLs for external services like Chatwoot)
    API_BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Public base URL of the API server (for generating absolute image URLs)"
    )

    # Admin Panel Authentication
    ADMIN_USERNAME: str = Field(
        default="admin",
        description="Admin panel username"
    )
    ADMIN_PASSWORD: str = Field(
        default="",
        description="Admin panel password in plain text (DEPRECATED)"
    )
    ADMIN_PASSWORD_HASH: str = Field(
        default="",
        description="Bcrypt hash of admin password"
    )
    ADMIN_JWT_SECRET: str = Field(
        default="",
        description="JWT secret key for admin panel authentication (min 32 chars)"
    )

    # CORS Origins for API
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000,http://localhost:8001,http://api:8000",
        description="Comma-separated list of allowed origins for CORS"
    )

    # RAG System - Qdrant
    QDRANT_URL: str = Field(
        default="http://qdrant:6333",
        description="Qdrant vector database URL"
    )
    QDRANT_API_KEY: str | None = Field(
        default=None,
        description="Qdrant API key (optional, for cloud deployments)"
    )
    QDRANT_COLLECTION_NAME: str = Field(
        default="msi_regulatory_docs",
        description="Name of the Qdrant collection for regulatory documents"
    )

    # RAG System - Ollama Embeddings
    OLLAMA_BASE_URL: str = Field(
        default="http://ollama:11434",
        description="Ollama server URL for embeddings"
    )
    EMBEDDING_MODEL: str = Field(
        default="nomic-embed-text",
        description="Embedding model name in Ollama"
    )
    EMBEDDING_DIMENSION: int = Field(
        default=768,
        description="Embedding vector dimension"
    )

    # RAG System - Re-ranking
    BGE_RERANKER_MODEL: str = Field(
        default="BAAI/bge-reranker-large",
        description="BGE re-ranker model for result re-ranking"
    )

    # RAG System - Query Parameters
    RAG_TOP_K: int = Field(
        default=30,
        description="Number of initial results to retrieve from vector search"
    )
    RAG_RERANK_TOP_K: int = Field(
        default=8,
        description="Number of results after re-ranking"
    )
    RAG_CHUNK_SIZE: int = Field(
        default=800,
        description="Target chunk size in characters"
    )
    RAG_CHUNK_OVERLAP: int = Field(
        default=200,
        description="Chunk overlap in characters"
    )
    RAG_CACHE_TTL: int = Field(
        default=3600,
        description="Query result cache TTL in seconds"
    )

    # RAG System - Document Storage
    DOCUMENT_UPLOAD_DIR: str = Field(
        default="/app/uploads/documents",
        description="Directory for storing uploaded regulatory documents"
    )
    DOCUMENT_MAX_SIZE_MB: int = Field(
        default=50,
        description="Maximum document upload size in MB"
    )

    # RAG System - LLM Fallback
    RAG_LLM_FALLBACK_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Local Ollama model for LLM fallback (lightweight)"
    )

    # ==========================================================================
    # Hybrid LLM Architecture - Local Model Routing
    # ==========================================================================

    # Enable/disable hybrid architecture
    USE_HYBRID_LLM: bool = Field(
        default=True,
        description="Enable hybrid LLM architecture (local + cloud models)"
    )

    # Tier 1: Fast local models for simple tasks
    LOCAL_FAST_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Fast local model for classification and extraction tasks"
    )

    # Tier 2: Capable local models for moderate tasks
    LOCAL_CAPABLE_MODEL: str = Field(
        default="llama3:8b",
        description="Capable local model for RAG and moderate complexity tasks"
    )

    # Vehicle Classification
    USE_LOCAL_VEHICLE_CLASSIFICATION: bool = Field(
        default=True,
        description="Use local model for vehicle type classification"
    )
    VEHICLE_CLASSIFICATION_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Model for vehicle classification (local recommended)"
    )

    # Document Processing
    USE_LOCAL_SECTION_MAPPING: bool = Field(
        default=True,
        description="Use local model for document section mapping extraction"
    )
    SECTION_MAPPING_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Model for section mapping extraction (local recommended)"
    )

    # RAG Query Routing
    USE_LOCAL_FOR_SIMPLE_RAG: bool = Field(
        default=True,
        description="Use local model for simple factual RAG queries"
    )
    RAG_PRIMARY_MODEL: str = Field(
        default="llama3:8b",
        description="Primary local model for simple RAG queries"
    )

    # LLM Metrics
    ENABLE_LLM_METRICS: bool = Field(
        default=True,
        description="Enable LLM usage metrics tracking"
    )
    LLM_METRICS_RETENTION_DAYS: int = Field(
        default=90,
        description="Days to retain LLM metrics data"
    )

    # Token Pricing (EUR per million tokens)
    # DeepSeek: €0.14 input, €0.28 output (much cheaper than GPT-4o-mini)
    TOKEN_PRICE_INPUT: Decimal = Field(
        default=Decimal("0.14"),
        description="Price per million input tokens in EUR"
    )
    TOKEN_PRICE_OUTPUT: Decimal = Field(
        default=Decimal("0.28"),
        description="Price per million output tokens in EUR"
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
