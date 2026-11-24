import pytest

from trace_ad.config import load_config, repo_path
from trace_ad.data.families import load_attack_families
from trace_ad.data.selection import (
    ATTACK,
    FAILED_ATTEMPT,
    check_excluded_pipelines_exist,
    is_normal_run,
    pipeline_included,
    select_attack_runs,
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


# --- attack runs (decision 2) -------------------------------------------------

FAMILIES = load_attack_families(repo_path("configs/attack_families.yaml"))


def _attack(**overrides):
    rec = _rec(
        suite="workspace",
        attack_type="important_instructions",
        injection_task_id="injection_task_4",  # exfiltration (development)
        security=True,
        n_messages=6,
    )
    rec.update(overrides)
    return rec


def _select(records, final_evaluation=False):
    return list(select_attack_runs(records, SELECTION, FAMILIES, final_evaluation))


def test_attack_config_is_option_a():
    assert SELECTION["attacks"]["attack_types"] == ["important_instructions"]


def test_success_is_labelled_attack_with_family_and_split():
    (out,) = _select([_attack()])
    assert (out["label"], out["family"], out["split"]) == (ATTACK, "exfiltration", "development")


def test_failure_is_labelled_failed_attempt():
    (out,) = _select([_attack(security=False)])
    assert out["label"] == FAILED_ATTEMPT


@pytest.mark.parametrize(
    "overrides",
    [
        {"attack_type": "direct"},  # other attack types (choice 2, option A)
        {"attack_type": "dos"},  # denial of service
        {"pipeline": PI},
        {"error": "Skipping task user_task_0 because of internal server error"},
        {"n_messages": 0},  # empty transcript
        {"security": None},  # no recorded label
    ],
)
def test_unusable_attack_runs_are_dropped(overrides):
    assert _select([_attack(**overrides)]) == []


def test_normal_runs_are_never_attack_runs():
    assert _select([_rec(suite="workspace", n_messages=4, security=True)]) == []


def test_held_out_attacks_need_final_evaluation():
    held = _attack(suite="banking", injection_task_id="injection_task_5")  # financial theft
    assert _select([held]) == []
    (out,) = _select([held], final_evaluation=True)
    assert out["split"] == "held_out"


def test_limitation_case_is_selected_with_its_own_split():
    (out,) = _select([_attack(suite="travel", injection_task_id="injection_task_6")])
    assert out["split"] == "limitation"


def test_dos_attack_type_in_config_is_rejected():
    bad = {**SELECTION, "attacks": {**SELECTION["attacks"], "attack_types": ["captcha_dos"]}}
    with pytest.raises(ValueError, match="Denial-of-service"):
        list(select_attack_runs([], bad, FAMILIES))
