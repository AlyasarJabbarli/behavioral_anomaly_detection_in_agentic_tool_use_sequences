"""Read task definitions (user tasks, injection tasks) from the pinned agentdojo package.

These are the benchmark's *definitions*, not recorded behaviour. They are
needed to group injection tasks into attack families and, later, to locate
harmful calls via each injection task's ground-truth function calls.
"""

from __future__ import annotations

import warnings
from typing import Any


def _get_suites(benchmark_version: str) -> dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from agentdojo.task_suite.load_suites import get_suites

        return get_suites(benchmark_version)


def _task_number(task_id: str) -> int:
    return int(task_id.rsplit("_", 1)[-1])


def injection_task_table(benchmark_version: str = "v1.2.1") -> list[dict[str, Any]]:
    """One row per injection task: suite, id, goal text, ground-truth function names.

    Ground truth is evaluated on each suite's default environment. Some tasks
    return an empty ground truth (their success is checked another way).
    """
    rows = []
    for suite_name, suite in _get_suites(benchmark_version).items():
        env = suite.load_and_inject_default_environment({})
        for task_id in sorted(suite.injection_tasks, key=_task_number):
            task = suite.injection_tasks[task_id]
            calls = task.ground_truth(env.model_copy(deep=True))
            rows.append(
                {
                    "suite": suite_name,
                    "injection_task_id": task_id,
                    "goal": task.GOAL,
                    "ground_truth_functions": [c.function for c in calls],
                }
            )
    return rows
