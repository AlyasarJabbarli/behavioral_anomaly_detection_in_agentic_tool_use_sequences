import copy

import pytest

from trace_ad.config import load_config, repo_path
from trace_ad.data.agentdojo_tasks import injection_task_table
from trace_ad.data.families import (
    filter_visible,
    injection_task_of,
    is_visible,
    load_attack_families,
    parse_attack_families,
)

CONFIG = repo_path("configs/attack_families.yaml")


@pytest.fixture(scope="module")
def families():
    return load_attack_families(CONFIG)


def _rec(suite, user_task_id, injection_task_id=None):
    return {"suite": suite, "user_task_id": user_task_id, "injection_task_id": injection_task_id}


def test_every_injection_task_has_exactly_one_family(families):
    defined = {(r["suite"], r["injection_task_id"]) for r in injection_task_table("v1.2.1")}
    assert set(families.family_of_task) == defined


def test_option_a_split(families):
    assert families.split_of_family == {
        "exfiltration": "development",
        "tampering": "development",
        "financial_theft": "held_out",
        "phishing_links": "held_out",
        "text_only": "limitation",
    }
    assert families.family("banking", "injection_task_5") == "financial_theft"
    assert families.split("slack", "injection_task_3") == "held_out"
    assert families.split("travel", "injection_task_6") == "limitation"


def test_injection_task_of():
    assert injection_task_of(_rec("banking", "user_task_0")) is None
    assert injection_task_of(_rec("banking", "user_task_0", "injection_task_4")) == (
        "injection_task_4"
    )
    # An injection task run on its own as the user's request.
    assert injection_task_of(_rec("banking", "injection_task_4")) == "injection_task_4"


def test_guard_hides_held_out_runs_by_default(families):
    benign = _rec("banking", "user_task_0")
    dev_attack = _rec("banking", "user_task_0", "injection_task_7")  # tampering
    held_attack = _rec("banking", "user_task_0", "injection_task_5")  # financial theft
    held_alone = _rec("banking", "injection_task_5")  # financial theft, run alone
    limitation = _rec("travel", "user_task_1", "injection_task_6")

    visible = list(
        filter_visible([benign, dev_attack, held_attack, held_alone, limitation], families)
    )
    assert visible == [benign, dev_attack, limitation]
    assert not is_visible(held_alone, families)


def test_guard_shows_everything_only_for_final_evaluation(families):
    held_attack = _rec("slack", "user_task_2", "injection_task_1")
    assert not is_visible(held_attack, families)
    assert is_visible(held_attack, families, final_evaluation=True)


def test_unassigned_task_raises(families):
    with pytest.raises(KeyError):
        is_visible(_rec("banking", "user_task_0", "injection_task_99"), families)


def test_config_validation_rejects_mistakes():
    base = load_config(CONFIG)

    dup = copy.deepcopy(base)
    dup["families"]["tampering"]["tasks"]["banking"].append(5)  # also in financial_theft
    with pytest.raises(ValueError, match="assigned to both"):
        parse_attack_families(dup)

    two_splits = copy.deepcopy(base)
    two_splits["splits"]["development"].append("financial_theft")
    with pytest.raises(ValueError, match="more than one split"):
        parse_attack_families(two_splits)

    missing = copy.deepcopy(base)
    missing["splits"]["limitation"] = []
    with pytest.raises(ValueError, match="not assigned to a split"):
        parse_attack_families(missing)
