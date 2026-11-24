"""Small helpers that turn per-call flags into per-step features."""

from __future__ import annotations


def running_count(flags: list[bool]) -> list[int]:
    """Number of True flags up to and including each step."""
    counts, total = [], 0
    for flag in flags:
        total += flag
        counts.append(total)
    return counts


def first_true(flags: list[bool]) -> int | None:
    """Index of the first True flag, or None."""
    return next((step for step, flag in enumerate(flags) if flag), None)
