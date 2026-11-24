# Behavioural Anomaly Detection in Agentic Tool-Use Sequences

MSc thesis project, ELTE Faculty of Informatics (Data Science). Author: Alyasar Jabbarli.

## Research question

Can a lightweight detector trained **only on normal tool-use traces** detect
prompt-injection attacks it has never seen? How early in the trajectory does
it catch them, and how do models of increasing complexity compare?

Design principle: the detector uses only the **structure** of a trace (which
tools are called, argument types, where values came from), never the meaning
of untrusted text, so the detector itself cannot be prompt-injected.

## Status

| Step | State |
|---|---|
| Project setup (package, tests, lint) | done |
| Data: AgentDojo recorded runs downloaded and parsed to JSONL | done |
| Attack-family grouping and held-out choice (guard in `trace_ad.data.families`) | done |
| Normal data selection (`trace_ad.data.selection`) | done |
| Attack runs and labels (`select_attack_runs`) | done |
| Detection-delay definition (harm signatures, `trace_ad.eval.harm`) | done |
| Tool categories (`trace_ad.features.categories`) | done |
| Intent mismatch (`trace_ad.features.intent`) | code done; **hand labels in progress** (`labels/user_task_intent.csv`) |
| Value provenance (`trace_ad.features.provenance`) | done |
| Features (n-grams, novelty) | not started |
| Models: frequency baseline → Markov/n-gram → Isolation Forest → (LSTM AE) | not started |
| Evaluation (detection rate at 1%/5% FPR, PR/ROC-AUC, alarms per 1k runs, delay) | not started |

## Data

Primary source: the recorded runs published in the
[AgentDojo](https://github.com/ethz-spylab/agentdojo) repository (36,679 runs,
29 pipeline directories over 22 models, 4 suites, 97 user tasks, 35 injection
tasks). Details and verified semantics: [`docs/agentdojo-notes.md`](docs/agentdojo-notes.md).

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Download and parse the data (about 525 MB raw, 260 MB parsed; both gitignored):

```bash
trace-ad-download --config configs/data.yaml
trace-ad-parse --config configs/data.yaml
```

Check the intent labels (see `docs/intent-labelling-guide.md`):

```bash
trace-ad-intent-check
```

Run tests and lint:

```bash
pytest
ruff check src tests
```

## Repository layout

```
src/trace_ad/     data/ (download, parse, task definitions), features/, models/, eval/
configs/          YAML configs; every experiment is reproducible from one
data/             raw/ and processed/ (gitignored)
docs/             decisions.md (decision log), agentdojo-notes.md, intent-labelling-guide.md
labels/           hand-made labels (user-task intent)
notebooks/        exploration only, never the source of results
results/          metrics and figures produced from configs
tests/            pytest suite
```
