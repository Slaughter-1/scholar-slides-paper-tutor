"""Phase 7 state-layer QA: conservative dedupe, idempotent retry and receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sync_receipt import validate_receipt


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_sync(project: Path, payload: list[dict[str, object]], *, retry: bool = False) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(ROOT / "runtime" / "update_tutor_state.py"), "--project", str(project), "sync", "--stdin", "--origin", "incremental_qa"]
    if retry:
        command.append("--retry")
    return subprocess.run(command, input=json.dumps(payload, ensure_ascii=False), text=True, encoding="utf-8", capture_output=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(ROOT / "fixtures" / "Reasoning-Table"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="phase7-state-"))
    try:
        build = subprocess.run([sys.executable, str(ROOT / "runtime" / "build_paper_map.py"), "--project", str(Path(args.fixture).resolve()), "--out", str(temp)], capture_output=True, text=True, encoding="utf-8", check=False)
        if build.returncode:
            raise RuntimeError(build.stderr or build.stdout)
        map_before = sha256(temp / "paper-map.json")
        payload: list[dict[str, object]] = [
            {"node_id": "term.1", "kind": "user_question", "question": "Agent Harness 是什么？", "answer": "运行时编排层。", "important": True},
            {"node_id": "term.1", "kind": "user_question", "question": "Agent Harness 的作用是什么？", "answer": "连接模型与工具。", "important": True},
            {"node_id": "term.1", "kind": "user_question", "question": "为什么需要 Agent Harness？", "answer": "为了统一运行链路。", "important": True},
            # Same words on another node must never be merged across nodes.
            {"node_id": "term.3", "kind": "user_question", "question": "Agent Harness 是什么？", "answer": "该节点的局部解释。", "important": True},
            {"kind": "user_question", "question": "M 是什么意思？", "answer": "上下文不足，保留为 unresolved。", "important": False},
        ]
        first = run_sync(temp, payload)
        if first.returncode:
            raise RuntimeError(first.stderr or first.stdout)
        state_after_first = json.loads((temp / "tutor-state.json").read_text(encoding="utf-8"))
        study_after_first = json.loads((temp / "study-state.json").read_text(encoding="utf-8"))
        tutor_hash_after_first = sha256(temp / "tutor-state.json")
        study_hash_after_first = sha256(temp / "study-state.json")
        second = run_sync(temp, payload, retry=True)
        if second.returncode:
            raise RuntimeError(second.stderr or second.stdout)
        tutor_hash_after_retry = sha256(temp / "tutor-state.json")
        study_hash_after_retry = sha256(temp / "study-state.json")
        receipts = []
        for path in sorted((temp / "sync-receipts").glob("*.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            validate_receipt(value)
            receipts.append(value)
        questions_by_node = {
            node_id: [item for item in (node_state.get("map_items") or []) if item.get("kind") == "user_question"]
            for node_id, node_state in (state_after_first.get("nodes") or {}).items()
        }
        term1 = questions_by_node.get("term.1", [])
        term3 = questions_by_node.get("term.3", [])
        report = {
            "schema_version": "1.0",
            "fixture": "Reasoning-Table",
            "paper_map_sha256_before": map_before,
            "paper_map_sha256_after": sha256(temp / "paper-map.json"),
            "paper_map_unchanged": map_before == sha256(temp / "paper-map.json"),
            "first_sync": json.loads(first.stdout),
            "retry_sync": json.loads(second.stdout),
            "retry_is_idempotent": json.loads(second.stdout).get("idempotent") is True,
            "state_hashes": {
                "tutor_after_first": tutor_hash_after_first,
                "tutor_after_retry": tutor_hash_after_retry,
                "study_after_first": study_hash_after_first,
                "study_after_retry": study_hash_after_retry,
                "retry_state_unchanged": tutor_hash_after_first == tutor_hash_after_retry and study_hash_after_first == study_hash_after_retry,
            },
            "study_transition": study_after_first.get("nodes", {}).get("term.1", {}),
            "dedupe_report": state_after_first.get("dedupe_report", {}),
            "question_counts": {"term.1": len(term1), "term.3": len(term3)},
            "cross_node_isolation": len(term1) >= 1 and len(term3) >= 1 and {item.get("id") for item in term1}.isdisjoint({item.get("id") for item in term3}),
            "unresolved_count": len(state_after_first.get("unresolved_items") or []),
            "receipts": receipts,
            "receipt_count": len(receipts),
            "all_receipts_valid": True,
        }
        report["passed"] = all((
            report["paper_map_unchanged"],
            report["retry_is_idempotent"],
            report["state_hashes"]["retry_state_unchanged"],
            report["cross_node_isolation"],
            report["unresolved_count"] == 1,
            report["receipt_count"] == 2,
            report["study_transition"].get("status") == "learning",
        ))
        (output / "state-observability.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
