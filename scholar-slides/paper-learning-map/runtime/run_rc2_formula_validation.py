"""Run the structured RC2 bridge, projection, and integrity checks.

The harness deliberately sends Tutor records over UTF-8 stdin from memory.  It
does not create a hand-edited ``records.json`` and never writes to the upstream
Scholar-Slides project.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


RUNTIME = Path(__file__).resolve().parent
sys.path.insert(0, str(RUNTIME))

from paper_tutor_projector import project_files  # noqa: E402
from render_paper_map import render_project  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def invoke_bridge(bridge: Path, project: Path, records: list[dict[str, Any]], origin: str) -> dict[str, Any]:
    payload = json.dumps(records, ensure_ascii=False).encode("utf-8")
    # The installed Paper-Tutor bridge consumes structured records directly
    # from stdin; it owns the forwarding to update_tutor_state.py.  Keep the
    # shared writer's subcommand out of this invocation so the validation
    # harness exercises the installed bridge contract rather than bypassing it.
    command = [
        sys.executable,
        str(bridge),
        "--project",
        str(project),
        "--map-root",
        str(RUNTIME.parent),
        "--origin",
        origin,
    ]
    completed = subprocess.run(command, input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    stdout = completed.stdout.decode("utf-8", errors="replace").splitlines()
    parsed: dict[str, Any] | None = None
    for line in reversed(stdout):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            parsed = value
            break
    if completed.returncode or parsed is None:
        stderr = completed.stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"bridge failed ({completed.returncode}): {stderr or stdout[-3:]}")
    if parsed.get("records_received") != len(records):
        raise RuntimeError(f"bridge accepted {parsed.get('records_received')} records, expected {len(records)}")
    return parsed


def swe_records() -> list[dict[str, Any]]:
    from verified_fresh_rc1 import build_full_analysis_records

    return build_full_analysis_records()


def qas(paper: str) -> list[dict[str, Any]]:
    if paper == "swe-touch":
        return [
            {"id": "Q1", "node_id": "term.1", "question": "Counter-Edit 的含义是什么？", "answer": "Counter-Edit 是任务相关、与完成目标冲突的局部用户代码修改，不是随机噪声。"},
            {"id": "Q2", "node_id": "method.step_2", "question": "公式 (3) 的三个验证条件如何工作？", "answer": "VF(R−)=0 排除编辑单独解题，VF(R⋆)=1 确认参考修复有效，VF(R−⋆)=0 排除简单叠加通过。"},
            {"id": "Q3", "node_id": "overview.findings", "question": "Counter-Edit 实验说明了什么？", "answer": "在受测设置下冲突编辑降低 resolve rate，但不能外推到所有真实协作。"},
            {"id": "Q4", "node_id": "term.1", "question": "Counter Edit 含义是什么", "answer": "它仍指任务相关、与目标冲突的局部用户编辑；这是近重复问题。"},
            {"id": "Q5", "node_id": None, "question": "M 是什么意思？", "answer": "上下文不足，保留 unresolved，不猜测锚点。"},
        ]
    return [
        {"id": "Q1", "node_id": "term.4", "question": "Position reward 为什么有作用？", "answer": "它用 P 与 G 的交并比对齐答案和推理引用的位置，补充答案正确性。"},
        {"id": "Q2", "node_id": "method.step_3", "question": "P 和 G 在 Position Reward 中分别是什么？", "answer": "P 是模型标注的位置集合，G 是应被引用的 ground-truth 位置集合。"},
        {"id": "Q3", "node_id": "method.step_3", "question": "Final Reward 的乘法结构限制什么？", "answer": "位置奖励只在答案奖励为正时提供额外信号，格式奖励独立约束结构。"},
        {"id": "Q4", "node_id": "term.4", "question": "Position reward 为什么有作用", "answer": "它把最终答案和推理引用的位置联系起来；这是 Q1 的近重复。"},
        {"id": "Q5", "node_id": None, "question": "M 是什么意思？", "answer": "上下文不足，保留 unresolved，不猜测锚点。"},
    ]


def q_record(item: dict[str, Any]) -> dict[str, Any]:
    node_id = item.get("node_id")
    important = node_id is not None
    return {
        "node_id": node_id,
        "kind": "user_question",
        "question": item["question"],
        "answer": item["answer"],
        "title": item["question"],
        "summary": item["answer"],
        "body": item["answer"],
        "important": important,
        "map_visible": important,
        "importance": "high" if important else "medium",
    }


def state_summary(path: Path) -> dict[str, Any]:
    state = read_json(path)
    items = [item for node in (state.get("nodes") or {}).values() for item in (node.get("map_items") or [])]
    return {
        "schema_version": state.get("schema_version"),
        "nodes": len(state.get("nodes") or {}),
        "map_items": len(items),
        "questions": sum(1 for item in items if item.get("kind") == "user_question"),
        "unresolved_items": len(state.get("unresolved_items") or []),
    }


def run_paper(
    *,
    paper: str,
    map_project: Path,
    scholar_project: Path,
    output: Path,
    bridge: Path,
    full_records: list[dict[str, Any]],
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    factual_paths = {
        "paper_map": map_project / "paper-map.json",
        "scholar_digest": scholar_project / "digest.json",
        "scholar_reading_view": scholar_project / "reading-view.json",
    }
    before = {name: sha256(path) for name, path in factual_paths.items()}
    full = invoke_bridge(bridge, map_project, full_records, "full_analysis")
    render_project(map_project)
    turns: list[dict[str, Any]] = []
    for item in qas(paper):
        result = invoke_bridge(bridge, map_project, [q_record(item)], "incremental_qa")
        render_project(map_project)
        turns.append({"id": item["id"], "question": item["question"], "node_id": item.get("node_id"), **result})

    deep_output = output / "paper-tutor-deep-v2.md"
    compact_output = output / "paper-tutor-compact.md"
    coverage_output = output / "paper-tutor-coverage.json"
    formula_output = output / "formula-index.json"
    deep_html_output = output / "paper-tutor-deep-v2.html"
    coverage = project_files(
        map_project,
        scholar_project,
        compact_output,
        deep_output,
        coverage_output,
        formula_index_path=formula_output,
        deep_html_path=deep_html_output,
    )
    shutil.copy2(formula_output, map_project / "formula-index.json")
    render_project(map_project)

    after = {name: sha256(path) for name, path in factual_paths.items()}
    state = state_summary(map_project / "tutor-state.json")
    study = read_json(map_project / "study-state.json")
    study_learning = sum(1 for node in (study.get("nodes") or {}).values() if node.get("status") == "learning")
    receipt = {
        "schema_version": "1.0",
        "paper": paper,
        "source_identity": read_json(map_project / "paper-map.json").get("paper_identity"),
        "full_analysis": full,
        "incremental_qa": turns,
        "tutor_state": state,
        "study_state": {"learning_nodes": study_learning},
        "factual_integrity": {"before": before, "after": after, "same": before == after},
        "no_records_json_created": not (map_project / "records.json").exists(),
        "projection": {
            "formula_count": coverage.get("formula_count"),
            "formula_blocks": coverage.get("formula_blocks"),
            "experiment_blocks": coverage.get("experiment_blocks"),
            "deep_characters": coverage.get("deep_characters"),
            "compact_characters": coverage.get("compact_characters"),
        },
    }
    write_json(output.parent / "receipts" / "bridge-integrity.json", receipt)
    if not receipt["factual_integrity"]["same"]:
        raise RuntimeError(f"{paper}: factual hash changed")
    if not receipt["no_records_json_created"]:
        raise RuntimeError(f"{paper}: records.json was created")
    if not any(turn.get("id") == "Q5" and turn.get("unresolved_added", 0) == 1 for turn in turns):
        raise RuntimeError(f"{paper}: unresolved Q5 was not observed")
    if not any(turn.get("id") == "Q4" and turn.get("items_deduped", 0) >= 1 for turn in turns):
        raise RuntimeError(f"{paper}: duplicate Q4 was not observed")
    if not any(turn.get("id") in {"Q1", "Q2", "Q3"} and turn.get("study_state") for turn in turns):
        raise RuntimeError(f"{paper}: study-state transition was not observed")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--bridge", required=True)
    parser.add_argument("--reasoning-records", required=True)
    parser.add_argument("--reasoning-scholar", help="Matching verified Scholar-Slides project for the Reasoning-Table fixture")
    args = parser.parse_args()
    root = Path(args.candidate_root).resolve()
    bridge = Path(args.bridge).resolve()
    swe_map = root / "swe-touch" / "map"
    reasoning_map = root / "reasoning-table" / "map"
    swe_scholar = Path("E:/Desktop/scholar-slides/docs/e2e-validation/verified-fresh/swe-touch/scholar").resolve()
    reasoning_scholar = Path(args.reasoning_scholar).resolve() if args.reasoning_scholar else root / "reasoning-table" / "scholar"
    # The verified SWE source is kept read-only outside the candidate.  The
    # Reasoning-Table source is copied into an ASCII candidate path so Python
    # subprocesses remain deterministic on Windows.
    results = {
        "swe-touch": run_paper(
            paper="swe-touch",
            map_project=swe_map,
            scholar_project=swe_scholar,
            output=root / "swe-touch" / "paper-tutor",
            bridge=bridge,
            full_records=swe_records(),
        ),
        "reasoning-table": run_paper(
            paper="reasoning-table",
            map_project=reasoning_map,
            scholar_project=reasoning_scholar,
            output=root / "reasoning-table" / "paper-tutor",
            bridge=bridge,
            full_records=read_json(Path(args.reasoning_records)),
        ),
    }
    write_json(root / "bridge-and-integrity-summary.json", results)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
