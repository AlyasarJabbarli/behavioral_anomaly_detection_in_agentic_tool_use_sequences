"""Parse recorded AgentDojo run files into one JSONL record per run.

Each run file lives at ``runs/<pipeline>/<suite>/<task>/<attack>/<file>.json``
and holds a full chat transcript plus AgentDojo's own evaluation fields.

This module does *no* filtering and derives *no* labels: every run file becomes
exactly one record, and AgentDojo's fields are copied as-is. Deciding which
runs count as normal or attack traces is a separate, explicit step.

Record schema (one JSON object per line)::

    run_id             "<pipeline>/<suite>/<task>/<attack>/<file stem>" (unique)
    pipeline           run directory name: model plus optional defence suffix,
                       e.g. "gpt-4o-2024-05-13-tool_filter"
    pipeline_recorded  "pipeline_name" field of the file (locally served models record "local")
    suite              "workspace" | "slack" | "travel" | "banking"
    user_task_id       e.g. "user_task_3" ("injection_task_2" when an injection task ran alone)
    injection_task_id  e.g. "injection_task_1", or None
    attack_type        e.g. "important_instructions", or None when no attack was run
    benchmark_version  e.g. "v1.2.1", or None when the run file does not record it
    utility            AgentDojo utility check (user task solved)
    security           AgentDojo security check. NOTE: True means the injection goal WAS achieved.
    error              run-level error message, or None
    duration           seconds, or None
    system_prompt      text of the system message, or None
    user_prompt        text of the first user message (the trusted request), or None
    injections         {injection placeholder: injected text} ({} for no-attack runs)
    final_output       text of the last assistant message, or None
    n_messages         number of messages in the transcript
    tool_calls         ordered list, one entry per tool call requested by the agent:
        step           0-based position in the flattened call sequence
        message_index  index of the assistant message that requested the call
        call_id        provider call id, or None (older runs do not record ids)
        function       tool name
        args           argument dict
        executed       False if the run ended before the call was executed
        output         text returned by the tool, or None if not executed
        tool_error     error raised by the tool, or None

Tool outputs can contain prompt-injection text by design. They are stored as
data only.

Usage:
    trace-ad-parse --config configs/data.yaml
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from trace_ad.config import load_config, repo_path


def content_to_text(content: Any) -> str | None:
    """Normalise message content to plain text.

    Older run files store a string; newer ones store a list of content blocks
    such as ``[{"type": "text", "content": "..."}]``.
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("content") or "" for b in content if b.get("type") == "text"]
        return "\n".join(parts)
    raise TypeError(f"Unexpected message content type: {type(content).__name__}")


def flatten_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the ordered tool calls of a transcript, each paired with its result.

    An assistant message may request several calls at once. The tool messages
    that follow it, in order, are the results of those calls. Pairing is by
    position, and the function names are checked to match. If the transcript
    ends before all requested calls ran, the rest are marked ``executed=False``.
    """
    calls: list[dict[str, Any]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg["role"] != "assistant" or not msg.get("tool_calls"):
            i += 1
            continue
        j = i + 1
        results = []
        while j < len(messages) and messages[j]["role"] == "tool":
            results.append(messages[j])
            j += 1
        requested = msg["tool_calls"]
        if len(results) > len(requested):
            raise ValueError(f"More tool results than calls after message {i}")
        for k, call in enumerate(requested):
            result = results[k] if k < len(results) else None
            if result is not None and result["tool_call"]["function"] != call["function"]:
                raise ValueError(
                    f"Tool result {j - len(results) + k} does not match call "
                    f"{call['function']!r} of message {i}"
                )
            calls.append(
                {
                    "step": len(calls),
                    "message_index": i,
                    "call_id": call.get("id"),
                    "function": call["function"],
                    "args": call.get("args") or {},
                    "executed": result is not None,
                    "output": content_to_text(result["content"]) if result else None,
                    "tool_error": result.get("error") if result else None,
                }
            )
        i = j
    return calls


def _first_text(messages: list[dict[str, Any]], role: str) -> str | None:
    for m in messages:
        if m["role"] == role:
            return content_to_text(m.get("content"))
    return None


def _last_assistant_text(messages: list[dict[str, Any]]) -> str | None:
    for m in reversed(messages):
        if m["role"] == "assistant":
            return content_to_text(m.get("content"))
    return None


def parse_run(raw: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Convert one raw run dict into a trace record (see module docstring)."""
    messages = raw.get("messages") or []
    return {
        "run_id": run_id,
        # The directory name identifies the pipeline; the recorded name is not
        # unique (several locally served models all record "local").
        "pipeline": run_id.split("/")[0],
        "pipeline_recorded": raw.get("pipeline_name"),
        "suite": raw["suite_name"],
        "user_task_id": raw["user_task_id"],
        "injection_task_id": raw.get("injection_task_id"),
        "attack_type": raw.get("attack_type"),
        "benchmark_version": raw.get("benchmark_version"),
        "utility": raw.get("utility"),
        "security": raw.get("security"),
        "error": raw.get("error"),
        "duration": raw.get("duration"),
        "system_prompt": _first_text(messages, "system"),
        "user_prompt": _first_text(messages, "user"),
        "injections": raw.get("injections") or {},
        "final_output": _last_assistant_text(messages),
        "n_messages": len(messages),
        "tool_calls": flatten_tool_calls(messages),
    }


def run_id_from_path(path: Path, runs_dir: Path) -> str:
    """``runs/<pipeline>/<suite>/<task>/<attack>/<file>.json`` -> ``<pipeline>/.../<file>``."""
    return path.relative_to(runs_dir).with_suffix("").as_posix()


def iter_runs(runs_dir: Path) -> Iterator[dict[str, Any]]:
    """Yield parsed records for every run file under ``runs_dir`` in sorted order."""
    for path in sorted(runs_dir.rglob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        yield parse_run(raw, run_id_from_path(path, runs_dir))


def write_jsonl(records: Iterator[dict[str, Any]], out_path: Path) -> int:
    """Write records to ``out_path`` as JSONL. Returns the number written."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield records from a JSONL file."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Parse AgentDojo run files into JSONL.")
    parser.add_argument("--config", default="configs/data.yaml")
    args = parser.parse_args(argv)

    cfg = load_config(repo_path(args.config))["agentdojo_runs"]
    runs_dir = repo_path(cfg["raw_dir"]) / "runs"
    out_path = repo_path(cfg["processed_path"])
    n = write_jsonl(iter_runs(runs_dir), out_path)
    print(f"Wrote {n} records to {out_path}")


if __name__ == "__main__":
    main()
