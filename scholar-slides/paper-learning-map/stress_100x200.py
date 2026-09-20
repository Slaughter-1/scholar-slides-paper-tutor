"""Generate a deterministic Paper Learning Map stress project.

The project contains exactly 100 source-grounded factual nodes and two Tutor
items per node.  It is intentionally synthetic and is used only to exercise
the standalone renderer at a larger scale.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ITEM_KINDS = (
    "tutor_explanation",
    "intuition",
    "necessity",
    "example",
    "reader_analysis",
    "comprehension_check",
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_project(out: Path) -> dict[str, int | str]:
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    identity = hashlib.sha256(b"paper-learning-map-stress-100x200-v1").hexdigest()

    nodes: list[dict[str, object]] = []
    # One root, nine section nodes, and ninety leaves gives the renderer a
    # realistic hierarchy while keeping the factual count exactly 100.
    nodes.append(
        {
            "id": "paper",
            "parent_id": None,
            "title": "Stress Paper 100",
            "node_type": "paper",
            "summary": "Synthetic source-grounded paper used for renderer stress testing.",
            "claim_type": "paper_fact",
            "availability": "supported",
            "paper_fact": {"statement": "Synthetic stress paper with 100 factual nodes."},
            "evidence_refs": ["p. 1"],
            "source_trace": [{"kind": "reference", "value": "p. 1", "verification": "stress_fixture"}],
            "tags": ["stress", "paper"],
        }
    )
    for section_index in range(9):
        section_id = f"section.{section_index + 1:02d}"
        nodes.append(
            {
                "id": section_id,
                "parent_id": "paper",
                "title": f"Section {section_index + 1:02d}",
                "node_type": "overview" if section_index < 3 else "mechanism",
                "summary": f"Factual section {section_index + 1:02d} of the synthetic paper.",
                "claim_type": "paper_fact",
                "availability": "supported",
                "paper_fact": {"statement": f"Section {section_index + 1:02d} is reported in the source."},
                "evidence_refs": [f"p. {section_index + 2}"],
                "source_trace": [{"kind": "reference", "value": f"p. {section_index + 2}", "verification": "stress_fixture"}],
                "tags": ["stress", "section", f"section-{section_index + 1:02d}"],
            }
        )
    for leaf_index in range(90):
        section_index = leaf_index // 10
        node_id = f"fact.{leaf_index + 1:03d}"
        page = (leaf_index % 9) + 2
        nodes.append(
            {
                "id": node_id,
                "parent_id": f"section.{section_index + 1:02d}",
                "title": f"Factual Node {leaf_index + 1:03d}",
                "node_type": "experiment" if leaf_index % 3 == 0 else "term",
                "summary": f"Source-grounded factual statement {leaf_index + 1:03d} for layout and interaction stress.",
                "claim_type": "paper_fact",
                "availability": "supported",
                "paper_fact": {"statement": f"The source reports factual observation {leaf_index + 1:03d}."},
                "evidence_refs": [f"p. {page}"],
                "source_trace": [{"kind": "reference", "value": f"p. {page}", "verification": "stress_fixture"}],
                "tags": ["stress", "fact", f"fact-{leaf_index + 1:03d}"],
            }
        )

    paper_map = {
        "schema_version": "1.0",
        "paper_identity": {"title": "Stress Paper 100", "source_pdf_sha256": identity},
        "source": {
            "reading_view": "stress-reading-view.json",
            "digest": "stress-digest.json",
            "mode": "integrated",
            "verification_level": "scholar_slides_validated",
        },
        "paper_type": "method",
        "language": "en-US",
        "nodes": nodes,
        "edges": [
            {"source": node["parent_id"], "target": node["id"], "relation": "parent_of"}
            for node in nodes
            if node["parent_id"] is not None
        ],
        "meta": {"generated_at": generated_at, "generator_version": "stress-100x200-v1"},
    }

    tutor_nodes: dict[str, dict[str, object]] = {}
    item_count = 0
    for node_index, node in enumerate(nodes):
        node_id = str(node["id"])
        items: list[dict[str, object]] = []
        for local_index in range(2):
            item_count += 1
            kind = ITEM_KINDS[(node_index + local_index) % len(ITEM_KINDS)]
            title = f"Tutor note {item_count:03d} for {node_id}"
            visible = local_index == 0
            item_id = f"stress.tutor.{item_count:03d}"
            items.append(
                {
                    "id": item_id,
                    "kind": kind,
                    "title": title,
                    "summary": f"Short Tutor summary for item {item_count:03d}.",
                    "body": (
                        f"Tutor {kind} for {node_id}. This explanatory layer is synthetic and "
                        "must remain separate from the factual layer."
                    ),
                    "map_visible": visible,
                    "importance": "high" if visible else "medium",
                    "source_layer": "tutor",
                    "created_at": generated_at,
                    "updated_at": generated_at,
                    "origin": "full_analysis",
                    "tags": ["stress", "synthetic"],
                }
            )
        tutor_nodes[node_id] = {"map_items": items, "updated_at": generated_at}

    tutor_state = {
        "schema_version": "1.1",
        "paper_identity": {"source_pdf_sha256": identity},
        "nodes": tutor_nodes,
        "unresolved_items": [],
    }
    study_state = {
        "schema_version": "1.0",
        "paper_identity": {"source_pdf_sha256": identity},
        "nodes": {
            str(node["id"]): {
                "status": "unseen",
                "mastery": 0,
                "important": False,
                "confusing": False,
                "last_reviewed_at": "",
            }
            for node in nodes
        },
    }
    _write(out / "paper-map.json", paper_map)
    _write(out / "tutor-state.json", tutor_state)
    _write(out / "study-state.json", study_state)
    _write(
        out / "stress-metadata.json",
        {
            "fixture": "stress-100x200",
            "source_layer": {"factual_nodes": len(nodes), "tutor_items": item_count},
            "generated_at": generated_at,
            "identity": identity,
        },
    )
    return {"factual_nodes": len(nodes), "tutor_items": item_count, "identity": identity, "output": str(out)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the 100 factual / 200 Tutor stress fixture")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build_project(args.out), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
