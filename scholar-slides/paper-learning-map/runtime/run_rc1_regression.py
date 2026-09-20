"""Run the RC1 regression commands and save a machine-readable receipt."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--scholar-tests", required=True)
    parser.add_argument("--map-tests", required=True)
    parser.add_argument("--fresh-project", required=True)
    parser.add_argument("--receipt-dir", required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    receipt_dir = Path(args.receipt_dir).resolve()
    receipt_dir.mkdir(parents=True, exist_ok=True)
    commands = [
        ("scholar_regression", [args.scholar_tests, "-m", "unittest", "discover", "-s", str(workspace / "tests"), "-q"], {}),
        ("paper_learning_map_regression", [args.map_tests, "-m", "unittest", "discover", "-s", str(workspace / "paper-learning-map" / "tests"), "-q"], {}),
        ("renderer_qa", ["node", str(workspace / "paper-learning-map" / "qa_renderer_v2.mjs")], {}),
        ("tutor_overlay_qa", ["node", str(workspace / "paper-learning-map" / "qa_tutor_overlay.mjs")], {}),
        ("stress_qa", ["node", str(workspace / "paper-learning-map" / "qa_stress_100x200.mjs")], {}),
        ("fresh_chromium_qa", ["node", str(workspace / "paper-learning-map" / "qa_verified_fresh.mjs")], {"PAPER_MAP_QA_PROJECT": str(Path(args.fresh_project).resolve())}),
    ]
    results = []
    for name, command, extra_env in commands:
        env = dict(os.environ)
        env.update(extra_env)
        started = time.perf_counter()
        completed = subprocess.run(command, cwd=workspace, capture_output=True, env=env, check=False)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        results.append({
            "name": name,
            "command": " ".join(command),
            "returncode": completed.returncode,
            "passed": completed.returncode == 0,
            "elapsed_ms": elapsed,
            "stdout_tail": stdout[-1200:],
            "stderr_tail": stderr[-1200:],
        })
    report = {"results": results, "all_passed": all(item["passed"] for item in results)}
    target = receipt_dir / "regression-results.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
