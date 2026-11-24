import csv
import warnings

import pytest

from trace_ad.config import repo_path
from trace_ad.features.categories import load_tool_categories
from trace_ad.features.intent import (
    ACTION_CATEGORIES,
    IncompleteLabelsError,
    IntentLabel,
    compare_with_ground_truth,
    first_mismatch_step,
    ground_truth_intent,
    main,
    mismatch_flags,
    parse_intent_labels,
    read_label_sheet,
    running_mismatch_count,
    unlabelled_tasks,
)

CATS = load_tool_categories(repo_path("configs/tool_categories.yaml"))
SHEET = repo_path("labels/user_task_intent.csv")


def _row(suite="banking", task="user_task_0", delegated="0", **actions):
    row = {"suite": suite, "user_task_id": task, "prompt": "", "older_wording": "", "notes": ""}
    row.update({c: actions.get(c, "0") for c in ACTION_CATEGORIES})
    row["delegated"] = delegated
    return row


# --- the sheet --------------------------------------------------------------------


def test_sheet_lists_every_user_task_once():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from agentdojo.task_suite.load_suites import get_suites

        expected = {(s, t) for s, suite in get_suites("v1.2.1").items() for t in suite.user_tasks}
    rows = read_label_sheet(SHEET)
    keys = [(r["suite"], r["user_task_id"]) for r in rows]
    assert len(keys) == len(set(keys)) == 97
    assert set(keys) == expected


def test_sheet_has_the_five_agreed_delegated_tasks():
    rows = read_label_sheet(SHEET)
    delegated = {(r["suite"], r["user_task_id"]) for r in rows if r["delegated"] == "1"}
    assert delegated == {
        ("banking", "user_task_12"),
        ("workspace", "user_task_13"),
        ("workspace", "user_task_25"),
        ("slack", "user_task_18"),
        ("slack", "user_task_19"),
    }


# --- validation -------------------------------------------------------------------


def test_incomplete_rows_are_reported_not_guessed():
    rows = [_row(task="user_task_0"), _row(task="user_task_1", payment="")]
    assert unlabelled_tasks(rows) == [("banking", "user_task_1")]
    with pytest.raises(IncompleteLabelsError) as err:
        parse_intent_labels(rows)
    assert err.value.missing == [("banking", "user_task_1")]


def test_delegated_rows_need_no_action_cells():
    rows = [_row(delegated="1", write="", delete="", send="", payment="", access="")]
    (label,) = parse_intent_labels(rows).values()
    assert label.delegated


def test_invalid_cell_value_rejected():
    with pytest.raises(ValueError, match="expected 0 or 1"):
        unlabelled_tasks([_row(payment="yes")])


# --- feature ----------------------------------------------------------------------


def test_mismatch_flags_follow_the_rules():
    labels = {
        ("workspace", "user_task_0"): IntentLabel(frozenset()),  # read-only
        ("banking", "user_task_0"): IntentLabel(frozenset({"payment"})),
        ("banking", "user_task_12"): IntentLabel(frozenset(), delegated=True),
    }
    read_only = {
        "suite": "workspace",
        "user_task_id": "user_task_0",
        "tool_calls": [
            {"function": "get_current_day"},
            {"function": "search_calendar_events"},
            {"function": "delete_file"},  # the tampering example from the decision
            {"function": "made_up_tool"},  # unknown never mismatches
        ],
    }
    flags = mismatch_flags(read_only, labels, CATS)
    assert flags == [False, False, True, False]
    assert running_mismatch_count(flags) == [0, 0, 1, 1]
    assert first_mismatch_step(flags) == 2

    pay = {
        "suite": "banking",
        "user_task_id": "user_task_0",
        "tool_calls": [{"function": "send_money"}, {"function": "update_password"}],
    }
    assert mismatch_flags(pay, labels, CATS) == [False, True]  # payment allowed, access not

    delegated = {**pay, "user_task_id": "user_task_12"}
    assert mismatch_flags(delegated, labels, CATS) == [False, False]
    assert first_mismatch_step([False, False]) is None


# --- ground-truth check -------------------------------------------------------------


def test_ground_truth_intent_examples():
    truth = ground_truth_intent(CATS)
    assert len(truth) == 97
    assert truth[("banking", "user_task_10")] == frozenset()  # "pay the bill, like last month"
    assert truth[("banking", "user_task_0")] == frozenset({"payment"})


def test_compare_lists_only_disagreements_and_skips_delegated():
    labels = {
        ("banking", "user_task_0"): IntentLabel(frozenset({"payment"})),
        ("banking", "user_task_10"): IntentLabel(frozenset({"payment"})),
        ("banking", "user_task_12"): IntentLabel(frozenset(), delegated=True),
    }
    truth = {k: frozenset() for k in labels} | {("banking", "user_task_0"): frozenset({"payment"})}
    rows = compare_with_ground_truth(labels, truth)
    assert rows == [
        {"task": "banking/user_task_10", "only_in_labels": ["payment"], "only_in_ground_truth": []}
    ]


def test_check_command_withholds_ground_truth_until_complete(tmp_path, capsys):
    path = tmp_path / "sheet.csv"
    rows = [_row(task="user_task_0"), _row(task="user_task_1", payment="")]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    main(["--labels", str(path)])
    out = capsys.readouterr().out
    assert "Labelled: 1 of 2" in out
    assert "only once every task is labelled" in out
    assert "Agreement" not in out
