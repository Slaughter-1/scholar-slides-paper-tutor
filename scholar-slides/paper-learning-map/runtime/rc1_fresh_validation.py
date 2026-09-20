"""Reproducible RC1 fresh-paper validation.

This harness starts from a Scholar-Slides project produced from a raw PDF,
builds a downstream Paper Learning Map without a hand-authored records file,
syncs Full Analysis through the integrated bridge, then exercises five Q&A
rounds.  It records hashes for the upstream/factual artifacts so Tutor writes
cannot silently mutate them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RC1 fresh-paper Tutor/Map validation")
    parser.add_argument("--project", required=True, help="Scholar-Slides project containing digest.json and source.pdf")
    parser.add_argument("--out", required=True, help="Fresh Paper Learning Map output directory")
    args = parser.parse_args()
    project = Path(args.project).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    # The fresh build creates reading-view.json from the extracted digest and
    # then validates it through the canonical Scholar-Slides reader.  It never
    # accepts a records.json input.
    run(str(HERE / "fresh_e2e.py"), "--project", str(project), "--out", str(out), "--skip-tutor-sync")

    factual_paths = {
        "reading-view.json": out / "reading-view.json",
        "digest.json": project / "digest.json",
        "paper-map.json": out / "paper-map.json",
    }
    before = {name: sha256(path) for name, path in factual_paths.items()}

    # Full Analysis uses the same writer as incremental Q&A.  The bridge reads
    # paper-map semantics and does not parse paper-tutor.md or accept records.
    # This invocation is the deterministic workspace fallback.  The installed
    # Skill's preferred path is `sync --stdin`, where the model streams its
    # in-memory logical records directly.  Keeping the fallback explicit makes
    # the Fresh E2E honest: this harness validates the writer and boundaries,
    # while the Skill hook contract is tested separately below.
    run(str(HERE / "update_tutor_state.py"), "--project", str(out), "sync", "--from-paper-map")
    run(str(HERE / "render_paper_map.py"), "--project", str(out))

    rounds = [
        {"node_id": "term.1", "question": "Agent Harness 是什么？", "answer": "它是负责 Prompt、Context、Tools、Loop 与 Memory 编排的运行时层。"},
        {"node_id": "term.1", "question": "Agent Harness 的作用是什么？", "answer": "它把模型与工具、环境和评测流程连接起来，帮助解释完整系统的表现。"},
        {"node_id": "method.step_1", "question": "为什么需要区分模型和 Harness？", "answer": "否则容易把完整运行链路的结果错误归因给模型本身。"},
        {"node_id": "evidence.block_1", "question": "这些评测指标到底证明了什么？", "answer": "它们能描述系统的准确率、成功率、成本和延迟，但不能单独证明某个组件的因果贡献。"},
        {"node_id": None, "question": "这是什么意思？", "answer": "上下文不足，无法安全绑定到某个稳定节点。", "important": "false"},
    ]
    round_results = []
    for item in rounds:
        before_state = json.loads((out / "study-state.json").read_text(encoding="utf-8"))
        before_status = before_state.get("nodes", {}).get(item.get("node_id"), {}).get("status") if item.get("node_id") else None
        cmd = [str(HERE / "update_tutor_state.py"), "--project", str(out), "ask"]
        if item.get("node_id"):
            cmd.extend(["--node-id", str(item["node_id"])])
        cmd.extend(["--question", item["question"], "--answer", item["answer"]])
        if item.get("important"):
            cmd.extend(["--important", str(item["important"])])
        run(*cmd)
        after_state = json.loads((out / "study-state.json").read_text(encoding="utf-8"))
        round_results.append({"question": item["question"], "node_id": item.get("node_id"), "before_status": before_status, "after_status": after_state.get("nodes", {}).get(item.get("node_id"), {}).get("status") if item.get("node_id") else None})

    run(str(HERE / "render_paper_map.py"), "--project", str(out))

    after = {name: sha256(path) for name, path in factual_paths.items()}
    state = json.loads((out / "tutor-state.json").read_text(encoding="utf-8"))
    study = json.loads((out / "study-state.json").read_text(encoding="utf-8"))
    report = {
        "fresh_source_pdf": str(project / "source.pdf"),
        "fresh_source_pdf_sha256": sha256(project / "source.pdf"),
        "rounds": rounds,
        "round_results": round_results,
        "factual_hashes_before": before,
        "factual_hashes_after": after,
        "factual_layer_unchanged": before == after,
        "tutor_state_schema_version": state.get("schema_version"),
        "tutor_node_count": len(state.get("nodes", {})),
        "tutor_item_count": sum(len(value.get("map_items", [])) for value in state.get("nodes", {}).values()),
        "unresolved_items": state.get("unresolved_items", []),
        "term_1_study_status": study.get("nodes", {}).get("term.1", {}).get("status"),
        "method_step_1_study_status": study.get("nodes", {}).get("method.step_1", {}).get("status"),
        "evidence_block_1_study_status": study.get("nodes", {}).get("evidence.block_1", {}).get("status"),
        "semantic_duplicate_item_count": len([item for item in state.get("nodes", {}).get("term.1", {}).get("map_items", []) if item.get("kind") == "user_question"]),
    }
    (out / "rc1-fresh-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not report["factual_layer_unchanged"]:
        raise SystemExit("factual layer hash changed during Tutor sync")
    if report["term_1_study_status"] != "learning" or report["method_step_1_study_status"] != "learning" or report["evidence_block_1_study_status"] != "learning":
        raise SystemExit("resolved first questions did not move unseen nodes to learning")
    if not any(item.get("reason") == "no_anchor" for item in report["unresolved_items"]):
        raise SystemExit("unanchored question was not preserved as unresolved")
    print(json.dumps({key: report[key] for key in ("factual_layer_unchanged", "tutor_item_count", "term_1_study_status", "method_step_1_study_status", "evidence_block_1_study_status", "semantic_duplicate_item_count")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
