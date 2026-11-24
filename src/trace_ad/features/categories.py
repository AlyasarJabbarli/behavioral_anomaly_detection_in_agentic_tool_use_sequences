"""Map tool calls to tool categories (configs/tool_categories.yaml).

Every detector sees a run as a sequence of categories, never as raw tool names
and never as the text inside arguments or outputs. Seven categories describe
what a call does (read_trusted, read_untrusted, write, delete, send, payment,
access); calls to tools that do not exist in the suite map to ``unknown``.

For value provenance, each tool's output is also trusted or untrusted:
untrusted for ``read_untrusted`` tools and for the write tools listed in
``untrusted_output_writes`` (they echo the third-party file or event they act
on). Only reads and those write tools count as sources of values.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trace_ad.config import load_config

UNKNOWN = "unknown"
READS = ("read_trusted", "read_untrusted")


@dataclass(frozen=True)
class ToolCategories:
    """Category per (suite, tool) and the allowed category names."""

    names: tuple[str, ...]
    of_tool: dict[tuple[str, str], str]
    untrusted_output_writes: frozenset[tuple[str, str]] = frozenset()

    def category(self, suite: str, tool: str) -> str:
        """Category of ``tool`` in ``suite``; ``unknown`` for tools the suite does not define."""
        return self.of_tool.get((suite, tool), UNKNOWN)

    def is_value_source(self, suite: str, tool: str) -> bool:
        """Whether the tool's output counts as a source of values (provenance)."""
        return self.category(suite, tool) in READS or (suite, tool) in self.untrusted_output_writes

    def output_untrusted(self, suite: str, tool: str) -> bool:
        """Whether the tool's output can contain free text written by someone else."""
        return (
            self.category(suite, tool) == "read_untrusted"
            or (suite, tool) in self.untrusted_output_writes
        )

    def sequence(self, record: dict[str, Any]) -> list[str]:
        """Categories of a run's tool calls, in order (requested calls included)."""
        return [self.category(record["suite"], c["function"]) for c in record["tool_calls"]]


def parse_tool_categories(cfg: dict[str, Any]) -> ToolCategories:
    """Build ``ToolCategories`` from the YAML structure, rejecting undefined categories."""
    names = tuple(cfg["categories"])
    if UNKNOWN not in names:
        raise ValueError(f"The category list must include {UNKNOWN!r}")
    of_tool = {}
    for suite, tools in cfg["tools"].items():
        for tool, category in tools.items():
            if category not in names or category == UNKNOWN:
                raise ValueError(f"{suite}/{tool}: invalid category {category!r}")
            of_tool[(suite, tool)] = category
    echo = set()
    for suite, tools in (cfg.get("untrusted_output_writes") or {}).items():
        for tool in tools:
            category = of_tool.get((suite, tool))
            if category is None or category in READS:
                raise ValueError(f"{suite}/{tool}: untrusted_output_writes must list write tools")
            echo.add((suite, tool))
    return ToolCategories(names, of_tool, frozenset(echo))


def load_tool_categories(path: str | Path) -> ToolCategories:
    return parse_tool_categories(load_config(path))


def check_covers_suites(cats: ToolCategories, suite_tools: Mapping[str, Iterable[str]]) -> None:
    """Raise unless the mapping covers exactly the tools each suite defines."""
    expected = {(s, t) for s, tools in suite_tools.items() for t in tools}
    missing = expected - set(cats.of_tool)
    extra = set(cats.of_tool) - expected
    if missing or extra:
        raise ValueError(f"Tool mapping mismatch: missing {sorted(missing)}, extra {sorted(extra)}")
