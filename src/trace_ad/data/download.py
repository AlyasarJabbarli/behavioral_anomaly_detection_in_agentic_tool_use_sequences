"""Download the recorded AgentDojo runs at a pinned commit.

Only the ``runs/`` directory is checked out (git sparse checkout of a blobless
clone), so no AgentDojo source code ends up on disk here; task definitions come
from the pinned ``agentdojo`` package instead.

Usage:
    trace-ad-download --config configs/data.yaml
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from trace_ad.config import load_config, repo_path


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def download_agentdojo_runs(repo_url: str, commit: str, raw_dir: Path) -> Path:
    """Sparse-checkout ``runs/`` of ``repo_url`` at ``commit`` into ``raw_dir``.

    Idempotent: if ``raw_dir`` already holds a checkout of ``commit``, nothing is
    downloaded. Writes ``raw_dir/MANIFEST.json`` with provenance information.
    Returns the path to the ``runs/`` directory.
    """
    raw_dir.parent.mkdir(parents=True, exist_ok=True)
    if not (raw_dir / ".git").exists():
        _git("clone", "--filter=blob:none", "--no-checkout", "--sparse", repo_url, str(raw_dir))
    _git("sparse-checkout", "set", "--no-cone", "/runs/", cwd=raw_dir)
    head = _git("rev-parse", "HEAD", cwd=raw_dir)
    if head != commit or not (raw_dir / "runs").exists():
        _git("fetch", "--filter=blob:none", "origin", commit, cwd=raw_dir)
        _git("checkout", "--detach", commit, cwd=raw_dir)

    runs_dir = raw_dir / "runs"
    n_files = sum(1 for _ in runs_dir.rglob("*.json"))
    manifest = {
        "repo_url": repo_url,
        "commit": _git("rev-parse", "HEAD", cwd=raw_dir),
        "n_run_files": n_files,
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (raw_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return runs_dir


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="configs/data.yaml")
    args = parser.parse_args(argv)

    cfg = load_config(repo_path(args.config))["agentdojo_runs"]
    runs_dir = download_agentdojo_runs(cfg["repo_url"], cfg["commit"], repo_path(cfg["raw_dir"]))
    manifest = json.loads((runs_dir.parent / "MANIFEST.json").read_text())
    print(f"{manifest['n_run_files']} run files at {runs_dir} (commit {manifest['commit'][:10]})")


if __name__ == "__main__":
    main()
