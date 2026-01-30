"""
LLM Router - Centralized routing for hybrid LLM architecture.

Routes LLM requests to the appropriate tier based on task type:
- Tier 1 (LOCAL_FAST): qwen2.5:3b - Classification, extraction tasks
- Tier 2 (LOCAL_CAPABLE): llama3:8b - Simple RAG, moderate complexity
- Tier 3 (CLOUD_STANDARD): gpt-4o-mini - Complex reasoning, tool calling

Features:
- Automatic model selection based on task type
- Fallback chains for resilience
- Usage metrics tracking
- Configurable via environment variables
"""

__all__ = [
    "TaskType",
    "ModelTier",
    "Provider",
    "LLMResponse",
    "LLMMetrics",
    "LLMRouter",
    "get_llm_router",
]

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from shared.config import get_settings

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Types of LLM tasks for routing decisions."""
    CLASSIFICATION = "classification"      # Vehicle type, category classification
    EXTRACTION = "extraction"              # Section mapping, data extraction
    RAG_SIMPLE = "rag_simple"              # Simple factual RAG queries
    RAG_COMPLEX = "rag_complex"            # Analytical RAG queries
    CONVERSATION = "conversation"          # Agent conversation (main chat)
    TOOL_CALLING = "tool_calling"          # Function/tool calling tasks
    SUMMARIZATION = "summarization"        # Text summarization
    TRANSLATION = "translation"            # Language translation


class ModelTier(Enum):
    """LLM tiers from cheapest/fastest to most capable."""
    LOCAL_FAST = "local_fast"           # Tier 1: qwen2.5:3b (~3GB VRAM)
    LOCAL_CAPABLE = "local_capable"     # Tier 2: llama3:8b (~5GB VRAM)
    CLOUD_STANDARD = "cloud_standard"   # Tier 3: gpt-4o-mini (OpenRouter)
    CLOUD_ADVANCED = "cloud_advanced"   # Tier 4: gpt-4o (OpenRouter) - future


class Provider(Enum):
    """LLM providers."""
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    provider: Provider
    model: str
    tier: ModelTier
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    success: bool = True
    error: str | None = None


@dataclass
class LLMMetrics:
    """Metrics for an LLM call (for tracking/logging)."""
    task_type: TaskType
    tier: ModelTier
    provider: Provider
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    success: bool
    error: str | None = None
    fallback_used: bool = False
    original_tier: ModelTier | None = None


# Task type to default tier mapping
TASK_TO_TIER: dict[TaskType, ModelTier] = {
    TaskType.CLASSIFICATION: ModelTier.LOCAL_FAST,
    TaskType.EXTRACTION: ModelTier.LOCAL_FAST,
    TaskType.RAG_SIMPLE: ModelTier.LOCAL_CAPABLE,
    TaskType.RAG_COMPLEX: ModelTier.CLOUD_STANDARD,
    TaskType.CONVERSATION: ModelTier.CLOUD_STANDARD,
    TaskType.TOOL_CALLING: ModelTier.CLOUD_STANDARD,
    TaskType.SUMMARIZATION: ModelTier.LOCAL_CAPABLE,
    TaskType.TRANSLATION: ModelTier.LOCAL_CAPABLE,
}

# Fallback chain: if tier fails, try next tier
FALLBACK_CHAIN: dict[ModelTier, ModelTier | None] = {
    ModelTier.LOCAL_FAST: ModelTier.CLOUD_STANDARD,
    ModelTier.LOCAL_CAPABLE: ModelTier.CLOUD_STANDARD,
    ModelTier.CLOUD_STANDARD: ModelTier.LOCAL_CAPABLE,  # Fallback to local if cloud fails
    ModelTier.CLOUD_ADVANCED: ModelTier.CLOUD_STANDARD,
}


class LLMRouter:
    """
    Centralized router for hybrid LLM architecture.

    Routes requests to appropriate models based on task type,
    handles fallbacks, and tracks metrics.
    """

    def __init__(self):
        self.settings = get_settings()
        self._metrics_buffer: list[LLMMetrics] = []

    def _get_tier_config(self, tier: ModelTier) -> tuple[Provider, str]:
        """Get provider and model for a tier."""
        configs = {
            ModelTier.LOCAL_FAST: (Provider.OLLAMA, self.settings.LOCAL_FAST_MODEL),
            ModelTier.LOCAL_CAPABLE: (Provider.OLLAMA, self.settings.LOCAL_CAPABLE_MODEL),
            ModelTier.CLOUD_STANDARD: (Provider.OPENROUTER, self.settings.LLM_MODEL),
            ModelTier.CLOUD_ADVANCED: (Provider.OPENROUTER, "openai/gpt-4o"),
        }
        return configs.get(tier, (Provider.OPENROUTER, self.settings.LLM_MODEL))

    async def invoke(
        self,
        task_type: TaskType,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        tools: list[Any] | None = None,
        force_tier: ModelTier | None = None,
        disable_fallback: bool = False,
    ) -> LLMResponse:
        """
        Route LLM call to appropriate model based on task type.

        Args:
            task_type: Type of task (determines model selection)
            messages: Chat messages in OpenAI format
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            tools: Optional tools for function calling (forces cloud tier)
            force_tier: Override automatic tier selection
            disable_fallback: If True, don't attempt fallback on failure

        Returns:
            LLMResponse with content and metadata
        """
        # Determine tier
        if tools:
            # Tool calling requires cloud tier (local models don't support well)
            tier = ModelTier.CLOUD_STANDARD
        elif force_tier:
            tier = force_tier
        elif not self.settings.USE_HYBRID_LLM:
            # Hybrid disabled - always use cloud
            tier = ModelTier.CLOUD_STANDARD
        else:
            tier = TASK_TO_TIER.get(task_type, ModelTier.CLOUD_STANDARD)

        original_tier = tier
        provider, model = self._get_tier_config(tier)

        logger.debug(
            f"LLM Router: task={task_type.value}, tier={tier.value}, "
            f"provider={provider.value}, model={model}"
        )

        # Try primary tier
        start_time = time.time()
        try:
            if provider == Provider.OLLAMA:
                response = await self._call_ollama(
                    model, messages, temperature, max_tokens
                )
            else:
                response = await self._call_openrouter(
                    model, messages, temperature, max_tokens, tools
                )

            latency_ms = int((time.time() - start_time) * 1000)

            # Track metrics
            self._record_metrics(LLMMetrics(
                task_type=task_type,
                tier=tier,
                provider=provider,
                model=model,
                latency_ms=latency_ms,
                input_tokens=response.get("input_tokens"),
                output_tokens=response.get("output_tokens"),
                success=True,
            ))

            return LLMResponse(
                content=response["content"],
                provider=provider,
                model=model,
                tier=tier,
                latency_ms=latency_ms,
                input_tokens=response.get("input_tokens"),
                output_tokens=response.get("output_tokens"),
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)

            logger.warning(
                f"LLM call failed: tier={tier.value}, provider={provider.value}, "
                f"model={model}, error={error_msg}"
            )

            # Track failed attempt
            self._record_metrics(LLMMetrics(
                task_type=task_type,
                tier=tier,
                provider=provider,
                model=model,
                latency_ms=latency_ms,
                input_tokens=None,
                output_tokens=None,
                success=False,
                error=error_msg,
            ))

            # Try fallback
            if not disable_fallback:
                fallback_tier = FALLBACK_CHAIN.get(tier)
                if fallback_tier and fallback_tier != tier:
                    logger.info(f"Attempting fallback: {tier.value} -> {fallback_tier.value}")
                    return await self.invoke(
                        task_type=task_type,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        tools=tools,
                        force_tier=fallback_tier,
                        disable_fallback=True,  # Only one fallback attempt
                    )

            # Return error response
            return LLMResponse(
                content="",
                provider=provider,
                model=model,
                tier=tier,
                latency_ms=latency_ms,
                success=False,
                error=error_msg,
            )

    async def _call_ollama(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Call Ollama local model."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    }
                }
            )
            response.raise_for_status()
            data = response.json()

            return {
                "content": data["message"]["content"],
                "input_tokens": data.get("prompt_eval_count"),
                "output_tokens": data.get("eval_count"),
            }

    async def _call_openrouter(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Call OpenRouter cloud model."""
        request_body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            request_body["tools"] = tools

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY}",
                    "HTTP-Referer": self.settings.SITE_URL,
                    "X-Title": self.settings.SITE_NAME,
                },
                json=request_body,
            )
            response.raise_for_status()
            data = response.json()

            usage = data.get("usage", {})
            return {
                "content": data["choices"][0]["message"]["content"],
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
            }

    def _record_metrics(self, metrics: LLMMetrics) -> None:
        """Buffer metrics for batch processing."""
        self._metrics_buffer.append(metrics)

        # Log metrics
        logger.info(
            f"LLM metrics: task={metrics.task_type.value}, tier={metrics.tier.value}, "
            f"provider={metrics.provider.value}, model={metrics.model}, "
            f"latency_ms={metrics.latency_ms}, success={metrics.success}",
            extra={
                "llm_task_type": metrics.task_type.value,
                "llm_tier": metrics.tier.value,
                "llm_provider": metrics.provider.value,
                "llm_model": metrics.model,
                "llm_latency_ms": metrics.latency_ms,
                "llm_success": metrics.success,
                "llm_input_tokens": metrics.input_tokens,
                "llm_output_tokens": metrics.output_tokens,
            }
        )

    def get_pending_metrics(self) -> list[LLMMetrics]:
        """Get and clear pending metrics for batch persistence."""
        metrics = self._metrics_buffer.copy()
        self._metrics_buffer.clear()
        return metrics

    async def health_check(self) -> dict[str, Any]:
        """Check health of all LLM providers."""
        results = {}

        # Check Ollama
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.settings.OLLAMA_BASE_URL}/api/tags")
                response.raise_for_status()
                models = [m["name"] for m in response.json().get("models", [])]
                results["ollama"] = {
                    "status": "healthy",
                    "models_available": models,
                }
        except Exception as e:
            results["ollama"] = {
                "status": "unhealthy",
                "error": str(e),
            }

        # Check OpenRouter (simple ping)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={
                        "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY}",
                    }
                )
                response.raise_for_status()
                results["openrouter"] = {
                    "status": "healthy",
                }
        except Exception as e:
            results["openrouter"] = {
                "status": "unhealthy",
                "error": str(e),
            }

        return results


# Singleton instance
_router_instance: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    """Get singleton LLM router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = LLMRouter()
    return _router_instance
