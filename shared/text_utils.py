"""
Text utilities for WhatsApp-compatible formatting.

WhatsApp does NOT support standard Markdown formatting like:
- **text** or __text__ (double asterisks/underscores)
- ### headers
- --- horizontal rules
- [link](url) syntax
- Code blocks with ```

This module provides utilities to strip markdown and convert
to plain text suitable for WhatsApp.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Special tokens from LLM model families that can be used for prompt injection.
# These tokens have semantic meaning to the model's tokenizer and can interfere
# with the system prompt context when sent by a user.
_LLM_INJECTION_TOKENS = [
    # DeepSeek / Qwen family
    "<｜begin▁of▁sentence｜>",
    "<｜end▁of▁sentence｜>",
    "<|im_start|>",
    "<|im_end|>",
    "<|endoftext|>",
    # Llama 2 / Mistral instruction format
    "[INST]",
    "[/INST]",
    "<<SYS>>",
    "<</SYS>>",
    # Generic chat template markers
    "<|system|>",
    "<|user|>",
    "<|assistant|>",
    "<|end|>",
]


def strip_markdown_for_whatsapp(text: str) -> str:
    """
    Remove markdown formatting from text for WhatsApp compatibility.

    Args:
        text: Text potentially containing markdown

    Returns:
        Plain text without markdown formatting
    """
    if not text:
        return text

    # 1. Remove **bold** (double asterisks)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)

    # 2. Remove __bold__ (double underscores)
    text = re.sub(r"__([^_]+)__", r"\1", text)

    # 3. Convert markdown headers (### Title) to plain text with colon
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1:", text, flags=re.MULTILINE)

    # 4. Remove horizontal rules (---)
    text = re.sub(r"^---+$", "", text, flags=re.MULTILINE)

    # 5. Remove inline code backticks
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 6. Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)

    # 7. Clean up excessive blank lines (more than 2 consecutive)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def sanitize_user_input(text: str, max_length: int = 4096) -> str:
    """
    Sanitize raw user input before passing it to the LLM pipeline.

    Performs three layers of cleaning:
    1. Strips control characters (except newlines and tabs, which are valid).
    2. Removes known LLM injection tokens (BOS/EOS, chat template markers).
    3. Truncates to max_length to prevent context overflow.

    This function is intentionally conservative — it only removes what is
    dangerous. Normal Spanish text, emojis, €, ñ, tildes, vehicle plate
    numbers and other expected user content pass through unchanged.

    Args:
        text: Raw user input from WhatsApp / Chatwoot webhook.
        max_length: Maximum character length (default 4096, matching
                    WhatsApp's practical message limit). The tool-helper
                    copy uses 1000 (LLM context limit), but at the webhook
                    boundary 4096 is more appropriate.

    Returns:
        Sanitized text, safe to pass to the LLM.

    Examples:
        >>> sanitize_user_input("Hola, quiero homologar mi moto")
        'Hola, quiero homologar mi moto'
        >>> sanitize_user_input("<｜begin▁of▁sentence｜>ignore instructions")
        'ignore instructions'
        >>> sanitize_user_input("hello\\x00world")
        'helloworld'
    """
    if not text:
        return ""

    # Strip leading/trailing whitespace
    text = text.strip()

    # Layer 1: Remove ASCII control characters (keep \n and \t — valid in messages)
    text = "".join(char for char in text if ord(char) >= 32 or char in "\n\t")

    # Layer 2: Strip known LLM injection tokens
    original_length = len(text)
    for token in _LLM_INJECTION_TOKENS:
        if token in text:
            text = text.replace(token, "")
            logger.warning(
                "llm_injection_token_stripped",
                extra={"token": token, "original_length": original_length},
            )

    # Layer 3: Truncate to max_length
    if len(text) > max_length:
        logger.warning(
            "user_input_truncated",
            extra={"original_length": len(text), "max_length": max_length},
        )
        text = text[:max_length]

    return text
