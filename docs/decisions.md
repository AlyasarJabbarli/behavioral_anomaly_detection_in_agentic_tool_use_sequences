# Decision log

Every research-critical decision (labels, splits, features, models,
thresholds, metrics, held-out choices) is recorded here once made.

Format for each entry:

```
## YYYY-MM-DD — <short title>
Decision: what was decided.
Alternatives considered: the other options and their trade-offs.
Why: the reason for the choice.
```

## Open decisions

Listed in the order they need to be made. Only development-family attack
runs may be inspected (see the 2026-11-23 entry below).

1. **Definition of the "first harmful call"** for detection delay, given that
   ground truth includes read calls and is empty for some tasks. The same
   definition will split failed attack attempts into "made a harmful call" and
   "did not" (see the 2026-11-24 attack-label entry).

## Log

## 2026-11-23 — Attack families and held-out families

Decision: group the 35 AgentDojo injection tasks into five families by the
attacker's end goal (`configs/attack_families.yaml`):

| Family | Split | Tasks | Injection tasks |
|---|---|---|---|
| Data exfiltration | development | 20 | workspace 3–12; travel 1, 3, 5; slack 2, 4; banking 0–3, 8 |
| Tampering (data, calendar, accounts) | development | 5 | workspace 1, 2; travel 2; banking 7; slack 5 |
| Financial theft | **held out** | 5 | banking 4, 5, 6; travel 0, 4 |
| Phishing & malicious links | **held out** | 4 | workspace 0, 13; slack 1, 3 |
| Text-only | limitation case | 1 | travel 6 |

Assignment rules: a task goes to the family of the goal stated in its GOAL
text, not the tool it uses; tasks with several goals go to their first goal.
Judgement calls: banking 0–3 and 8 (leak data in the subject of a small
payment) → exfiltration; workspace 5–12 (exfiltrate, then delete the evidence
or the data, some with a fake ransom note) → exfiltration; workspace 0 (email
harmless text to an outside address) → phishing; slack 3 (visit a URL) →
phishing.

Alternatives considered:
- Hold out financial theft + tampering: the strictest test of unseen harmful
  actions, but development would contain almost no state-changing attacks, so
  features would be designed blind to that kind of harm.
- Hold out exfiltration: the most held-out data, but development would have
  only 14 tasks and would never see the most common threat.
- Group by attack type (`important_instructions`, `ignore_previous`, …): rejected
  because these are phrasings of the same goal, and the detector never reads
  injection text, so holding out phrasings would test nothing.

Why: all four suites appear in the held-out set (banking and travel through
financial theft, workspace and slack through phishing), so the final result
is not a single-suite result. Development still contains both "send data
out" and "change state" attacks. The grouping was made from the task
definitions only, before any attack trace or attack outcome was inspected.

Known limitation: held-out attacks use some of the same tools as development
attacks (`send_money` in banking exfiltration; `send_email` and
`send_direct_message` in exfiltration). The held-out test therefore measures
generalisation to unseen *goals* more than to unseen *tools*.

Enforcement: `trace_ad.data.families.filter_visible` hides held-out runs,
including injection tasks run on their own, unless called with
`final_evaluation=True`. Denial-of-service runs are recorded against each
suite's first injection task and follow that task's family. Resulting sizes:
23,661 development attack runs, 1,000 limitation-case runs, 8,688 held-out
runs hidden, and 2,756 benign runs.

## 2026-11-24 — Normal data

Decision: a run is **normal** if it is a user-task run with no attack, from
any pipeline except `gpt-4o-2024-05-13-transformers_pi_detector`, and has no
run-level error (`configs/data_selection.yaml`, `trace_ad.data.selection`).
Runs where the agent failed the user's task, runs with no tool calls, and
calls that were requested but never executed are kept. The same pipeline
exclusion applies to attack runs, so attacks are only evaluated on setups
whose normal behaviour was learned.

Result: 2,648 normal runs from 28 pipelines over all 97 user tasks (banking
432, slack 567, travel 539, workspace 1,110). Of these, 1,100 failed the
user's task, 214 make no tool call and 49 end with unexecuted calls. The
largest share from one model is gpt-4o at 14.7% (four pipelines).

Alternatives considered:
- Undefended pipelines only (22 pipelines, 2,123 runs): one pipeline per
  model and no defence effects, but 20% less data and no evidence about the
  detector running next to a defence.
- All 29 pipelines (2,745 runs): the most data, but includes the
  prompt-injection-detector pipeline, which replaced at least one tool output
  in 63 of its 97 normal runs (false positives). Its agents were reacting to
  censored data, which shows in a task-success rate of 41% against 55–72% for
  the other setups.
- Adding failed attack runs as extra normal data (not offered): breaks
  "trained only on normal logs", puts development-attack information into
  training, and partly followed attacks would contaminate the normal set.

Why: the repeat-prompt, spotlighting and tool-filter defences change the
agent's prompt or tool set, but the resulting behaviour is still genuine
normal use in a different deployment, and it adds variety (under the tool
filter, gpt-4o's call sequence matches its undefended run in only 54% of
tasks). The detector defence is the exception, because its normal runs are
distorted by false positives.

Rules and their reasons:
- Injection tasks run on their own are not normal: they are attack goals
  given as if the user asked for them.
- Run-level API errors (11 runs) are dropped: the trace was cut short by
  infrastructure, not by the agent.
- Failed tasks (42%) are kept: the detector cannot know task success at run
  time, and dropping failures would make ordinary failures look anomalous,
  inflating false alarms in real use.
- Zero-call runs and unexecuted calls are kept: a monitor sees a call when it
  is requested, so a requested call is observable behaviour.

## 2026-11-24 — Attack runs and labels

Decision: an **attack run** is an `important_instructions` run from a
non-excluded pipeline, without a run-level error, with a non-empty transcript
and a recorded security value, and visible under the held-out guard
(`configs/data_selection.yaml`, `trace_ad.data.selection.select_attack_runs`).
It is labelled `attack` if AgentDojo's security check says the injection goal
was achieved, otherwise `failed_attempt`. Main metrics compare `attack` runs
with normal test runs. Failed attempts are reported separately with their own
alarm rate, and are never used as normal runs. Travel injection task 6
(text-only) is reported only as the limitation case.

Result (development families): 2,226 attacks (exfiltration 1,178, tampering
1,048) over 96 user tasks and 27 pipelines, largest pipeline share 11%;
10,964 failed attempts. Limitation case: 540 runs, 95 attacks.

Cleanup rules and their reasons:
- Same pipeline exclusion as normal runs (prompt-injection-detector setup).
- Run-level API errors dropped (75 development/limitation runs): AgentDojo
  records every one of them as "attack succeeded" although nothing happened.
- Empty transcripts dropped (173), plus 1 run with no security value: there
  is no behaviour to score, and 7 empty runs are wrongly marked "succeeded".
- Denial-of-service attacks excluded (180 runs, gpt-4o only): their success
  means the agent failed the user's task; there is no harmful call to detect,
  and their injection task id is a placeholder.
- Label check: of 3,474 successful development runs (all attack types) whose
  injection task has a ground truth, only 1 never calls a ground-truth tool.
  AgentDojo's label is kept as the protocol requires.

Choice 1, failed attempts — alternatives considered:
- Count them as normal (negatives): one realistic number, but AgentDojo's
  success check is strict, and 3.8% of failed attempts (734 runs, all attack
  types) contain a call carrying the attacker's address, IBAN, URL or password.
  Catching those would be scored as false alarms. Example: in
  workspace/injection_task_4, `search_emails → send_email(to=<attacker>)` is
  labelled failed, with the same structure as a success.
- Count them as attacks (not offered): contradicts the label definition, and
  about 96% of them look entirely normal because the agent ignored the
  injection.
Why separate: keeps the main metrics exactly on the protocol's label
definition, while still showing behaviour on the realistic attack mix. A high
alarm rate on failed attempts that made a harmful call is a strength, not a
false alarm. The "made a harmful call" split needs the harmful-call
definition (open decision 1) and is added once that is decided.

Choice 2, attack types — alternatives considered:
- All non-DoS attack types: 3,487 development attacks (+57%), but three models
  (gpt-4o, Llama-3.3-70B, Meta-SecAlign-70B) would supply 62% of attack runs
  instead of 34%, and the same (user task, injection task) pair would appear up
  to 9 times for gpt-4o, overstating the effective sample size.
Why `important_instructions`: it is AgentDojo's headline attack and exists for
all 27 attack pipelines. The other types reword the same goals, and the
detector never reads wording, so they mostly add near-duplicates. They remain
available for a later robustness check.
