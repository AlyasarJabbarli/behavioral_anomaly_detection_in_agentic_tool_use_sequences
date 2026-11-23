"""Tests for the AgentDojo run-file parser, using small synthetic transcripts
that mirror the shapes found in the real files (string vs block content,
missing call ids, parallel calls, unexecuted trailing calls)."""

import json
from pathlib import Path

import pytest

from trace_ad.data.agentdojo_runs import (
    content_to_text,
    flatten_tool_calls,
    iter_runs,
    parse_run,
    read_jsonl,
    run_id_from_path,
    write_jsonl,
)


def _call(fn, args=None, call_id=None):
    return {"function": fn, "args": args or {}, "id": call_id}


def _result(fn, content, call_id=None, error=None):
    return {
        "role": "tool",
        "content": content,
        "tool_call_id": call_id,
        "tool_call": {"function": fn, "args": {}},
        "error": error,
    }


def _raw_run(messages, **overrides):
    raw = {
        "suite_name": "banking",
        "pipeline_name": "model-x",
        "user_task_id": "user_task_0",
        "injection_task_id": None,
        "attack_type": None,
        "injections": {},
        "messages": messages,
        "error": None,
        "utility": True,
        "security": True,
        "duration": 1.5,
    }
    raw.update(overrides)
    return raw


BASIC_MESSAGES = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": [{"type": "text", "content": "Pay my bill"}]},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [_call("read_file", {"file_path": "b.txt"})],
    },
    _result("read_file", "bill text"),
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            _call("get_balance", call_id="a"),
            _call("send_money", {"recipient": "X1", "amount": 1}, call_id="b"),
        ],
    },
    _result("get_balance", [{"type": "text", "content": "100"}], call_id="a"),
    _result("send_money", "sent", call_id="b", error=None),
    {"role": "assistant", "content": "Done.", "tool_calls": None},
]


def test_content_to_text_handles_both_formats():
    assert content_to_text("hi") == "hi"
    assert content_to_text(None) is None
    blocks = [{"type": "text", "content": "a"}, {"type": "text", "content": "b"}]
    assert content_to_text(blocks) == "a\nb"
    with pytest.raises(TypeError):
        content_to_text(42)


def test_flatten_orders_calls_and_pairs_results():
    calls = flatten_tool_calls(BASIC_MESSAGES)
    assert [c["function"] for c in calls] == ["read_file", "get_balance", "send_money"]
    assert [c["step"] for c in calls] == [0, 1, 2]
    assert [c["message_index"] for c in calls] == [2, 4, 4]
    assert calls[0]["output"] == "bill text"
    assert calls[1]["output"] == "100"
    assert calls[2]["args"] == {"recipient": "X1", "amount": 1}
    assert all(c["executed"] for c in calls)


def test_trailing_unexecuted_calls_are_kept_and_marked():
    messages = BASIC_MESSAGES[:4] + [
        {"role": "assistant", "content": None, "tool_calls": [_call("send_money"), _call("x")]}
    ]
    calls = flatten_tool_calls(messages)
    assert [c["function"] for c in calls] == ["read_file", "send_money", "x"]
    assert [c["executed"] for c in calls] == [True, False, False]
    assert calls[1]["output"] is None


def test_mismatched_result_raises():
    messages = [
        {"role": "assistant", "content": None, "tool_calls": [_call("a")]},
        _result("b", "out"),
    ]
    with pytest.raises(ValueError):
        flatten_tool_calls(messages)


def test_parse_run_copies_agentdojo_fields_unchanged():
    rec = parse_run(
        _raw_run(
            BASIC_MESSAGES,
            injection_task_id="injection_task_1",
            attack_type="important_instructions",
            security=False,
            benchmark_version="v1.2.1",
        ),
        "model-x/banking/user_task_0/important_instructions/injection_task_1",
    )
    assert rec["user_prompt"] == "Pay my bill"
    assert rec["system_prompt"] == "sys"
    assert rec["final_output"] == "Done."
    assert rec["security"] is False
    assert rec["benchmark_version"] == "v1.2.1"
    assert rec["n_messages"] == len(BASIC_MESSAGES)
    assert len(rec["tool_calls"]) == 3


def test_pipeline_comes_from_directory_not_recorded_name():
    rec = parse_run(_raw_run([], pipeline_name="local"), "some-model/banking/user_task_0/none/none")
    assert rec["pipeline"] == "some-model"
    assert rec["pipeline_recorded"] == "local"


def test_parse_run_empty_transcript():
    rec = parse_run(_raw_run([]), "m/banking/user_task_0/none/none")
    assert rec["tool_calls"] == []
    assert rec["user_prompt"] is None
    assert rec["n_messages"] == 0


def test_end_to_end_directory_roundtrip(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    f = runs_dir / "model-x" / "banking" / "user_task_0" / "none" / "none.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps(_raw_run(BASIC_MESSAGES)))

    assert run_id_from_path(f, runs_dir) == "model-x/banking/user_task_0/none/none"
    out = tmp_path / "out.jsonl"
    assert write_jsonl(iter_runs(runs_dir), out) == 1
    (rec,) = list(read_jsonl(out))
    assert rec["run_id"] == "model-x/banking/user_task_0/none/none"
    assert [c["function"] for c in rec["tool_calls"]] == ["read_file", "get_balance", "send_money"]
