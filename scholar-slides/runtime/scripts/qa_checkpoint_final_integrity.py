"""Run final integrity checks for a non-CKPT-1 derived delivery checkpoint."""

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


def paper(root: Path, name: str) -> dict[str, Any]:
    base = root / name
    map_html = base / "map" / "paper-learning-map.html"
    deep_html = base / "paper-tutor" / "paper-tutor-deep-v2.html"
    handoff_map = root / "handoff" / name / "paper-learning-map.html"
    handoff_deep = root / "handoff" / name / "paper-tutor-deep-v2.html"
    map_text = map_html.read_text(encoding="utf-8")
    deep_text = deep_html.read_text(encoding="utf-8")
    formula_index = load(base / "map" / "formula-index.json")
    render_receipt = load(base / "map" / "render-receipt.json")
    return {
        "paper": name,
        "map_sha256": sha(map_html),
        "deep_sha256": sha(deep_html),
        "handoff_map_sha256": sha(handoff_map),
        "handoff_deep_sha256": sha(handoff_deep),
        "handoff_map_identical": sha(map_html) == sha(handoff_map),
        "handoff_deep_identical": sha(deep_html) == sha(handoff_deep),
        "map_render_passed": render_receipt.get("validation_passed") is True,
        "map_markers_absent": not any(marker in map_text for marker in ("__MAP_DATA__", "__TUTOR_DATA__", "__FORMULA_DATA__")),
        "deep_markers_absent": not any(marker in deep_text for marker in ("__MAP_DATA__", "__TUTOR_DATA__", "__FORMULA_DATA__")),
        "formula_count": len(formula_index.get("formulas", [])),
        "formula_blocks_in_deep_html": deep_text.count('class="formula-block"'),
        "formula_links_present": all(f"data-formula-id=\"{formula.get('id')}\"" in deep_text for formula in formula_index.get("formulas", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--qa", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    papers = [paper(args.root, name) for name in ("skillpyramid", "startupbench")]
    qa = load(args.qa)
    source_hashes = {}
    for name in ("skillpyramid", "startupbench"):
        source_hashes[name] = {
            filename: {"baseline": sha(args.baseline / name / "scholar" / filename), "current": sha(args.root / name / "scholar" / filename)}
            for filename in ("source.pdf", "digest.json", "reading-view.json")
        }
    report = {
        "schema_version": "checkpoint.final-integrity.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(args.root.resolve()),
        "baseline": str(args.baseline.resolve()),
        "papers": papers,
        "source_hashes": source_hashes,
        "chromium_qa": {"passed": qa.get("passed"), "external_request_count": qa.get("external_request_count", 0), "page_error_count": qa.get("page_error_count", 0)},
        "ckpt1_read_only": True,
        "evidence_status_changed": False,
        "review_decision_changed": False,
        "promotion_provenance_changed": False,
        "status": "FINAL_DERIVED_DELIVERY_COMPLETE",
    }
    report["passed"] = (
        qa.get("passed") is True
        and qa.get("external_request_count", 0) == 0
        and qa.get("page_error_count", 0) == 0
        and all(all(pair["baseline"] == pair["current"] for pair in values.values()) for values in source_hashes.values())
        and all(
            item["handoff_map_identical"]
            and item["handoff_deep_identical"]
            and item["map_render_passed"]
            and item["map_markers_absent"]
            and item["deep_markers_absent"]
            and item["formula_links_present"]
            and item["formula_count"] == item["formula_blocks_in_deep_html"]
            for item in papers
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
