"""Paper-Tutor installation-side bridge to the shared Learning Map writer.

The bridge intentionally owns no state-writing logic.  It resolves an
explicit/configured Paper Learning Map runtime and forwards the in-memory JSON
payload to ``update_tutor_state.py sync --stdin``.  This keeps Full Analysis
and Incremental Q&A on the single ``TutorStateStore`` implementation.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def resolve_map_root(explicit: str | None) -> Path:
    values = [explicit, os.environ.get("PAPER_LEARNING_MAP_ROOT")]
    for value in values:
        if not value:
            continue
        root = Path(value).expanduser().resolve()
        writer = root / "runtime" / "update_tutor_state.py"
        schemas = root / "schemas"
        if writer.is_file() and schemas.is_dir():
            return root
    raise SystemExit(
        "Paper Learning Map runtime was not found. Pass --map-root or set "
        "PAPER_LEARNING_MAP_ROOT to a directory containing runtime/ and schemas/."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream Paper-Tutor Full Analysis records to TutorStateStore")
    parser.add_argument("--project", required=True, help="Map project containing paper-map.json and tutor-state.json")
    parser.add_argument("--map-root", help="Paper Learning Map root; otherwise PAPER_LEARNING_MAP_ROOT is used")
    parser.add_argument("--origin", choices=("full_analysis", "incremental_qa"), default="full_analysis")
    args = parser.parse_args()

    project = Path(args.project).expanduser().resolve()
    # The shared writer owns the no-map and failed-sync receipts.  Do not fail
    # here before it can record ``sync_skipped`` or ``sync_failed``.
    map_root = resolve_map_root(args.map_root)
    writer = map_root / "runtime" / "update_tutor_state.py"
    payload = sys.stdin.buffer.read()
    if not payload.strip():
        raise SystemExit("Structured Tutor payload is empty; no state was written.")
    completed = subprocess.run(
        [
            sys.executable,
            str(writer),
            "--project",
            str(project),
            "sync",
            "--stdin",
            "--origin",
            args.origin,
        ],
        input=payload,
        check=False,
        capture_output=True,
    )
    if completed.stdout:
        sys.stdout.buffer.write(completed.stdout)
    if completed.stderr:
        sys.stderr.buffer.write(completed.stderr)
    if completed.returncode:
        print(
            "Paper-Tutor Learning Map sync warning: structured synchronization failed; "
            "see the append-only receipt for the short error.",
            file=sys.stderr,
        )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
