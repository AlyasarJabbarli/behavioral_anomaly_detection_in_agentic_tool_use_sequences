"""Select which recorded runs are used (configs/data_selection.yaml).

A **normal run** is:
- a user-task run (``user_task_id`` is ``"user_task_<n>"``) with no attack
  (``attack_type`` is None). Injection tasks run on their own are not normal:
  they are attack goals given to the agent as if the user had asked for them;
- from a pipeline that is not excluded in the config (the exclusion list is
  shared with attack runs);
- without a run-level error, if ``drop_run_errors`` is set (API failures cut
  the trace short for reasons unrelated to the agent's behaviour).

Deliberately kept: runs where the agent failed the user's task (the detector
cannot know task success at run time), runs with no tool calls, and calls
that were requested but never executed (a monitor sees a call when it is
requested).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


def pipeline_included(pipeline: str, selection: dict[str, Any]) -> bool:
    """True unless the pipeline is in ``pipelines.exclude`` (applies to all runs)."""
    return pipeline not in set(selection["pipelines"]["exclude"])


def check_excluded_pipelines_exist(selection: dict[str, Any], known: Iterable[str]) -> None:
    """Raise if an excluded pipeline name does not occur in the data (catches typos)."""
    unknown = set(selection["pipelines"]["exclude"]) - set(known)
    if unknown:
        raise ValueError(f"Excluded pipelines not found in the data: {sorted(unknown)}")


def is_normal_run(record: dict[str, Any], selection: dict[str, Any]) -> bool:
    """Whether a parsed run record counts as normal (see module docstring)."""
    if record["attack_type"] is not None:
        return False
    if not record["user_task_id"].startswith("user_task_"):
        return False
    if not pipeline_included(record["pipeline"], selection):
        return False
    return not (selection["normal"]["drop_run_errors"] and record["error"] is not None)


def select_normal(
    records: Iterable[dict[str, Any]], selection: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    """Yield the normal runs among ``records``."""
    for record in records:
        if is_normal_run(record, selection):
            yield record
