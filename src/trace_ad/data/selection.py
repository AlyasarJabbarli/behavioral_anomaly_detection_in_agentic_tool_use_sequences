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

An **attack run** (``select_attack_runs``) is:
- a run of an allowed attack type (``attacks.attack_types``; denial-of-service
  types are rejected), from a pipeline that is not excluded;
- without a run-level error (all of these are recorded as "attack succeeded"
  by AgentDojo although nothing happened), and with a non-empty transcript and
  a recorded security value;
- visible under the held-out guard (``families.filter_visible``).
Each selected run is labelled ``attack`` if AgentDojo's security check says the
injection goal was achieved, else ``failed_attempt``. Failed attempts are
reported separately and never used as normal runs.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from trace_ad.data.families import AttackFamilies, filter_visible, injection_task_of

ATTACK = "attack"
FAILED_ATTEMPT = "failed_attempt"


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


def check_attack_types(selection: dict[str, Any]) -> None:
    """Raise if a denial-of-service attack type is configured."""
    dos = [t for t in selection["attacks"]["attack_types"] if t.endswith("dos")]
    if dos:
        raise ValueError(f"Denial-of-service attack types are excluded by design: {dos}")


def is_usable_attack_run(record: dict[str, Any], selection: dict[str, Any]) -> bool:
    """Whether a run is an attack run we evaluate on (before the held-out guard)."""
    cfg = selection["attacks"]
    if record["attack_type"] not in cfg["attack_types"]:
        return False
    if not pipeline_included(record["pipeline"], selection):
        return False
    if cfg["drop_run_errors"] and record["error"] is not None:
        return False
    return not (
        cfg["drop_empty_transcripts"] and (record["n_messages"] == 0 or record["security"] is None)
    )


def attack_label(record: dict[str, Any]) -> str:
    """``attack`` if the injection goal was achieved, else ``failed_attempt``."""
    return ATTACK if record["security"] else FAILED_ATTEMPT


def select_attack_runs(
    records: Iterable[dict[str, Any]],
    selection: dict[str, Any],
    families: AttackFamilies,
    final_evaluation: bool = False,
) -> Iterator[dict[str, Any]]:
    """Yield usable attack runs, each extended with ``label``, ``family`` and ``split``.

    Always goes through the held-out guard: held-out families are only returned
    when ``final_evaluation`` is True.
    """
    check_attack_types(selection)
    usable = (r for r in records if is_usable_attack_run(r, selection))
    for record in filter_visible(usable, families, final_evaluation):
        task = injection_task_of(record)
        yield {
            **record,
            "label": attack_label(record),
            "family": families.family(record["suite"], task),
            "split": families.split(record["suite"], task),
        }
