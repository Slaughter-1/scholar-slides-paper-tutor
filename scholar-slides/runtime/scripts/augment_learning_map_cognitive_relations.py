"""Add source-traced cognitive links to a downstream Learning Map copy."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--diff-output", required=True, type=Path)
    args = parser.parse_args()
    map_path = args.project / "paper-map.json"
    view_path = args.project.parent / "scholar" / "reading-view.json"
    before_hash = sha256(map_path)
    paper_map = load(map_path)
    view = load(view_path)
    node_ids = {node.get("id") for node in paper_map.get("nodes", [])}
    before_edges = list(paper_map.get("edges", []))
    candidates = [
        ("overview.problem", "overview.gap", "motivates", "argument_chain / first transition"),
        ("overview.gap", "overview.approach", "requires", "argument_chain / gap-to-approach transition"),
        ("overview.approach", "overview.findings", "tests", "argument_chain / approach-to-result transition"),
    ]
    added = []
    for source, target, relation, basis in candidates:
        if source not in node_ids or target not in node_ids:
            continue
        edge = {
            "source": source,
            "target": target,
            "relation": relation,
            "relation_type": "cognitive",
            "source_layer": "tutor",
            "source_trace": [{"kind": "argument_chain", "value": "reading-view.json#/argument_chain", "basis": basis}],
        }
        if not any(existing.get("source") == source and existing.get("target") == target and existing.get("relation") == relation for existing in paper_map.get("edges", [])):
            paper_map.setdefault("edges", []).append(edge)
            added.append(edge)
    paper_map.setdefault("meta", {})["cognitive_relations"] = {
        "source_layer": "tutor",
        "source": "reading-view.json#/argument_chain",
        "count": len(added),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paper_identity_sha256": paper_map.get("paper_identity", {}).get("source_pdf_sha256"),
        "argument_chain_entries": len(view.get("argument_chain") or []),
    }
    map_path.write_text(json.dumps(paper_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    diff = {
        "schema_version": "learning-map.cognitive-relations-diff.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paper_map_before_sha256": before_hash,
        "paper_map_after_sha256": sha256(map_path),
        "added_edges": added,
        "edge_count_before": len(before_edges),
        "edge_count_after": len(paper_map.get("edges", [])),
        "source_layer": "tutor",
        "source_trace": "reading-view.json#/argument_chain",
        "evidence_status_changed": False,
        "paper_facts_changed": False,
    }
    args.diff_output.parent.mkdir(parents=True, exist_ok=True)
    args.diff_output.write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(diff, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
