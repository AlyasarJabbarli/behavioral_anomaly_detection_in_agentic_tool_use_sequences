# Intent labelling guide

Purpose: for each of the 97 AgentDojo user tasks, record which kinds of action
the user's request allows. The intent-mismatch feature flags any action the
agent takes outside this set. Decided 2026-11-24 (`docs/decisions.md`).

Sheet: `labels/user_task_intent.csv` (one row per user task).

## Protocol

- Label from the **prompt text only**. Do not look at AgentDojo's ground
  truth, the agent traces or the injection tasks while labelling. The
  ground-truth comparison (`trace-ad-intent-check`) only runs once every row is
  labelled, so the labels stay independent of it.
- Where `older_wording` is filled, the same task was asked with that wording in
  older benchmark versions. Give one label that fits both.
- Uncertain? Decide, and write the reason in `notes`. Uncertain rows are
  listed in the thesis.

## What to fill in

For each row, put `1` (allowed) or `0` (not allowed) in each action column.
An empty cell means "not labelled yet".

| Column | Allowed if the request asks for or clearly implies… |
|---|---|
| `write` | creating or changing the user's own data: a calendar event, a file, a reminder, profile details |
| `delete` | removing or cancelling data: deleting a file or email, cancelling an event |
| `send` | making content available to another person or site: an email, a message, a web post, sharing a file |
| `payment` | moving money or committing to a purchase or booking: a transfer, a standing order, a reservation |
| `access` | changing a password or who belongs to an account or workspace: inviting, adding, removing users |

Reading and looking things up is always allowed and has no column.

## Rules

1. **Explicit or clearly implied.** "Renew my gym membership fee" allows
   `payment`. "What time does the museum open?" allows nothing (all `0`).
2. **Conditional requests allow their action.** "If the train is delayed,
   email my manager" allows `send`.
3. **Delegated requests.** If the request hands the decision to content the
   agent must read ("follow the instructions in the file", "do the tasks on my
   to-do list at this URL"), put `1` in `delegated`; the action columns may
   then stay empty and the feature stays silent for that task. Five rows are
   pre-marked as agreed. A request that names the action but takes details
   from content (e.g. "renew my parking permit as the council letter
   describes") is **not** delegated: label the named action.
4. **Multi-part requests.** Allow the union of the actions of all parts.

## After labelling

Run:

```bash
trace-ad-intent-check
```

It reports how many rows are complete. When all are, it compares your labels
with the action categories of AgentDojo's ground-truth calls and lists every
disagreement, for the thesis.
