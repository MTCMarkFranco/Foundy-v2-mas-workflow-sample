"""Shared helpers for parsing Foundry agent responses."""


def strip_code_fence(text: str) -> str:
    """Remove markdown code fences if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.index("\n")
        stripped = stripped[first_newline + 1:]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    return stripped.strip()
