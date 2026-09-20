from __future__ import annotations

import argparse, hashlib, json, shutil, subprocess, sys
from pathlib import Path

def build_view(project: Path) -> None:
    digest = json.loads((project / "digest.json").read_text(encoding="utf-8"))
    title = digest["paper_metadata"]["title"]
    sha = digest["paper_metadata"]["pdf_sha256"]
    refs = ["p. 1"]
    def rec(text, claim="analysis", evidence=refs):
        return {"content": text, "claim_type": claim, "availability": "supported", "evidence_refs": evidence}
    view = {"schema_version": 1, "paper_identity": {"title": title, "source_pdf_sha256": sha}, "source_bindings": [{"path": "digest.json", "sha256": hashlib.sha256((project / "digest.json").read_bytes()).hexdigest()}, {"path": "source.pdf", "sha256": sha}], "language": "zh-CN", "paper_type": {"kind": "mixed", "reason": "Fresh E2E source is a system and benchmark teaching report."}, "overview": {"problem": rec("如何把模型、Harness、环境与 Benchmark 的关系讲清楚。"), "gap": rec("只看模型分数会混淆 Harness、工具、预算和评测设置的影响。"), "approach": rec("从原始 PDF 的提取证据构造问题、机制、证据和术语的阅读视图。"), "insight": rec("系统成绩应作为完整运行链路的结果理解。"), "findings": rec("文档讨论了 Accuracy、Pass@1、success rate、cost、latency 等指标。"), "boundary": rec("当前 PDF 提取结果不是经过 CKPT-1 人工确认的完整研究结论。", "analysis")}, "mechanism_steps": [{"title": "区分模型与 Harness", "purpose": "明确参数训练与运行时编排的边界", "input": "模型、Prompt、Tools、Loop、Memory", "output": "可比较的系统链路", "necessity": "避免把系统分数直接归因给模型", "claim_type": "explanation", "availability": "supported", "evidence_refs": ["p. 2"]}, {"title": "定义评测协议", "purpose": "把环境、metric、evaluator 和预算纳入比较", "input": "任务与运行环境", "output": "可复核的 Benchmark 设置", "necessity": "保证结果边界清楚", "claim_type": "explanation", "availability": "supported", "evidence_refs": ["p. 7"]}], "argument_chain": [{"node": "Problem", "relation": "motivates", "claim_type": "analysis", "availability": "supported", "evidence_refs": refs}, {"node": "Method", "relation": "implements", "claim_type": "analysis", "availability": "supported", "evidence_refs": ["p. 2"]}, {"node": "Evidence", "relation": "supports", "claim_type": "paper_fact", "availability": "supported", "evidence_refs": ["p. 7"]}], "decisive_evidence": [{"question": "评测到底量化什么？", "comparison": "Accuracy、Pass@1、success rate、cost、latency", "metric": "多维系统指标", "result": "文档列出这些指标作为系统评测维度。", "can_support": "评测不只看单一准确率。", "cannot_support": "不能由提取摘要推出某个模型的优胜结论。", "claim_type": "paper_fact", "availability": "supported", "evidence_refs": ["p. 7"]}], "terms": [{"term": "Agent Harness", "plain": "模型外负责 Prompt、Context、Tools、Loop、Memory 等运行时编排的层。", "role": "连接模型与评测环境。", "confusions": "不等于模型参数或训练算法。", "claim_type": "explanation", "availability": "supported", "evidence_refs": ["p. 2"]}, {"term": "Benchmark", "plain": "包含任务、环境、指标、评估器和预算的评测协议。", "role": "测量完整系统。", "confusions": "不等于只有数据集。", "claim_type": "explanation", "availability": "supported", "evidence_refs": ["p. 2"]}], "takeaways": [{"kind": "reader_analysis", "content": "读 Agent 论文时应同时核对模型、Harness、工具、环境、预算与 evaluator。", "claim_type": "analysis", "availability": "supported", "evidence_refs": ["p. 9"]}, {"kind": "explicit_limitation", "content": "本次 Fresh E2E 以原始 PDF 和 extractive digest 为输入，仍保留 CKPT-1 pending 边界。", "claim_type": "analysis", "availability": "supported", "evidence_refs": ["p. 1"]}]}
    (project / "reading-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8")

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--project", required=True); parser.add_argument("--out", required=True); parser.add_argument("--skip-tutor-sync", action="store_true", help="stop after source-grounded map creation")
    args = parser.parse_args(); project = Path(args.project).resolve(); out = Path(args.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    # Keep the Scholar-Slides project read-only.  The candidate reading view
    # is a validation bridge generated in the isolated downstream project; it
    # carries the source identity and remains explicitly CKPT-1-pending.
    for name in ("digest.json", "source.pdf"):
        source = project / name
        if not source.is_file():
            raise SystemExit(f"fresh source project is missing {name}: {source}")
        shutil.copy2(source, out / name)
    build_view(out)
    subprocess.run([sys.executable, str(Path(__file__).with_name("build_paper_map.py")), "--project", str(out), "--out", str(out)], check=True)
    if not args.skip_tutor_sync:
        subprocess.run([sys.executable, str(Path(__file__).with_name("update_tutor_state.py")), "--project", str(out), "sync", "--from-paper-map"], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("render_paper_map.py")), "--project", str(out)], check=True)
    return 0
if __name__ == "__main__": raise SystemExit(main())
