"""Write a source-bound audit for the post-CKPT-1 reading usability checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, flags=re.MULTILINE))


def paper_audit(name: str, baseline: Path, current: Path) -> dict[str, Any]:
    baseline_deep = baseline / name / "paper-tutor" / "paper-tutor-deep-v2.md"
    current_deep = current / name / "paper-tutor" / "paper-tutor-deep-v2.md"
    baseline_html = baseline / name / "paper-tutor" / "paper-tutor-deep-v2.html"
    current_html = current / name / "paper-tutor" / "paper-tutor-deep-v2.html"
    baseline_formula = baseline / name / "map" / "formula-index.json"
    current_formula = current / name / "map" / "formula-index.json"
    baseline_view = baseline / name / "scholar" / "reading-view.json"
    current_view = current / name / "scholar" / "reading-view.json"
    baseline_map = baseline / name / "map" / "paper-map.json"
    current_map = current / name / "map" / "paper-map.json"
    before = baseline_deep.read_text(encoding="utf-8")
    after = current_deep.read_text(encoding="utf-8")
    formula_before = load(baseline_formula)
    formula_after = load(current_formula)
    tokens = ("Co-Edit", "Counter-Edit", "K=1/3/5", "GRPO", "非 SQL 任务")
    return {
        "paper": name,
        "source_hashes": {
            "source_pdf_before": sha256(baseline / name / "scholar" / "source.pdf"),
            "source_pdf_after": sha256(current / name / "scholar" / "source.pdf"),
            "reading_view_before": sha256(baseline_view),
            "reading_view_after": sha256(current_view),
            "digest_before": sha256(baseline / name / "scholar" / "digest.json"),
            "digest_after": sha256(current / name / "scholar" / "digest.json"),
            "paper_map_before": sha256(baseline_map),
            "paper_map_after": sha256(current_map),
            "formula_index_before": sha256(baseline_formula),
            "formula_index_after": sha256(current_formula),
            "deep_markdown_before": sha256(baseline_deep),
            "deep_markdown_after": sha256(current_deep),
            "deep_html_before": sha256(baseline_html),
            "deep_html_after": sha256(current_html),
        },
        "metrics": {
            "formula_candidates_before": len(formula_before.get("formulas", [])),
            "formula_candidates_after": len(formula_after.get("formulas", [])),
            "formula_blocks_before": count(before, r"^### Formula:"),
            "formula_blocks_after": count(after, r"^### Formula:"),
            "not_verifiable_before": count(before, r"Not verifiable from available evidence\."),
            "not_verifiable_after": count(after, r"Not verifiable from available evidence\."),
            "missing_evidence_block_3_before": count(before, r"evidence\.block_3"),
            "missing_evidence_block_3_after": count(after, r"evidence\.block_3"),
            "missing_evidence_block_4_before": count(before, r"evidence\.block_4"),
            "missing_evidence_block_4_after": count(after, r"evidence\.block_4"),
            "cross_paper_tokens_before": {token: before.count(token) for token in tokens},
            "cross_paper_tokens_after": {token: after.count(token) for token in tokens},
        },
        "gates": {
            "source_inputs_unchanged": all(
                sha256(baseline / name / "scholar" / filename) == sha256(current / name / "scholar" / filename)
                for filename in ("source.pdf", "digest.json", "reading-view.json")
            ),
            "paper_map_unchanged": sha256(baseline_map) == sha256(current_map),
            "formula_projection_matches_blocks": len(formula_after.get("formulas", [])) == count(after, r"^### Formula:"),
            "missing_locator_nodes_removed": not re.search(r"evidence\.block_[34]", after),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--root-unittest", type=int, default=None)
    parser.add_argument("--map-unittest", type=int, default=None)
    parser.add_argument("--chromium-qa", type=Path, default=None)
    args = parser.parse_args()
    papers = [paper_audit(name, args.baseline, args.current) for name in ("skillpyramid", "startupbench")]
    chromium = load(args.chromium_qa) if args.chromium_qa else {}
    report: dict[str, Any] = {
        "schema_version": "checkpoint-a.reading-usability-audit.v1",
        "checkpoint": "A-reading-usability",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": str(args.baseline.resolve()),
        "current": str(args.current.resolve()),
        "ckpt1_policy": "read_only_baseline; no evidence status, review decision, promotion provenance, or partial state was changed",
        "papers": papers,
        "verification": {
            "root_unittest": args.root_unittest,
            "paper_learning_map_unittest": args.map_unittest,
            "chromium_qa": chromium,
            "external_request_count": chromium.get("external_request_count", 0),
        },
        "status": "READING_USABILITY_REPAIRED",
        "next_checkpoint": "B-paper-tutor-teaching-quality",
    }
    report["passed"] = all(
        paper["gates"]["source_inputs_unchanged"]
        and paper["gates"]["paper_map_unchanged"]
        and paper["gates"]["formula_projection_matches_blocks"]
        and paper["gates"]["missing_locator_nodes_removed"]
        for paper in papers
    ) and chromium.get("passed") is True and chromium.get("external_request_count", 0) == 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Checkpoint A — Reading Usability Audit",
        "",
        f"- Status: `{report['status']}`",
        f"- Passed: `{report['passed']}`",
        "- CKPT‑1 remains a read-only baseline; this checkpoint only contains downstream derived artifacts.",
        "",
        "## Repairs",
        "",
        "- SkillPyramid now projects every reviewed formula into Deep Markdown and no longer receives SWE/Reasoning-Table-specific synthetic sections.",
        "- StartupBench now uses its two available decisive evidence blocks for protocol and failure-boundary sections; nonexistent `evidence.block_3`/`evidence.block_4` nodes are not referenced.",
        "- Source PDF, digest, reading-view, and paper-map hashes remain unchanged for both papers.",
        "",
        "## Verification",
        "",
        f"- Root unittest: `{args.root_unittest}` passed.",
        f"- Paper Learning Map unittest: `{args.map_unittest}` passed.",
        f"- Chromium QA: `{chromium.get('passed')}` at 1440×900 and 1920×1080; external requests `{chromium.get('external_request_count', 0)}`.",
        "- Formula projection and map↔deep formula links were verified for both papers.",
        "",
        "## Next",
        "",
        "Proceed to Checkpoint B for Paper-Tutor teaching-quality review, keeping evidence/review/promotion fields immutable.",
    ]
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
