# Behavioural Anomaly Detection in Agentic Tool-Use Sequences

MSc thesis project, ELTE Faculty of Informatics (Data Science). Author: Laguna Rosa.

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
| Attack-family grouping and held-out choice | **open** (see `docs/decisions.md`) |
| Normal / attack data selection and labels | open |
| Features (tool categories, n-grams, intent mismatch, provenance, novelty) | not started |
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
docs/             decisions.md (decision log), agentdojo-notes.md
notebooks/        exploration only, never the source of results
results/          metrics and figures produced from configs
tests/            pytest suite
```
