from collections import Counter

from trace_ad.data.agentdojo_tasks import injection_task_table


def test_injection_task_counts_per_version():
    # Counts match the injection-task ids present in the recorded runs.
    v1 = Counter(r["suite"] for r in injection_task_table("v1"))
    v121 = Counter(r["suite"] for r in injection_task_table("v1.2.1"))
    assert v1 == {"workspace": 6, "travel": 7, "banking": 9, "slack": 5}
    assert v121 == {"workspace": 14, "travel": 7, "banking": 9, "slack": 5}


def test_ground_truth_functions_are_tool_names():
    rows = {(r["suite"], r["injection_task_id"]): r for r in injection_task_table("v1.2.1")}
    assert rows[("banking", "injection_task_5")]["ground_truth_functions"] == ["send_money"]
