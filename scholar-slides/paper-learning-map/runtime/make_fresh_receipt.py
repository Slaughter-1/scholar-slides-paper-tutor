"""Materialize one auditable Fresh E2E receipt from verified run artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scholar-project", required=True)
    parser.add_argument("--map-project", required=True)
    parser.add_argument("--receipt-dir", required=True)
    parser.add_argument("--stress-report", required=True)
    args = parser.parse_args()
    scholar = Path(args.scholar_project).resolve()
    project = Path(args.map_project).resolve()
    receipt_dir = Path(args.receipt_dir).resolve()
    receipt_dir.mkdir(parents=True, exist_ok=True)
    browser_path = project / "fresh-verified-chromium-qa.json"
    qa_path = receipt_dir / "qa-report.json"
    integrity_path = receipt_dir / "factual-integrity-after.json"
    browser = load(browser_path)
    qa = load(qa_path)
    integrity = load(integrity_path)
    stress_path = Path(args.stress_report).resolve()
    stress = load(stress_path)
    screenshot_paths = [project / "screenshots" / name for name in browser.get("screenshots", [])]
    result = {
        "receipt_version": "1.0",
        "kind": "verified_fresh_e2e",
        "paper": "SWE-Touch: Benchmarking Coding Agents When Users Touch the Code",
        "source": {
            "pdf_sha256": sha256(scholar / "source.pdf"),
            "digest_sha256": sha256(scholar / "digest.json"),
            "reading_view_sha256": sha256(scholar / "reading-view.json"),
            "paper_map_sha256": sha256(project / "paper-map.json"),
            "paper_map_source": load(project / "paper-map.json").get("source"),
        },
        "tutor": {
            "qa_report": str(qa_path),
            "qa_report_sha256": sha256(qa_path),
            "observability_report": str(receipt_dir / "observability-report.json"),
            "tutor_state_sha256": sha256(project / "tutor-state.json"),
            "study_state_sha256": sha256(project / "study-state.json"),
            "no_records_json": not (project / "records.json").exists(),
        },
        "browser_qa": {
            "report": str(browser_path),
            "report_sha256": sha256(browser_path),
            "viewports": browser.get("results", []),
            "screenshots": [{"path": str(path), "sha256": sha256(path)} for path in screenshot_paths],
        },
        "stress": {
            "report": str(stress_path),
            "report_sha256": sha256(stress_path),
            "viewports": stress.get("viewports", []),
        },
        "integrity": integrity,
    }
    target = receipt_dir / "fresh-verified-e2e-receipt.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
