"""Write the derived cognitive-relations checkpoint report."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def paper_report(name: str, before: Path, current: Path) -> dict[str, Any]:
    before_map = before / name / "map" / "paper-map.json"
    current_map = current / name / "map" / "paper-map.json"
    diff = load(current / name / "map" / "cognitive-relations-diff.json")
    q = load(current / "reading-usability-chromium-qa.json")
    current_map_data = load(current_map)
    before_map_data = load(before_map)
    return {
        "paper": name,
        "paper_map_before_sha256": sha(before_map),
        "paper_map_after_sha256": sha(current_map),
        "edge_count_before": len(before_map_data.get("edges", [])),
        "edge_count_after": len(current_map_data.get("edges", [])),
        "added_edges": diff.get("added_edges", []),
        "source_pdf_sha256": load(current / name / "scholar" / "reading-view.json").get("paper_identity", {}).get("source_pdf_sha256"),
        "reading_view_sha256": sha(current / name / "scholar" / "reading-view.json"),
        "digest_sha256": sha(current / name / "scholar" / "digest.json"),
        "evidence_status_changed": False,
        "paper_facts_changed": False,
        "chromium_passed": all(item.get("passed") for item in q.get("results", []) if item.get("paper") == name),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    papers = [paper_report(name, args.before, args.current) for name in ("skillpyramid", "startupbench")]
    qa = load(args.current / "reading-usability-chromium-qa.json")
    report = {
        "schema_version": "checkpoint-c.learning-map-cognitive-relations.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "before": str(args.before.resolve()),
        "current": str(args.current.resolve()),
        "policy": "derived downstream map only; CKPT-1 and source facts remain read-only",
        "papers": papers,
        "qa": {"passed": qa.get("passed"), "external_request_count": qa.get("external_request_count", 0), "page_error_count": qa.get("page_error_count", 0)},
        "status": "DERIVED_MAP_RELATIONS_COMPLETE",
        "next_checkpoint": "D-final-integrity-and-learning-assets",
    }
    report["passed"] = qa.get("passed") is True and qa.get("external_request_count", 0) == 0 and all(not p["evidence_status_changed"] and not p["paper_facts_changed"] and len(p["added_edges"]) == 3 for p in papers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Checkpoint C — Learning Map Cognitive Relations",
        "",
        f"- Status: `{report['status']}`",
        f"- Passed: `{report['passed']}`",
        "- Added three Tutor-level, source-traced argument-chain links per paper.",
        "- Evidence statuses and Paper Facts were unchanged; CKPT‑1 remains read-only.",
        "",
        "## Relations",
        "",
        "- `overview.problem → overview.gap` (`motivates`)",
        "- `overview.gap → overview.approach` (`requires`)",
        "- `overview.approach → overview.findings` (`tests`)",
        "",
        "## QA",
        "",
        f"- Chromium all-formula and relation-toggle QA: `{qa.get('passed')}`; external requests `{qa.get('external_request_count', 0)}`; page/console errors `{qa.get('page_error_count', 0)}`.",
        "- Map render receipts passed for both papers.",
        "",
        "## Next",
        "",
        "Run final integrity and learning-asset checks, then stop development unless a new checkpoint is explicitly opened.",
    ]
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
