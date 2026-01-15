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

import re


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
