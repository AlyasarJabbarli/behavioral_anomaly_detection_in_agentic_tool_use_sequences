import pytest

from trace_ad.config import load_config, repo_path
from trace_ad.data.selection import (
    check_excluded_pipelines_exist,
    is_normal_run,
    pipeline_included,
    select_normal,
)

SELECTION = load_config(repo_path("configs/data_selection.yaml"))
PI = "gpt-4o-2024-05-13-transformers_pi_detector"


def _rec(**overrides):
    rec = {
        "pipeline": "gpt-4o-2024-05-13",
        "user_task_id": "user_task_0",
        "injection_task_id": None,
        "attack_type": None,
        "error": None,
        "utility": True,
        "tool_calls": [{"function": "read_file", "executed": True}],
    }
    rec.update(overrides)
    return rec


def test_option_b_excludes_only_the_pi_detector_pipeline():
    assert SELECTION["pipelines"]["exclude"] == [PI]
    assert not pipeline_included(PI, SELECTION)
    assert pipeline_included("gpt-4o-2024-05-13-tool_filter", SELECTION)
    assert pipeline_included("gpt-4o-2024-05-13-repeat_user_prompt", SELECTION)


def test_plain_benign_run_is_normal():
    assert is_normal_run(_rec(), SELECTION)


@pytest.mark.parametrize(
    "overrides",
    [
        {"attack_type": "important_instructions", "injection_task_id": "injection_task_1"},
        {"user_task_id": "injection_task_1"},  # injection task run on its own
        {"pipeline": PI},
        {"error": "Skipping task user_task_0 due to context_length_exceeded"},
    ],
)
def test_excluded_runs(overrides):
    assert not is_normal_run(_rec(**overrides), SELECTION)


@pytest.mark.parametrize(
    "overrides",
    [
        {"utility": False},  # failed the task
        {"tool_calls": []},  # no tool calls
        {"tool_calls": [{"function": "send_money", "executed": False}]},  # unexecuted call
        {"pipeline": "gpt-4o-2024-05-13-tool_filter"},  # other defences stay
    ],
)
def test_kept_runs(overrides):
    assert is_normal_run(_rec(**overrides), SELECTION)


def test_drop_run_errors_switch():
    keep_errors = {**SELECTION, "normal": {"drop_run_errors": False}}
    assert is_normal_run(_rec(error="server error"), keep_errors)


def test_select_normal_filters_a_stream():
    records = [_rec(), _rec(pipeline=PI), _rec(utility=False)]
    assert list(select_normal(records, SELECTION)) == [records[0], records[2]]


def test_excluded_pipeline_typo_is_caught():
    check_excluded_pipelines_exist(SELECTION, [PI, "gpt-4o-2024-05-13"])
    with pytest.raises(ValueError):
        check_excluded_pipelines_exist(SELECTION, ["gpt-4o-2024-05-13"])
