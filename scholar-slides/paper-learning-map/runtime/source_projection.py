from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _record_node(node_id: str, title: str, node_type: str, record: Mapping[str, Any], parent_id: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    refs = [str(ref) for ref in record.get("evidence_refs", []) if isinstance(ref, str)]
    availability = str(record.get("availability", "unverifiable"))
    return {
        "id": node_id,
        "parent_id": parent_id,
        "title": title,
        "node_type": node_type,
        "summary": str(record.get("content", record.get("summary", ""))),
        "claim_type": str(record.get("claim_type", "analysis")),
        "availability": availability,
        "paper_fact": {"statement": str(record.get("content", ""))} if record.get("claim_type") == "paper_fact" else None,
        "evidence_refs": refs,
        "source_trace": [{"kind": "reference", "value": ref, "verification": "inherited_from_validated_reading_view"} for ref in refs],
        "tags": tags or [],
    }


def build_paper_map(view: Mapping[str, Any], project_name: str, verification_level: str = "scholar_slides_validated") -> dict[str, Any]:
    identity = view["paper_identity"]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    root_id = "paper"
    nodes.append({"id": root_id, "parent_id": None, "title": identity["title"], "node_type": "paper", "summary": identity["title"], "claim_type": "paper_fact", "availability": "supported", "paper_fact": {"statement": identity["title"]}, "evidence_refs": [], "source_trace": [], "tags": [str(view.get("paper_type", {}).get("kind", "paper"))]})
    overview = view.get("overview", {})
    labels = {"problem": "Problem", "gap": "Gap", "approach": "Approach", "insight": "Insight", "findings": "Findings", "boundary": "Boundary"}
    for key, title in labels.items():
        record = overview.get(key)
        if isinstance(record, Mapping):
            node_id = f"overview.{key}"
            nodes.append(_record_node(node_id, title, "overview", record, root_id, [key]))
            edges.append({"source": root_id, "target": node_id, "relation": "parent_of"})
    method_root = "method"
    nodes.append({"id": method_root, "parent_id": root_id, "title": "Method", "node_type": "method", "summary": "Mechanism steps from the validated reading view.", "claim_type": "explanation", "availability": "supported", "paper_fact": None, "evidence_refs": [], "source_trace": [], "tags": []})
    edges.append({"source": root_id, "target": method_root, "relation": "parent_of"})
    for index, step in enumerate(view.get("mechanism_steps", []), 1):
        if not isinstance(step, Mapping):
            continue
        node_id = f"method.step_{index}"
        record = dict(step)
        record["content"] = f"{step.get('purpose', '')} Input: {step.get('input', '')}. Output: {step.get('output', '')}."
        nodes.append(_record_node(node_id, str(step.get("title", f"Step {index}")), "mechanism", record, method_root, ["mechanism"]))
        edges.append({"source": method_root, "target": node_id, "relation": "parent_of"})
        if index > 1:
            edges.append({"source": f"method.step_{index - 1}", "target": node_id, "relation": "implements"})
    evidence_root = "evidence"
    nodes.append({"id": evidence_root, "parent_id": root_id, "title": "Evidence", "node_type": "evidence", "summary": "Decisive evidence blocks.", "claim_type": "explanation", "availability": "supported", "paper_fact": None, "evidence_refs": [], "source_trace": [], "tags": []})
    edges.append({"source": root_id, "target": evidence_root, "relation": "parent_of"})
    for index, item in enumerate(view.get("decisive_evidence", []), 1):
        if not isinstance(item, Mapping):
            continue
        node_id = f"evidence.block_{index}"
        record = dict(item); record["content"] = str(item.get("result", ""))
        nodes.append(_record_node(node_id, str(item.get("question", f"Evidence {index}")), "experiment", record, evidence_root, ["evidence"]))
        edges.append({"source": evidence_root, "target": node_id, "relation": "parent_of"})
        if nodes:
            edges.append({"source": node_id, "target": "overview.findings", "relation": "supports"})
    terms_root = "terms"
    nodes.append({"id": terms_root, "parent_id": root_id, "title": "Key Terms", "node_type": "terms", "summary": "Terms required to understand the paper.", "claim_type": "explanation", "availability": "supported", "paper_fact": None, "evidence_refs": [], "source_trace": [], "tags": []})
    edges.append({"source": root_id, "target": terms_root, "relation": "parent_of"})
    for index, term in enumerate(view.get("terms", []), 1):
        if not isinstance(term, Mapping):
            continue
        node_id = f"term.{index}"
        record = dict(term); record["content"] = str(term.get("plain", ""))
        nodes.append(_record_node(node_id, str(term.get("term", f"Term {index}")), "term", record, terms_root, ["term"]))
        edges.append({"source": terms_root, "target": node_id, "relation": "parent_of"})
    take_root = "takeaways"
    nodes.append({"id": take_root, "parent_id": root_id, "title": "Takeaways", "node_type": "takeaway", "summary": "Contributions, boundaries, and research questions.", "claim_type": "explanation", "availability": "supported", "paper_fact": None, "evidence_refs": [], "source_trace": [], "tags": []})
    edges.append({"source": root_id, "target": take_root, "relation": "parent_of"})
    for index, item in enumerate(view.get("takeaways", []), 1):
        if not isinstance(item, Mapping):
            continue
        node_id = f"takeaway.{index}"
        nodes.append(_record_node(node_id, str(item.get("kind", "Takeaway")), "takeaway", item, take_root, [str(item.get("kind", "takeaway"))]))
        edges.append({"source": take_root, "target": node_id, "relation": "parent_of"})
    if verification_level not in {"scholar_slides_validated", "tutor_only"}:
        raise ValueError(f"unsupported verification level: {verification_level}")
    return {"schema_version": "1.0", "paper_identity": {"title": identity["title"], "source_pdf_sha256": identity["source_pdf_sha256"]}, "source": {"reading_view": "reading-view.json", "digest": "digest.json", "mode": "integrated", "verification_level": verification_level}, "paper_type": str(view.get("paper_type", {}).get("kind", "mixed")), "language": view.get("language", "zh-CN"), "nodes": nodes, "edges": edges, "meta": {"generated_at": datetime.now(timezone.utc).isoformat(), "generator_version": "paper-learning-map-0.1.0", "project": project_name}}
