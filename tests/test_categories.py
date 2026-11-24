import warnings

import pytest

from trace_ad.config import load_config, repo_path
from trace_ad.features.categories import (
    UNKNOWN,
    check_covers_suites,
    load_tool_categories,
    parse_tool_categories,
)

PATH = repo_path("configs/tool_categories.yaml")
CATS = load_tool_categories(PATH)


def _suite_tools(version):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from agentdojo.task_suite.load_suites import get_suites

        return {name: [t.name for t in s.tools] for name, s in get_suites(version).items()}


@pytest.mark.parametrize("version", ["v1", "v1.1.2", "v1.2.1", "v1.2.2"])
def test_mapping_covers_every_agentdojo_tool_exactly(version):
    check_covers_suites(CATS, _suite_tools(version))


def test_option_b_category_set():
    assert set(CATS.names) == {
        "read_trusted",
        "read_untrusted",
        "write",
        "delete",
        "send",
        "payment",
        "access",
        "unknown",
    }


@pytest.mark.parametrize(
    ("suite", "tool", "expected"),
    [
        # the semantic untrusted rule, including where AgentDojo has no injection slot
        ("slack", "read_channel_messages", "read_untrusted"),
        ("slack", "get_channels", "read_trusted"),
        ("banking", "get_most_recent_transactions", "read_untrusted"),
        ("banking", "get_scheduled_transactions", "read_trusted"),
        ("workspace", "get_sent_emails", "read_untrusted"),
        # write tools that echo third-party text keep their action category
        ("workspace", "delete_file", "delete"),
        ("workspace", "append_to_file", "write"),
        # judgement calls
        ("workspace", "share_file", "send"),
        ("travel", "reserve_restaurant", "payment"),
        ("workspace", "add_calendar_event_participants", "write"),
        ("slack", "remove_user_from_slack", "access"),
    ],
)
def test_agreed_assignments(suite, tool, expected):
    assert CATS.category(suite, tool) == expected


def test_unknown_tools_and_sequence():
    assert CATS.category("travel", "get_current_date") == UNKNOWN
    run = {
        "suite": "workspace",
        "tool_calls": [
            {"function": "list_files"},
            {"function": "delete_file"},
            {"function": "create_calendar_event"},
            {"function": "search_files_by_content"},  # invented by the model
        ],
    }
    assert CATS.sequence(run) == ["read_untrusted", "delete", "write", UNKNOWN]


def test_invalid_category_rejected():
    cfg = load_config(PATH)
    cfg["tools"]["banking"]["send_money"] = "transfer"
    with pytest.raises(ValueError, match="invalid category"):
        parse_tool_categories(cfg)
    cfg["tools"]["banking"]["send_money"] = UNKNOWN
    with pytest.raises(ValueError, match="invalid category"):
        parse_tool_categories(cfg)


def test_coverage_check_reports_gaps():
    with pytest.raises(ValueError, match="missing"):
        check_covers_suites(CATS, {"banking": ["send_money", "brand_new_tool"]})


def test_untrusted_output_flag():
    echo = {"delete_file", "append_to_file", "share_file", "add_calendar_event_participants"}
    assert {t for s, t in CATS.untrusted_output_writes} == echo
    assert CATS.output_untrusted("workspace", "delete_file")
    assert CATS.output_untrusted("slack", "read_channel_messages")
    assert not CATS.output_untrusted("slack", "get_channels")  # kept trusted
    assert not CATS.output_untrusted("workspace", "send_email")
    assert CATS.is_value_source("workspace", "delete_file")
    assert CATS.is_value_source("banking", "get_iban")
    assert not CATS.is_value_source("banking", "send_money")  # echoes the agent's own arguments
    assert not CATS.is_value_source("travel", "get_current_date")  # unknown tool


def test_untrusted_output_writes_must_be_write_tools():
    cfg = load_config(PATH)
    cfg["untrusted_output_writes"] = {"workspace": ["search_emails"]}
    with pytest.raises(ValueError, match="must list write tools"):
        parse_tool_categories(cfg)
