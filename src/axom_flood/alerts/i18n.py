"""Reviewed-string gate for user-facing Assamese content."""

from __future__ import annotations

import json
from pathlib import Path


class UnreviewedTranslationError(ValueError):
    """Raised when code attempts to publish an unreviewed translation."""


def load_reviewed_catalog(path: Path) -> dict[str, str]:
    document = json.loads(path.read_text())
    if not document.get("reviewed"):
        raise UnreviewedTranslationError(f"translation catalog is not reviewed: {path}")
    strings = document.get("strings")
    if not isinstance(strings, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in strings.items()
    ):
        raise ValueError(f"invalid translation catalog: {path}")
    return strings


def reviewed_text(
    english: str,
    *,
    translated: str | None,
    reviewed: bool,
) -> str:
    """Return translated text only after an explicit review flag."""

    return translated if reviewed and translated else english

