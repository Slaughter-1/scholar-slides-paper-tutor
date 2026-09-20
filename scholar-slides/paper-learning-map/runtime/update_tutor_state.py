from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path

from sync_receipt import (
    append_receipt,
    build_receipt,
    diff_counts,
    load_state,
    short_error,
    state_hash,
    study_transition,
)
from tutor_state import TutorStateStore, _question_duplicate, sync_records


def _load_records(path: Path | str) -> list[dict]:
    if str(path) == "-":
        # Windows PowerShell may expose a UTF-8 pipe as the active GBK code
        # page.  Reconfigure the text wrapper before reading so Chinese Tutor
        # titles do not become replacement characters/surrogate fragments.
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="strict")
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    value = json.loads(raw)
    if isinstance(value, dict):
        value = value.get("records", [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("records file must contain a JSON array or {\"records\": [...]}")
    return value


def records_from_paper_map(project: Path) -> list[dict]:
    """Create a conservative Tutor logical model from validated map semantics.

    This is the integrated Full Analysis hook: it reads facts as navigation input,
    writes only Tutor explanations, and never parses paper-tutor.md.
    """
    paper_map = json.loads((project / "paper-map.json").read_text(encoding="utf-8"))
    records = []
    for node in paper_map.get("nodes", []):
        node_id, title, summary = node["id"], node["title"], node.get("summary", "")
        node_type = node.get("node_type")
        if node_id == "paper" or not summary or node_type in {"group", "method", "evidence", "terms", "takeaway"}:
            continue
        if node_type == "term":
            kind = "tutor_explanation"
            teaching = f"把“{title}”先当作阅读路标：它在当前论文语境中的摘要是“{summary}”。阅读时要区分术语定义、它在本文中的作用，以及 Tutor 为了帮助理解补充的直觉。"
        elif node_type == "mechanism":
            kind = "intuition"
            teaching = f"直觉上，步骤“{title}”把输入逐步转成下一阶段可检查的结果。论文节点摘要是“{summary}”；这里的直觉说明用于帮助串起步骤，不新增作者未报告的事实。"
        elif node_type == "experiment":
            kind = "reader_analysis"
            teaching = f"阅读证据节点“{title}”时，先问它支持什么、不能支持什么。节点摘要是“{summary}”。这段 Tutor Analysis 只提供读法，不把解释写成新的 Paper Fact。"
        else:
            kind = "tutor_explanation"
            teaching = f"先把“{title}”放回论文主线理解。节点摘要是“{summary}”。教学重点是理解它与相邻问题、方法或证据的关系；这段 Tutor Explanation 不会扩大事实边界。"
        records.append({"node_id": node_id, "kind": kind, "title": f"如何理解：{title}", "summary": teaching[:160], "body": teaching, "map_visible": node_type in {"overview", "mechanism", "experiment", "term"}, "importance": "high" if node_type in {"overview", "mechanism", "experiment"} else "medium", "tags": ["full-analysis-bridge", str(node_type)]})
    return records


def _paper_sha256(project: Path) -> str | None:
    try:
        value = json.loads((project / "paper-map.json").read_text(encoding="utf-8"))
        sha = value.get("paper_identity", {}).get("source_pdf_sha256")
        return sha if isinstance(sha, str) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return None


def _dedupe_count(before: Mapping | None, records: list[dict]) -> int:
    """Count records that matched an existing Tutor item before this turn."""

    if not isinstance(before, Mapping):
        return 0
    total = 0
    for record in records:
        kind = str(record.get("kind", ""))
        title = str(record.get("question", record.get("title", "")))
        node_id = record.get("node_id")
        if not node_id:
            continue
        state = (before.get("nodes") or {}).get(node_id) or {}
        items = state.get("map_items") or []
        for item in items:
            if item.get("kind") != kind:
                continue
            if str(item.get("title", "")).strip().casefold() == title.strip().casefold():
                total += 1
                break
            if kind == "user_question":
                variants = [item.get("title", ""), *(item.get("question_variants") or [])]
                if any(_question_duplicate(title, str(variant)) for variant in variants):
                    total += 1
                    break
    return total


def _write_receipt(project: Path, receipt: dict) -> Path | None:
    try:
        return append_receipt(project, receipt)
    except Exception as exc:  # pragma: no cover - defensive audit fallback
        print(f"Paper Learning Map receipt warning: {exc}", file=sys.stderr)
        return None


def _idempotency_key(records: list[dict], origin: str, paper_sha: str | None) -> str:
    payload = json.dumps({"origin": origin, "paper_sha256": paper_sha, "records": records}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sync-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _find_prior_receipt(project: Path, key: str) -> dict | None:
    directory = project / "sync-receipts"
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if value.get("idempotency_key") == key and value.get("status") == "success":
            return value
    return None


def _sync_with_receipt(project: Path, records: list[dict], origin: str) -> int:
    """Run one structured sync and always leave an observable receipt."""

    event = "incremental_qa_sync" if origin == "incremental_qa" else "full_analysis_sync"
    project = project.resolve()
    paper_sha = _paper_sha256(project)
    idempotency_key = _idempotency_key(records, origin, paper_sha)
    before_tutor = state_hash(project / "tutor-state.json")
    before_study = state_hash(project / "study-state.json")
    before_state = load_state(project, "tutor-state.json")
    before_study_state = load_state(project, "study-state.json")

    if not (project / "paper-map.json").is_file():
        receipt = build_receipt(
            event="sync_skipped",
            project=project,
            paper_sha256=paper_sha,
            status="skipped",
            records_received=len(records),
            before_tutor=before_tutor,
            after_tutor=before_tutor,
            before_study=before_study,
            after_study=before_study,
            reason="no_learning_map",
            idempotency_key=idempotency_key,
        )
        path = _write_receipt(project, receipt)
        print(json.dumps({"status": "skipped", "reason": "no_learning_map", "receipt": str(path) if path else None}, ensure_ascii=False))
        return 0

    try:
        prior = _find_prior_receipt(project, idempotency_key)
        if prior is not None:
            # Idempotent retry: do not touch Tutor/Study state or create a
            # duplicate item.  Append a fresh receipt so the retry itself is
            # visible to the user and remains auditable.
            receipt = build_receipt(
                event=event,
                project=project,
                paper_sha256=paper_sha,
                status="success",
                records_received=len(records),
                before_tutor=before_tutor,
                after_tutor=before_tutor,
                before_study=before_study,
                after_study=before_study,
                counts={"records_received": len(records), "items_deduped": len(records)},
                reason="idempotent_retry",
                idempotency_key=idempotency_key,
                retry_of=prior.get("timestamp"),
                dedupe_report=(before_state or {}).get("dedupe_report") if isinstance(before_state, Mapping) else None,
            )
            path = _write_receipt(project, receipt)
            print(json.dumps({"status": "success", "idempotent": True, "receipt": str(path) if path else None, "items_deduped": len(records)}, ensure_ascii=False))
            return 0
        sync_records(project, records, origin=origin)
        after_state = load_state(project, "tutor-state.json")
        after_study_state = load_state(project, "study-state.json")
        counts = diff_counts(before_state, after_state, len(records))
        counts["items_deduped"] = _dedupe_count(before_state, records)
        preferred = next((str(item.get("node_id")) for item in records if item.get("node_id")), None)
        transition = study_transition(before_study_state, after_study_state, preferred)
        receipt = build_receipt(
            event=event,
            project=project,
            paper_sha256=paper_sha,
            status="success",
            before_tutor=before_tutor,
            after_tutor=state_hash(project / "tutor-state.json"),
            before_study=before_study,
            after_study=state_hash(project / "study-state.json"),
            counts=counts,
            study=transition,
            idempotency_key=idempotency_key,
            dedupe_report=(after_state or {}).get("dedupe_report") if isinstance(after_state, Mapping) else None,
        )
        path = _write_receipt(project, receipt)
        print(json.dumps({"status": "success", "receipt": str(path) if path else None, **counts, "study_state": transition}, ensure_ascii=False))
        return 0
    except Exception as exc:
        receipt = build_receipt(
            event=event,
            project=project,
            paper_sha256=paper_sha,
            status="failed",
            records_received=len(records),
            before_tutor=before_tutor,
            after_tutor=state_hash(project / "tutor-state.json"),
            before_study=before_study,
            after_study=state_hash(project / "study-state.json"),
            error=short_error(exc),
            reason="sync_exception",
            idempotency_key=idempotency_key,
        )
        path = _write_receipt(project, receipt)
        print(json.dumps({"status": "failed", "error": short_error(exc), "receipt": str(path) if path else None}, ensure_ascii=False), file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Paper-Tutor state without modifying source-grounded map data")
    parser.add_argument("--project", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="sync a full analysis or a batch of incremental records")
    sync.add_argument("--records", type=Path, help="JSON array or {records: [...]} input; use '-' for stdin")
    sync.add_argument("--stdin", action="store_true", help="read the structured Tutor payload from stdin")
    sync.add_argument("--origin", choices=("full_analysis", "incremental_qa"), default="full_analysis")
    sync.add_argument("--from-paper-map", action="store_true", help="run integrated Full Analysis hook from paper-map semantics")
    sync.add_argument("--retry", action="store_true", help="retry the same structured payload idempotently")

    ask = sub.add_parser("ask", help="append one answered user question")
    ask.add_argument("--node-id")
    ask.add_argument("--title-anchor")
    ask.add_argument("--question", required=True)
    ask.add_argument("--answer", required=True)
    ask.add_argument("--important", choices=("true", "false"), default="true")

    item = sub.add_parser("item", help="append or update one structured tutor item")
    item.add_argument("--node-id")
    item.add_argument("--title-anchor")
    item.add_argument("--aliases", nargs="*", default=[])
    item.add_argument("--kind", required=True)
    item.add_argument("--title", required=True)
    item.add_argument("--summary", required=True)
    item.add_argument("--body", required=True)
    item.add_argument("--map-visible", choices=("true", "false"), default="false")
    item.add_argument("--importance", choices=("low", "medium", "high"), default="medium")
    item.add_argument("--origin", choices=("full_analysis", "incremental_qa"), default="full_analysis")

    args = parser.parse_args()
    project = Path(args.project).resolve()
    if args.command == "sync":
        selected = sum(bool(value) for value in (args.from_paper_map, args.records, args.stdin))
        if selected != 1:
            parser.error("sync requires exactly one of --records, --stdin, or --from-paper-map")
        try:
            records = records_from_paper_map(project) if args.from_paper_map else _load_records("-" if args.stdin else args.records)
        except Exception as exc:
            # Parsing failures are observable too.  There may be no map yet, so
            # use the same project-local append-only receipt directory.
            receipt = build_receipt(
                event="incremental_qa_sync" if args.origin == "incremental_qa" else "full_analysis_sync",
                project=project,
                paper_sha256=_paper_sha256(project),
                status="failed",
                error=short_error(exc),
                reason="payload_parse_failed",
            )
            path = _write_receipt(project, receipt)
            print(json.dumps({"status": "failed", "error": short_error(exc), "receipt": str(path) if path else None}, ensure_ascii=False), file=sys.stderr)
            return 1
        return _sync_with_receipt(project, records, args.origin)
    elif args.command == "ask":
        store = TutorStateStore(project)
        store.add_user_question(
            node_id=args.node_id,
            title_anchor=args.title_anchor,
            question=args.question,
            answer=args.answer,
            important=args.important == "true",
            study_path=project / "study-state.json",
        )
        store.save()
        state = store.state
    else:
        store = TutorStateStore(project)
        store.add_structured_item(
            node_id=args.node_id,
            title_anchor=args.title_anchor,
            aliases=args.aliases,
            kind=args.kind,
            title=args.title,
            summary=args.summary,
            body=args.body,
            map_visible=args.map_visible == "true",
            importance=args.importance,
            origin=args.origin,
        )
        store.save()
        state = store.state
    print(json.dumps({"schema_version": state["schema_version"], "nodes": len(state.get("nodes", {})), "unresolved_items": len(state.get("unresolved_items", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
