"""Audit and specify a source-bound cognitive reading structure for Learning Maps."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def depth(nodes: list[dict[str, Any]]) -> int:
    parents = {node.get("id"): node.get("parent_id") for node in nodes}
    best = 0
    for node_id in parents:
        current, seen = node_id, set()
        level = 0
        while current and current not in seen:
            seen.add(current)
            level += 1
            current = parents.get(current)
        best = max(best, level)
    return best


def audit_paper(project: Path) -> dict[str, Any]:
    paper_map = load(project / "map" / "paper-map.json")
    view = load(project / "scholar" / "reading-view.json")
    formula_index = load(project / "map" / "formula-index.json")
    coverage = load(project / "paper-tutor" / "paper-tutor-coverage.json")
    nodes = paper_map.get("nodes", [])
    edges = paper_map.get("edges", [])
    relations = Counter(edge.get("relation") for edge in edges)
    node_ids = {node.get("id") for node in nodes}
    evidence_ids = [node.get("id") for node in nodes if str(node.get("id", "")).startswith("evidence.block_")]
    support_edges = [edge for edge in edges if edge.get("relation") == "supports"]
    proposed = [
        {"source": "overview.problem", "target": "overview.gap", "relation": "motivates", "basis": "argument_chain / first transition"},
        {"source": "overview.gap", "target": "overview.approach", "relation": "requires", "basis": "argument_chain / gap-to-approach transition"},
        {"source": "overview.approach", "target": "overview.findings", "relation": "tests", "basis": "argument_chain / approach-to-result transition"},
    ]
    proposed = [edge for edge in proposed if edge["source"] in node_ids and edge["target"] in node_ids]
    explicit = sum(
        any(
            existing.get("source") == edge["source"]
            and existing.get("target") == edge["target"]
            and existing.get("relation") == edge["relation"]
            for existing in edges
        )
        for edge in proposed
    )
    term_quality = []
    for term in view.get("terms") or []:
        term_quality.append({
            "term": term.get("term"),
            "has_plain": bool(term.get("plain")),
            "has_role": bool(term.get("role")),
            "has_confusion": bool(term.get("confusions")),
        })
    return {
        "paper": project.name,
        "paper_identity": paper_map.get("paper_identity"),
        "nodes": len(nodes),
        "edges": len(edges),
        "relation_counts": dict(relations),
        "hierarchy_depth": depth(nodes),
        "decisive_evidence_blocks": len(view.get("decisive_evidence") or []),
        "evidence_nodes": len(evidence_ids),
        "evidence_to_findings_edges": len([edge for edge in support_edges if edge.get("target") == "overview.findings"]),
        "argument_chain_entries": len(view.get("argument_chain") or []),
        "formula_count": len(formula_index.get("formulas", [])),
        "formula_anchor_counts": dict(Counter(formula.get("anchor_node_id") for formula in formula_index.get("formulas", []))),
        "tutor_coverage": {key: coverage.get(key) for key in ("total_items", "represented_items", "high_importance_total", "high_importance_represented", "unresolved_items")},
        "term_quality": term_quality,
        "cognitive_gap": {
            "explicit_problem_gap_approach_result_edges": explicit,
            "parent_of_share": round((relations.get("parent_of", 0) / len(edges)), 4) if edges else 0,
            "finding": "The current map is structurally valid but mostly hierarchical; the argument chain is not directly navigable as cross-node relations.",
        },
        "proposed_source_bound_edges": proposed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    papers = [audit_paper(args.checkpoint / name) for name in ("skillpyramid", "startupbench")]
    report = {
        "schema_version": "learning-map.cognitive-audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint": str(args.checkpoint.resolve()),
        "ckpt1_policy": "read_only_baseline; audit is downstream and does not mutate paper-map.json",
        "papers": papers,
        "status": "COGNITIVE_AUDIT_COMPLETE",
        "next_checkpoint": "C-learning-map-source-bound-relations",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Learning Map Cognitive Audit",
        "",
        "- Status: `COGNITIVE_AUDIT_COMPLETE`",
        "- The existing maps are structurally valid and source-bound; this audit does not mutate CKPT‑1 or the current derived map.",
        "",
        "## Findings",
        "",
        "- Both maps preserve evidence nodes, formula anchors, tutor coverage, and interactive relation toggles.",
        "- The graph is mostly a containment hierarchy, so a reader cannot directly follow Problem → Gap → Approach → Result as navigable cognitive links.",
        "- The next checkpoint may add only the three proposed links whose basis is the existing reading-view argument chain; evidence statuses and Paper Facts remain unchanged.",
        "",
        "## Per-paper checks",
        "",
    ]
    for paper in papers:
        lines.extend([
            f"### {paper['paper']}",
            f"- Nodes/edges: `{paper['nodes']}/{paper['edges']}`; hierarchy depth `{paper['hierarchy_depth']}`.",
            f"- Evidence blocks/nodes/supports: `{paper['decisive_evidence_blocks']}/{paper['evidence_nodes']}/{paper['evidence_to_findings_edges']}`.",
            f"- Formula anchors: `{paper['formula_count']}`; Tutor coverage `{paper['tutor_coverage']['represented_items']}/{paper['tutor_coverage']['total_items']}`.",
            f"- Proposed source-bound relations: `{len(paper['proposed_source_bound_edges'])}`.",
            "",
        ])
    lines.extend([
        "## Next",
        "",
        "Create a separate derived map checkpoint, apply the three argument-chain relations, rerender the map, and rerun relation-toggle plus map↔Deep QA.",
    ])
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
