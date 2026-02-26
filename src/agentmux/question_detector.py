"""Heuristic question detection in agent output."""

from __future__ import annotations

import re

_MIN_LENGTH = 5

_PERMISSION_PATTERNS = [
    re.compile(r"\[Y/n\]", re.IGNORECASE),
    re.compile(r"\[y/N\]", re.IGNORECASE),
    re.compile(r"\by/n\b", re.IGNORECASE),
    re.compile(r"\bAllow\b"),
    re.compile(r"\bConfirm\b", re.IGNORECASE),
    re.compile(r"\bProceed\?", re.IGNORECASE),
]

_CHOICE_KEYWORDS = re.compile(
    r"\b(choose|select|which|prefer|pick|option)\b",
    re.IGNORECASE,
)

_NUMBERED_LIST = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)


def detect_question(text: str) -> bool:
    """Return True if the text likely contains a question needing user input."""
    if len(text.strip()) < _MIN_LENGTH:
        return False

    for pattern in _PERMISSION_PATTERNS:
        if pattern.search(text):
            return True

    if text.rstrip().endswith("?"):
        return True

    return bool(_NUMBERED_LIST.search(text) and _CHOICE_KEYWORDS.search(text))


def extract_question(text: str) -> str:
    """Extract the most relevant question portion from text.

    Returns the last line ending with '?' or a permission pattern match,
    falling back to the last non-empty line.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return ""

    for line in reversed(lines):
        if line.endswith("?"):
            return line

    for line in reversed(lines):
        for pattern in _PERMISSION_PATTERNS:
            if pattern.search(line):
                return line

    return lines[-1]
