"""Attack families and the held-out guard.

Injection tasks are grouped into attacker-goal families (configs/attack_families.yaml),
and each family is assigned to one split: ``development``, ``held_out`` or
``limitation``. Held-out families may be used exactly once, for the final
evaluation. ``filter_visible`` is the single gate every experiment should read
records through: it hides runs of held-out families unless the caller passes
``final_evaluation=True`` explicitly.

A record belongs to an injection task if either
- it is an attack run (``injection_task_id`` is set), or
- it is an injection task run on its own as if it were the user's request
  (``user_task_id`` is ``"injection_task_<n>"``). These runs contain the attack
  behaviour itself, so they must be hidden too.
Benign user-task runs belong to no injection task and are always visible.

Note: denial-of-service attacks are recorded against the suite's first
injection task, so the guard treats them as that task's family (conservative).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trace_ad.config import load_config

SPLITS = ("development", "held_out", "limitation")


@dataclass(frozen=True)
class AttackFamilies:
    """Mapping from (suite, injection task id) to family, and family to split."""

    family_of_task: dict[tuple[str, str], str]
    split_of_family: dict[str, str]

    def family(self, suite: str, injection_task_id: str) -> str:
        try:
            return self.family_of_task[(suite, injection_task_id)]
        except KeyError:
            raise KeyError(
                f"Injection task {suite}/{injection_task_id} is not assigned to any family"
            ) from None

    def split(self, suite: str, injection_task_id: str) -> str:
        return self.split_of_family[self.family(suite, injection_task_id)]


def parse_attack_families(cfg: dict[str, Any]) -> AttackFamilies:
    """Build and validate ``AttackFamilies`` from the YAML structure."""
    family_of_task: dict[tuple[str, str], str] = {}
    for family, spec in cfg["families"].items():
        for suite, numbers in spec["tasks"].items():
            for n in numbers:
                key = (suite, f"injection_task_{n}")
                if key in family_of_task:
                    raise ValueError(
                        f"{suite}/injection_task_{n} is assigned to both "
                        f"{family_of_task[key]!r} and {family!r}"
                    )
                family_of_task[key] = family

    split_of_family: dict[str, str] = {}
    for split, families in cfg["splits"].items():
        if split not in SPLITS:
            raise ValueError(f"Unknown split {split!r}; expected one of {SPLITS}")
        for family in families:
            if family not in cfg["families"]:
                raise ValueError(f"Split {split!r} lists unknown family {family!r}")
            if family in split_of_family:
                raise ValueError(f"Family {family!r} is in more than one split")
            split_of_family[family] = split

    unassigned = set(cfg["families"]) - set(split_of_family)
    if unassigned:
        raise ValueError(f"Families not assigned to a split: {sorted(unassigned)}")
    return AttackFamilies(family_of_task, split_of_family)


def load_attack_families(path: str | Path) -> AttackFamilies:
    """Load and validate configs/attack_families.yaml."""
    return parse_attack_families(load_config(path))


def injection_task_of(record: dict[str, Any]) -> str | None:
    """The injection task a run record belongs to, or None for benign user-task runs."""
    if record.get("injection_task_id"):
        return record["injection_task_id"]
    if record["user_task_id"].startswith("injection_task_"):
        return record["user_task_id"]
    return None


def is_visible(
    record: dict[str, Any], families: AttackFamilies, final_evaluation: bool = False
) -> bool:
    """False for runs of held-out families, unless ``final_evaluation`` is True."""
    task = injection_task_of(record)
    if task is None:
        return True
    split = families.split(record["suite"], task)  # raises on unassigned tasks
    return final_evaluation or split != "held_out"


def filter_visible(
    records: Iterable[dict[str, Any]], families: AttackFamilies, final_evaluation: bool = False
) -> Iterator[dict[str, Any]]:
    """Yield only the records an experiment is allowed to see."""
    for record in records:
        if is_visible(record, families, final_evaluation):
            yield record
