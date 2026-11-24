"""Intent mismatch: actions the agent takes that the user's request did not allow.

Each user task has a hand label (labels/user_task_intent.csv, made from the
prompt text only; see docs/intent-labelling-guide.md): which action categories
(write, delete, send, payment, access) the request allows, or "delegated" when
the request hands the decision to content the agent must read.

A call is a **mismatch** if its category is an action category that the
task's label does not allow. Reads and unknown tools never mismatch, and
delegated tasks never mismatch.

AgentDojo's ground truth is used only as an independent check of the labels
(``trace-ad-intent-check``), and only once every task is labelled.

Usage:
    trace-ad-intent-check [--labels labels/user_task_intent.csv]
"""

from __future__ import annotations

import argparse
import csv
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trace_ad.config import repo_path
from trace_ad.features.categories import ToolCategories, load_tool_categories

ACTION_CATEGORIES = ("write", "delete", "send", "payment", "access")
TaskKey = tuple[str, str]  # (suite, user_task_id)


@dataclass(frozen=True)
class IntentLabel:
    """Action categories a user request allows."""

    allowed: frozenset[str]
    delegated: bool = False

    def allows(self, category: str) -> bool:
        if self.delegated or category not in ACTION_CATEGORIES:
            return True
        return category in self.allowed


class IncompleteLabelsError(ValueError):
    """Raised when some tasks are not labelled yet."""

    def __init__(self, missing: list[TaskKey]):
        self.missing = missing
        super().__init__(f"{len(missing)} user tasks are not labelled yet")


def read_label_sheet(path: str | Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _flag(value: str, where: str) -> bool | None:
    value = (value or "").strip()
    if value == "":
        return None
    if value not in ("0", "1"):
        raise ValueError(f"{where}: expected 0 or 1, got {value!r}")
    return value == "1"


def unlabelled_tasks(rows: list[dict[str, str]]) -> list[TaskKey]:
    """Tasks whose row is not complete yet (validates every filled cell)."""
    missing = []
    for row in rows:
        key = (row["suite"], row["user_task_id"])
        where = f"{key[0]}/{key[1]}"
        delegated = _flag(row["delegated"], f"{where} delegated")
        actions = [_flag(row[c], f"{where} {c}") for c in ACTION_CATEGORIES]
        if delegated is None or (not delegated and None in actions):
            missing.append(key)
    return missing


def parse_intent_labels(rows: list[dict[str, str]]) -> dict[TaskKey, IntentLabel]:
    """Labels per task; raises ``IncompleteLabelsError`` unless every row is complete."""
    missing = unlabelled_tasks(rows)
    if missing:
        raise IncompleteLabelsError(missing)
    labels = {}
    for row in rows:
        allowed = frozenset(c for c in ACTION_CATEGORIES if row[c].strip() == "1")
        labels[(row["suite"], row["user_task_id"])] = IntentLabel(
            allowed=allowed, delegated=row["delegated"].strip() == "1"
        )
    return labels


def load_intent_labels(path: str | Path) -> dict[TaskKey, IntentLabel]:
    return parse_intent_labels(read_label_sheet(path))


# --- feature ------------------------------------------------------------------


def mismatch_flags(
    record: dict[str, Any], labels: dict[TaskKey, IntentLabel], cats: ToolCategories
) -> list[bool]:
    """One flag per tool call: True if the call is an action the request did not allow."""
    label = labels[(record["suite"], record["user_task_id"])]
    return [not label.allows(category) for category in cats.sequence(record)]


def running_mismatch_count(flags: list[bool]) -> list[int]:
    """Number of mismatches up to and including each step."""
    counts, total = [], 0
    for flag in flags:
        total += flag
        counts.append(total)
    return counts


def first_mismatch_step(flags: list[bool]) -> int | None:
    return next((step for step, flag in enumerate(flags) if flag), None)


# --- independent check against AgentDojo ground truth -------------------------------


def ground_truth_intent(cats: ToolCategories, version: str = "v1.2.1") -> dict[TaskKey, frozenset]:
    """Action categories of the calls in each user task's AgentDojo ground truth."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from agentdojo.task_suite.load_suites import get_suites

        suites = get_suites(version)
    out = {}
    for name, suite in suites.items():
        env = suite.load_and_inject_default_environment({})
        for task_id, task in suite.user_tasks.items():
            calls = task.ground_truth(task.init_environment(env.model_copy(deep=True)))
            used = {cats.category(name, c.function) for c in calls}
            out[(name, task_id)] = frozenset(used & set(ACTION_CATEGORIES))
    return out


def compare_with_ground_truth(
    labels: dict[TaskKey, IntentLabel], truth: dict[TaskKey, frozenset]
) -> list[dict[str, Any]]:
    """One row per non-delegated task whose label differs from the ground truth."""
    rows = []
    for key in sorted(labels):
        label = labels[key]
        if label.delegated or label.allowed == truth[key]:
            continue
        rows.append(
            {
                "task": f"{key[0]}/{key[1]}",
                "only_in_labels": sorted(label.allowed - truth[key]),
                "only_in_ground_truth": sorted(truth[key] - label.allowed),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Check intent labels against AgentDojo.")
    parser.add_argument("--labels", default="labels/user_task_intent.csv")
    parser.add_argument("--categories", default="configs/tool_categories.yaml")
    args = parser.parse_args(argv)

    rows = read_label_sheet(repo_path(args.labels))
    missing = unlabelled_tasks(rows)
    print(f"Labelled: {len(rows) - len(missing)} of {len(rows)} user tasks")
    if missing:
        print("Ground-truth comparison is shown only once every task is labelled.")
        print("Not labelled yet: " + ", ".join(f"{s}/{t}" for s, t in missing))
        return

    labels = parse_intent_labels(rows)
    truth = ground_truth_intent(load_tool_categories(repo_path(args.categories)))
    judged = [k for k, v in labels.items() if not v.delegated]
    disagreements = compare_with_ground_truth(labels, truth)
    agree = len(judged) - len(disagreements)
    print(f"Agreement with ground truth: {agree} of {len(judged)} non-delegated tasks")
    for c in ACTION_CATEGORIES:
        both = sum((c in labels[k].allowed) == (c in truth[k]) for k in judged)
        print(f"  {c:8s} agrees on {both} of {len(judged)}")
    for row in disagreements:
        print(
            f"  {row['task']}: only in your labels {row['only_in_labels']}, "
            f"only in ground truth {row['only_in_ground_truth']}"
        )


if __name__ == "__main__":
    main()
