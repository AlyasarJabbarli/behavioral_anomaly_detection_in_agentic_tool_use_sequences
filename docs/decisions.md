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

Listed in the order they need to be made. Attack traces are not analysed
until the first one is settled, so that the held-out families stay unseen.

1. **Attack-family grouping and held-out families.** Assign each of the 35
   injection tasks (see `docs/agentdojo-notes.md` §7) to an attacker-goal
   family, and choose which families are held out for the single final test.
   To be decided from the task definitions only, before any attack trace is
   inspected.
2. **Which runs count as normal training data.** Benign user-task runs only, or
   also the "injection task run alone" files; with or without defended
   pipelines (`-tool_filter`, `-transformers_pi_detector`, …); how to treat
   runs with a run-level error, empty transcripts and unexecuted calls.
3. **Attack label details.** Successful (`security == True`, no error) attack
   runs are attacks. To decide: treatment of failed attack attempts in the test
   set, DoS attack types, and the text-only injection task (travel 6).
4. **Definition of the "first harmful call"** for detection delay, given that
   ground truth includes read calls and is empty for some tasks.

## Log

(No decisions recorded yet.)
