"""Run the verified Fresh Paper RC1 Tutor/Map transaction.

This is an execution harness for the already reviewed SWE-Touch reading view.
The Full Analysis and each follow-up Q&A payload are built in memory and sent
to the installed Paper-Tutor bridge over stdin; no records.json is created.
The factual Scholar-Slides layer is treated as read-only and is hash-checked
before and after every downstream operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def state_summary(path: Path) -> dict[str, Any]:
    value = read_json(path)
    items = [
        item
        for node in (value.get("nodes") or {}).values()
        for item in (node.get("map_items") or [])
        if isinstance(item, dict)
    ]
    return {
        "schema_version": value.get("schema_version"),
        "nodes": len(value.get("nodes") or {}),
        "map_items": len(items),
        "unresolved_items": len(value.get("unresolved_items") or []),
    }


def _record(node_id: str, kind: str, title: str, summary: str, body: str, *, visible: bool = True, importance: str = "high", tags: list[str] | None = None) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "kind": kind,
        "title": title,
        "summary": summary[:160],
        "body": body,
        "map_visible": visible,
        "importance": importance,
        "tags": tags or ["fresh-verified", "full-analysis"],
    }


def build_full_analysis_records() -> list[dict[str, Any]]:
    """Return the current paper analysis as Tutor-layer records in memory."""

    return [
        _record(
            "overview.problem", "tutor_explanation", "如何读这个问题",
            "把用户改代码视为共享状态变化，而不是普通聊天反馈。",
            "Tutor Explanation：SWE-Touch 的问题不是‘模型会不会写补丁’这么简单，而是用户在任务进行中改变可执行仓库后，代理能否重新理解当前状态并继续修复。静态 benchmark 通常固定初始仓库，因此这里要把仓库状态变化作为一等输入。",
        ),
        _record(
            "overview.gap", "reader_analysis", "Gap 的关键边界",
            "现有编码代理评测多为独立工作或 message-only 交互。",
            "Tutor Analysis：论文把缺口限定为用户直接修改可执行代码，而不是泛化到所有协作行为。SWE-chat 分析报告 59.0% 会话出现用户归因的仓库变化（Figure 1），这说明交互渠道具有现实动机，但该比例本身不证明模型鲁棒性。",
        ),
        _record(
            "overview.approach", "tutor_explanation", "SWE-Touch 主线",
            "先找关键区域，再生成并验证冲突编辑，最后注入共享工作空间。",
            "Tutor Explanation：整条链路是‘多条轨迹定位区域 → User Patch Generator 产生局部 Counter-Edit → 通过三条件验证 → 在代理触达重叠区域时注入编辑和上下文消息 → 用任务 verifier 比较 Vanilla 与 Counter-Edit’。每一步都在缩小干预的随机性。",
        ),
        _record(
            "overview.insight", "reader_analysis", "自治分数不是协作鲁棒性",
            "静态 resolve rate 不能直接预测共享工作空间下的表现。",
            "Tutor Analysis：应把‘能独立完成’和‘能识别外部状态变化并恢复’分开看。论文报告 Counter-Edit 平均使 SWE-bench Verified resolve rate 下降 7.7 个百分点，且模型间损失从 1.3 到 16.5 个百分点不等；这支持‘新增交互维度’的解读，而不是简单的统一惩罚。",
        ),
        _record(
            "overview.findings", "tutor_explanation", "主结果怎么读",
            "主结果是受控冲突下的成对退化与行为差异。",
            "Tutor Explanation：9 个模型在 Vanilla 与 Counter-Edit 下成对比较。Claude Opus 4.8 从 85.2% 到 83.3%，GPT 5.5 从 80.5% 到 79.2%；其他模型退化更大，排序也会变化。结论是‘状态感知和适应仍不足’，不是某个模型在所有设置下绝对最好。",
        ),
        _record(
            "overview.boundary", "reader_analysis", "结论能走多远",
            "这是受控、模拟的 task-conflicting edit，不等于全部真实协作。",
            "Tutor Analysis：Counter-Edit 让因果比较更清楚，但它只覆盖任务相关、与完成目标冲突的局部编辑。论文的限制部分明确指出，真实协作还包括部分正确修复、需求变化和双向适应；因此不能把本实验直接外推为所有用户行为的总体风险。",
        ),
        _record(
            "method.step_1", "intuition", "为什么先挖关键区域",
            "让干预靠近代理真正依赖的代码，而不是随机位置。",
            "Tutor Explanation：对每个任务收集 GPT 5.5、GLM 5.1、MiniMax M2.7 的完整轨迹，分别统计 Read/Edit 覆盖并取交集，再按优先级合并邻近区间，最多保留 8 个区域。这样 Counter-Edit 更像任务相关的状态冲突。",
        ),
        _record(
            "method.step_2", "intuition", "Counter-Edit 的三重验证",
            "编辑本身不能解题，也不能与参考修复简单叠加通过。",
            "Tutor Explanation：公式 (3) 要求 VF(R−)=0、VF(R⋆)=1、VF(R−⋆)=0。第一条排除‘用户编辑单独解题’，第二条确认参考修复有效，第三条排除‘把两份 patch 叠起来就能通过’。这让冲突具有可解释的任务语义。",
        ),
        _record(
            "method.step_3", "necessity", "何时注入用户编辑",
            "代理读写与编辑区域重叠时触发，最多 K 次。",
            "Tutor Explanation：运行时按 Scope(a_t) 与编辑行集合的交集触发；默认 K=3。每次把可应用的 Counter-Edit 和由轨迹上下文生成的用户消息一起交给代理，代理在下一步看到的是演化后的仓库状态。长时程 benchmark 改用轨迹分数位置注入，因此两类设置要分开报告。",
        ),
        _record(
            "method.step_4", "tutor_explanation", "为什么要看 verifier 和轨迹",
            "最终通过率与过程行为互相补充。",
            "Tutor Explanation：resolve 是 verifier 通过的任务比例；retention 只在 Vanilla 多数解决的任务上计算保留比例。再结合 steps、tokens 与失败分类，才能区分‘完全没发现冲突’、‘发现后改错’和‘改了但没有充分验证’，避免把更多调用次数误当作恢复。",
        ),
        _record(
            "evidence.block_1", "reader_analysis", "59.0% 证据支持什么",
            "用户改代码是现实交互通道的动机证据。",
            "Tutor Analysis：Figure 1 对 SWE-chat 的分析报告 59.0% 会话含用户归因的仓库变化。它支持‘共享工作空间值得专门评测’，但不能推出任何模型的成功率或因果机制。",
        ),
        _record(
            "evidence.block_2", "tutor_explanation", "7.7 个百分点的含义",
            "Counter-Edit 条件平均降低 SWE-bench Verified resolve rate。",
            "Tutor Explanation：9 个模型平均下降 7.7 个百分点，模型级变化范围 1.3–16.5 个百分点。Co-Edit 控制平均只有 −0.1 个百分点，而 Counter-Edit 约 −7.2 个百分点，说明主要困难与‘冲突方向’有关，而非任意外部改动。",
        ),
        _record(
            "evidence.block_3", "tutor_explanation", "实验覆盖范围",
            "主实验 200 个 SWE-bench Verified 任务，另有两个长时程集合。",
            "Tutor Explanation：主实验是带种子的 200 个任务，100-step budget，每条件 3 次独立运行；SWE-Bench Pro 和 DeepSWE 各取 25 个任务，500-step budget、每条件 2 次。4.0% 主任务没有保留可用 patch 而使用 text-only feedback，6.4% scored Counter-Edit runs 没有实际改变仓库，这些边界应保留在报告里。",
        ),
        _record(
            "evidence.block_4", "reader_analysis", "失败行为的证据链",
            "失败既可能保留冲突，也可能反抗后改错或验证不足。",
            "Tutor Analysis：Figure 4 的审计中，63.3% 是 retained conflict，13.9% incorrect replacement，11.6% incomplete reconciliation，5.5% off-target；修订率与性能变化的 Spearman ρ=0.80 只是模型层面的相关性，不能当作修订导致恢复的因果证明。",
        ),
        _record(
            "term.1", "tutor_explanation", "Counter-Edit",
            "任务相关、局部、看似合理但与完成目标冲突的用户代码修改。",
            "Tutor Explanation：它不是随机噪声，也不是能独立解决任务的参考 patch。其作用是构造一个必须检查当前仓库状态、识别冲突并重新验证的受控压力。",
        ),
        _record(
            "term.2", "tutor_explanation", "任务关键区域",
            "从多条读写轨迹中提取的、与修复过程相关的代码范围。",
            "Tutor Explanation：区域由 Read/Edit 覆盖证据确定，并按实现文件优先于测试或元数据的规则筛选；它决定 Counter-Edit 放在哪里，不等于整个仓库。",
        ),
        _record(
            "term.3", "tutor_explanation", "共享工作空间",
            "代理与用户共同观察、读取和修改的演化仓库状态。",
            "Tutor Explanation：这里的 workspace 不只是对话上下文，还包括当前代码、diff、测试结果和后续动作所看到的仓库状态。",
        ),
        _record(
            "term.4", "tutor_explanation", "Resolve rate",
            "通过完整任务 verifier 的任务比例。",
            "Tutor Explanation：它不是单个测试的通过率，也不是模型能力的全部；论文同时报告 retention、steps、tokens 和失败类型，避免只看一个数字。",
        ),
        _record(
            "term.5", "tutor_explanation", "Retention",
            "Vanilla 多数解决任务在 Counter-Edit 下仍保持解决的比例。",
            "Tutor Explanation：Retention 的分母是 Vanilla 多数解决的任务，不等同于总体 resolve rate；它更适合回答‘原本成功的任务保住了多少’。",
        ),
        _record(
            "takeaway.1", "tutor_explanation", "贡献的最短总结",
            "把用户直接改代码纳入编码代理 benchmark。",
            "Tutor Explanation：论文从 message-only 交互推进到共享可执行状态，并给出可验证的 Counter-Edit 协议。",
        ),
        _record(
            "takeaway.2", "reader_analysis", "主要限制",
            "受控模拟编辑不能覆盖真实协作的全部分布。",
            "Tutor Analysis：应把论文结论限定在其触发规则、patch 生成器、预算和 verifier 设置内。",
        ),
        _record(
            "takeaway.3", "reader_analysis", "阅读建议",
            "同时查看结果、状态变化和再检查行为。",
            "Tutor Analysis：更多 steps 或 tokens 并不保证恢复；过程是否找到受影响代码、改对并用 targeted tests 验证更关键。",
        ),
        _record(
            "takeaway.4", "reader_analysis", "可验证的后续问题",
            "把检测、冲突协调和验证分别控制会怎样？",
            "Tutor Analysis：这是基于论文失败链条提出的研究问题，不是作者已经证明的结果。",
        ),
    ]


def invoke_bridge(bridge: Path, map_root: Path, project: Path, records: list[dict[str, Any]], origin: str) -> dict[str, Any]:
    payload = json.dumps(records, ensure_ascii=False).encode("utf-8")
    env = dict(os.environ)
    env["PAPER_LEARNING_MAP_ROOT"] = str(map_root)
    completed = subprocess.run(
        [sys.executable, str(bridge), "--map-root", str(map_root), "--project", str(project), "--origin", origin],
        input=payload,
        capture_output=True,
        env=env,
        check=False,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace").strip()
    stderr = completed.stderr.decode("utf-8", errors="replace").strip()
    if completed.returncode:
        raise RuntimeError(f"bridge failed ({completed.returncode}): {stderr or stdout}")
    try:
        result = json.loads(stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"bridge returned no JSON result: {stdout!r}; stderr={stderr!r}") from exc
    if result.get("status") == "failed":
        raise RuntimeError(f"bridge reported failed sync: {result}")
    result["stderr"] = stderr
    return result


def factual_hashes(scholar: Path, map_project: Path) -> dict[str, str]:
    return {
        "pdf": sha256(scholar / "source.pdf"),
        "digest": sha256(scholar / "digest.json"),
        "reading_view": sha256(scholar / "reading-view.json"),
        "paper_map": sha256(map_project / "paper-map.json"),
    }


def write_tutor_projection(out: Path) -> None:
    paper_tutor = out / "paper-tutor.md"
    paper_tutor.write_text(
        """# SWE-Touch: Benchmarking Coding Agents When Users Touch the Code

来源：Scholar-Slides integrated；CKPT-1 confirmed（Explicit user-authorized RC1 validation）；讲解深度：deep

## 30 秒主线

SWE-Touch 把用户在任务进行中直接修改共享代码这一现实交互，变成可控的 Counter-Edit 评测：先从多条代理轨迹挖出任务关键区域，再生成并验证与任务完成冲突的局部编辑，在代理触达相关代码时注入，最后用完整 verifier 比较 Vanilla 与 Counter-Edit。主实验显示，9 个模型在 SWE-bench Verified 上的平均 resolve rate 下降 7.7 个百分点；失败主要来自保留冲突、错误替换、不完整协调和验证不足。

## Benchmark Card

| 问题你必须回答 | 回答 |
| --- | --- |
| **Motivation** | 既有仓库级 benchmark 多让代理独立工作，或只用消息模拟用户；它们没有评估用户直接改变可执行代码后代理如何适应（PDF pp. 2–3；digest `context`）。 |
| **Capability** | 评估代理识别演化中的共享工作空间、协调任务冲突并重新验证受影响行为的能力；这是协作鲁棒性构造，不等同于一般自治编码能力。 |
| **Task** | SWE-bench Verified 的仓库修复；补充 SWE-Bench Pro 与 DeepSWE 的长时程修复；每个任务在 Vanilla 或 Counter-Edit 条件下完成。 |
| **Input / Output** | 输入是 issue、初始仓库、测试 verifier、轨迹中的用户编辑和上下文消息；输出是继续修复后的仓库状态与代理轨迹。成功要求完整 verifier 通过，且原本通过的测试仍保持通过。 |
| **Dataset** | 主评测为带种子的 200 个 SWE-bench Verified 任务；长时程集合各 25 个任务。主任务中 96.0% 保留可用 patch，4.0% 使用 text-only feedback；另记录 6.4% scored runs 未实际改变仓库。 |
| **Environment** | Mini-SWE-Agent shell interface；主实验 100-step、每条件 3 次、按读写区域重叠触发，默认最多 K=3；长时程使用 500-step、每条件 2 次并按轨迹分数位置注入。 |
| **Models** | Claude Opus 4.8、GPT 5.5、GLM 5.1、MiniMax M2.7、MiniMax M2.5、Qwen 3.7 Max、Qwen3-Coder-480B-A35B、Kimi K2.6、DeepSeek V4 Pro。 |
| **Agent** | 9 个 coding agent 在同一任务条件下比较；区域挖掘使用 GPT 5.5、GLM 5.1、MiniMax M2.7 的完整轨迹，评测条件分别为自治 Vanilla 与注入 Counter-Edit。 |
| **Baseline** | 主要 baseline 是同一任务、同一模型的 Vanilla（无外部冲突编辑）；Co-Edit 是控制条件，用于区分一般外部改动与任务冲突。 |
| **Metric** | Resolve rate 是完整 verifier 通过比例；同时报告 retention、steps、tokens、成本和 Counter-Edit−Vanilla 的差值。Retention 的分母是 Vanilla 多数解决的任务。 |
| **Result** | SWE-bench Verified 平均下降 7.7 个百分点，模型级损失 1.3–16.5；Claude Opus 4.8 与 GPT 5.5 相对稳定，但排序会重排。SWE-Bench Pro 与 DeepSWE 也出现设置相关的退化。 |
| **Scaling** | 编辑频率 K=1/3/5 的变化不是统一剂量反应；MiniMax M2.7 与 Qwen 3.7 Max 随 K 增大更差，而 GPT 5.5/GLM 5.1 在部分区间平台或恢复。更长时程通常增加调用，却不稳定地恢复 resolve rate。 |
| **Failure** | 审计的 solved→unresolved 运行中，63.3% 保留冲突，13.9% 错误替换，11.6% 协调不完整，5.5% off-target；作者还报告验证不足等类别。 |
| **Validity** | 内部公平性来自成对 Vanilla/Counter-Edit、统一 verifier 和 Co-Edit 控制；外部真实性受控于模拟、任务相关的冲突编辑；污染与真实用户行为分布不能由本实验单独证明。 |
| **Conclusion** | 在受测任务、模型、预算和触发协议下，自治 resolve rate 不足以预测共享工作空间鲁棒性；代理需要检测变化、协调冲突并验证受影响行为。 |
| **Research Gap** | Tutor Analysis：把变化检测、冲突协调、目标行为验证和更真实的双向用户模拟分别控制，能否解释并改善失败？这些是后续问题，不是本 benchmark 已完成的结论。 |

## Task → Input / Output Map

| Task | Capability | Input / Observation | Output / Action | Success criterion |
| --- | --- | --- | --- | --- |
| SWE-bench Verified + Vanilla | 自治仓库修复 | issue、仓库、测试、shell | 读/改/测并提交最终仓库 | 完整 verifier 通过 |
| SWE-bench Verified + Counter-Edit | 共享状态冲突协调 | Vanilla 同类任务，加上局部 Counter-Edit 与上下文消息 | 检查当前代码、修复冲突、针对性测试 | 完整 verifier 通过且 pass-to-pass 不回退 |
| SWE-Bench Pro / DeepSWE | 长时程状态适应 | 更大仓库、更长轨迹、按固定分数位置注入 | 在 500-step 预算内继续修复 | 同一 verifier 条件下 resolve |

## Benchmark 一句公式

**作者认为现有 Benchmark 无法评估用户直接修改共享可执行代码后代理的状态感知与冲突协调，因此构建了包含 200 个 SWE-bench Verified 任务及长时程任务的数据和 Counter-Edit 任务，使用 resolve rate、retention、steps 与 tokens 指标评估 9 个 coding 模型/Agent，最终发现当前模型主要在检测外部变化、协调冲突和重新验证受影响行为上存在明显不足。**

## 为什么这样测

Paper Fact：SWE-chat 会话中 59.0% 出现用户归因的仓库变化（Figure 1）。Tutor Explanation：这给出交互动机；真正的能力构造由 Counter-Edit 把‘代码状态改变’和‘任务目标冲突’同时固定下来。Co-Edit 平均仅 −0.1 个百分点，而 Counter-Edit 约 −7.2 个百分点，支持冲突语义而非任意中断是主要压力来源。

## 一道任务怎样完成并评分

代理先在 Vanilla 或 Counter-Edit 条件下通过 Mini-SWE-Agent shell 读、改、测。Counter-Edit 由关键区域、生成器和三条件验证得到，代理触达重叠区域后接收编辑及上下文消息。Resolve rate 要求 fail-to-pass 与 pass-to-pass verifier 同时满足；steps、tokens 和 retention 用来解释代价与保持程度，而不是替代成功标准。

## 实验真正发现了什么

Paper Fact：平均 resolve rate 下降 7.7 个百分点，且损失异质；Figure 4 的 63.3% retained conflict 说明很多失败甚至没有真正移除冲突。Tutor Analysis：修订率与性能变化的 ρ=0.80 只能说明相关模式；每条轨迹仍可能因为错误替换或验证不充分而失败。长时程实验中增加调用通常没有自动转化为恢复。

## 结论能走多远

作者结论限于受控、模拟、任务相关的用户编辑。不能据此断言所有真实用户行为、所有代码库或未来模型都会有相同退化，也不能把相关性当作组件的因果证明。后续可测试部分正确编辑、需求变化、动态用户模拟及显式状态检测/验证策略。

## Claim → Evidence Appendix

| Claim ID | Claim | Type | Evidence |
| --- | --- | --- | --- |
| C1 | 59.0% SWE-chat 会话含用户归因仓库变化。 | Paper Fact | PDF p. 2, Figure 1；`digest.json#/figures/0` |
| C2 | 主实验使用带种子的 200 个 SWE-bench Verified 任务。 | Paper Fact | PDF p. 6；`digest.json#/paper_semantics/slots/experimental_setup` |
| C3 | Counter-Edit 使平均 resolve rate 下降 7.7 个百分点。 | Paper Fact | PDF pp. 1, 7；`digest.json#/paper_semantics/slots/limitations_or_failure_modes` |
| C4 | 失败中 retained conflict 占 63.3%。 | Paper Fact | PDF p. 10, Figure 4；`digest.json#/figures/9` |
| C5 | 修订率与性能变化的 ρ=0.80。 | Paper Fact（相关性） | PDF p. 11, Figure 4；`digest.json#/figures/9` |
| C6 | 把检测、协调和验证分开控制是后续研究方向。 | Tutor Analysis | 基于 C3–C5 的边界分析，不是作者已验证的新增结果 |

## 来源与验证状态

- Paper identity：SWE-Touch: Benchmarking Coding Agents When Users Touch the Code；arXiv:2608.02499v1；39 pages。
- Analysis source: Scholar-Slides-backed Paper-Tutor analysis。
- Evidence source: matching confirmed Scholar-Slides digest, source-bound reading-view, and original PDF.
- Paper map: `source.mode=integrated`; `verification_level=scholar_slides_validated`。
- Tutor records are downstream only (`source_layer=tutor`); no Paper Fact, digest, reading-view, or paper-map content was written by the bridge.
- Depth: deep
""",
        encoding="utf-8",
    )

    (out / "reading-note.md").write_text(
        """# SWE-Touch: Benchmarking Coding Agents When Users Touch the Code

## Reading Card

| Field | Answer |
|---|---|
| Problem | 静态或 message-only benchmark 没有评估用户直接改变共享可执行代码后代理如何适应。 |
| Setting | Input: issue、仓库、verifier、Counter-Edit 与上下文消息；Output: 继续修复后的仓库状态；Supervision / Feedback: 运行时用户编辑与最终 verifier。 |
| Baseline | Primary baseline: 同模型同任务的 Vanilla；Co-Edit 是外部改动控制。 |
| Method | 多轨迹 → 关键区域 → User Patch Generator → 三条件验证 Counter-Edit → 重叠触发注入 → verifier 比较；各模块分别修复随机位置、可独立解题、简单叠加和不可解释触发。 |
| Objective | No trainable objective introduced；这是评测协议，优化压力来自任务冲突与状态变化。 |
| Evaluation | Dataset: 200 SWE-bench Verified + 各 25 个 SWE-Bench Pro/DeepSWE；Metric: resolve、retention、steps、tokens；Model / Backbone: 9 个 coding models；Shot setting: 每条件 3 次（主实验）或 2 次（长时程）。 |
| Result | 平均 resolve 下降 7.7 个百分点，损失范围 1.3–16.5；强模型相对稳定但排序会重排。 |
| Ablation | Message-only 影响小且不一致；code edit 单独造成更一致退化；Co-Edit 平均 −0.1，支持冲突语义的必要性。 |
| Failure | Author-reported：保留冲突、错误替换、协调不完整、off-target、验证不足；Reader inference：恢复需要检测、改对和 targeted verification 的组合。 |
| Your idea | 若保持任务与预算不变、只加入显式 workspace-diff 检测再触发 targeted tests，预测 retained conflict 与 incomplete reconciliation 下降；需用同一 Vanilla/Counter-Edit 配对实验证伪。 |

## One-sentence takeaway

自治编码分数不能替代共享工作空间中的状态感知、冲突协调和验证能力。

## Verification Question

Question: 在相同 Counter-Edit 与预算下，显式 diff 检测加 targeted tests 是否比现有 agent 降低 retained-conflict 比例？
Hypothesis: 会降低 retained conflict 与 solved→unresolved 转换。
Test: 固定任务、模型、K 和 verifier，仅加入检测/测试策略并比较三次运行的 failure composition。
Disconfirming evidence: resolve、retention 或 retained-conflict 比例无改善，或新增策略只增加 steps/tokens。
""",
        encoding="utf-8",
    )

    (out / "method.svg").write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="430" viewBox="0 0 1500 430">
  <style>text{font-family:Arial,'Microsoft YaHei',sans-serif;fill:#17212b} .box{fill:#eef6fb;stroke:#176b87;stroke-width:2} .core{fill:#fff1d6;stroke:#a76522;stroke-width:3} .out{fill:#e6f4ed;stroke:#2f7d55;stroke-width:2} .arrow{stroke:#526575;stroke-width:3;fill:none;marker-end:url(#m)} .small{font-size:17px} .title{font-size:23px;font-weight:700}</style>
  <defs><marker id="m" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#526575"/></marker></defs>
  <rect class="box" x="30" y="150" width="190" height="110" rx="14"/><text class="title" x="55" y="195">Input</text><text class="small" x="55" y="225">issue + 初始仓库</text><text class="small" x="55" y="248">+ verifier</text>
  <rect class="box" x="270" y="125" width="220" height="160" rx="14"/><text class="title" x="290" y="170">关键区域挖掘</text><text class="small" x="290" y="205">多条 Read/Edit 轨迹</text><text class="small" x="290" y="233">交集与优先级</text><text class="small" x="290" y="262">修复：随机注入风险</text>
  <rect class="core" x="540" y="105" width="245" height="200" rx="14"/><text class="title" x="565" y="150">Counter-Edit</text><text class="small" x="565" y="185">生成局部冲突 patch</text><text class="small" x="565" y="213">VF(R−)=0</text><text class="small" x="565" y="239">VF(R⋆)=1</text><text class="small" x="565" y="265">VF(R−⋆)=0</text><text class="small" x="565" y="292">修复：伪冲突/叠加通过</text>
  <rect class="box" x="835" y="125" width="245" height="160" rx="14"/><text class="title" x="855" y="170">共享工作空间</text><text class="small" x="855" y="205">重叠触发注入</text><text class="small" x="855" y="233">编辑 + 上下文消息</text><text class="small" x="855" y="262">修复：状态变化盲点</text>
  <rect class="out" x="1130" y="125" width="330" height="160" rx="14"/><text class="title" x="1150" y="170">Output / Evaluation</text><text class="small" x="1150" y="205">修复后仓库 + 轨迹</text><text class="small" x="1150" y="233">resolve / retention</text><text class="small" x="1150" y="261">失败分类与成本</text>
  <path class="arrow" d="M220 205 L270 205"/><path class="arrow" d="M490 205 L540 205"/><path class="arrow" d="M785 205 L835 205"/><path class="arrow" d="M1080 205 L1130 205"/>
</svg>
""",
        encoding="utf-8",
    )


def write_depth_projections(out: Path, scholar: Path, project: Path) -> None:
    """Generate Compact and Deep Markdown from the post-sync structured state."""
    projector = Path(__file__).with_name("paper_tutor_projector.py")
    compact = out / "paper-tutor-compact.md"
    deep = out / "paper-tutor-deep-v2.md"
    coverage = out / "paper-tutor-coverage.json"
    subprocess.run(
        [
            sys.executable,
            str(projector),
            "--map-project",
            str(project),
            "--scholar-project",
            str(scholar),
            "--compact-output",
            str(compact),
            "--deep-output",
            str(deep),
            "--coverage-output",
            str(coverage),
        ],
        check=True,
    )
    # Preserve an existing RC1 artifact for Before/After comparison.  A new
    # output directory still gets a canonical compact paper-tutor.md.
    legacy = out / "paper-tutor.md"
    if not legacy.exists():
        legacy.write_text(compact.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute the Fresh SWE-Touch RC1 Tutor/Map validation")
    parser.add_argument("--scholar-project", required=True)
    parser.add_argument("--map-project", required=True)
    parser.add_argument("--bridge", required=True)
    parser.add_argument("--map-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    scholar = Path(args.scholar_project).resolve()
    project = Path(args.map_project).resolve()
    bridge = Path(args.bridge).resolve()
    map_root = Path(args.map_root).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt_root = output.parent / "receipts"
    receipt_root.mkdir(parents=True, exist_ok=True)
    baseline = read_json(receipt_root / "factual-integrity-before.json")
    before = factual_hashes(scholar, project)
    expected = {
        "pdf": baseline["source"]["sha256"],
        "digest": baseline["digest"]["sha256"],
        "reading_view": baseline["reading_view"]["sha256"],
        "paper_map": baseline["paper_map"]["sha256"],
    }
    if before != expected:
        raise SystemExit(f"factual baseline mismatch before Tutor operations: {before} != {expected}")

    full_records = build_full_analysis_records()
    full_result = invoke_bridge(bridge, map_root, project, full_records, "full_analysis")
    subprocess.run([sys.executable, str(map_root / "runtime" / "render_paper_map.py"), "--project", str(project)], check=True)

    questions = [
        {
            "id": "Q1",
            "question": "Counter-Edit 是什么意思？",
            "answer": "Counter-Edit 是靠近任务关键代码、看似合理但会与任务完成冲突的用户代码修改；它不是随机噪声，也不是能独立解题的参考 patch。",
            "node_id": "term.1",
        },
        {
            "id": "Q2",
            "question": "为什么要把 Counter-Edit 放在任务关键区域？",
            "answer": "这样干预会落在代理实际读写、真正影响修复的代码附近，避免随机位置造成不可解释的失败。",
            "node_id": "method.step_1",
        },
        {
            "id": "Q3",
            "question": "公式 (3) 的三个验证条件具体如何工作？",
            "answer": "VF(R−)=0 排除编辑单独解题，VF(R⋆)=1 确认参考修复有效，VF(R−⋆)=0 排除两者简单叠加就能通过。",
            "node_id": "method.step_2",
        },
        {
            "id": "Q4",
            "question": "这个实验真正说明了什么？",
            "answer": "在受测设置下，冲突编辑平均降低 resolve rate，且失败机制异质；它说明自治分数不能替代共享状态下的检测、协调和验证能力。",
            "node_id": "evidence.block_2",
        },
        {
            "id": "Q5",
            "question": "M 是什么意思？",
            "answer": "没有足够上下文安全绑定到具体论文节点，因此保留为 unresolved，不猜测锚点。",
            "node_id": None,
            "important": False,
        },
        {
            "id": "duplicate",
            "question": "Counter-Edit 的含义是什么？",
            "answer": "它仍然指任务相关、与完成目标冲突的局部用户代码修改；这是对 Q1 的近义复述。",
            "node_id": "term.1",
        },
    ]
    qa_results: list[dict[str, Any]] = []
    for item in questions:
        before_study = read_json(project / "study-state.json")
        before_tutor_summary = state_summary(project / "tutor-state.json")
        node_id = item.get("node_id")
        before_status = (before_study.get("nodes", {}).get(node_id, {}) or {}).get("status") if node_id else None
        record = {
            "node_id": node_id,
            "kind": "user_question",
            "question": item["question"],
            "answer": item["answer"],
            "title": item["question"],
            "summary": item["answer"][:160],
            "body": item["answer"],
            "important": item.get("important", True),
            "map_visible": item.get("important", True),
            "importance": "high" if item.get("important", True) else "medium",
        }
        result = invoke_bridge(bridge, map_root, project, [record], "incremental_qa")
        subprocess.run([sys.executable, str(map_root / "runtime" / "render_paper_map.py"), "--project", str(project)], check=True)
        after_study = read_json(project / "study-state.json")
        after_status = (after_study.get("nodes", {}).get(node_id, {}) or {}).get("status") if node_id else None
        qa_results.append(
            {
                "id": item["id"],
                "question": item["question"],
                "resolved_node": node_id,
                "tutor_state_before": before_tutor_summary,
                "tutor_state_after": state_summary(project / "tutor-state.json"),
                "study_before": before_status,
                "study_after": after_status,
                "receipt": result.get("receipt"),
                "status": result.get("status"),
                "items_added": result.get("items_added", 0),
                "items_updated": result.get("items_updated", 0),
                "items_deduped": result.get("items_deduped", 0),
                "unresolved_added": result.get("unresolved_added", 0),
                "unresolved_total": result.get("unresolved_total", 0),
                "study_state_transition": result.get("study_state"),
            }
        )

    # Project only after the five incremental turns so the final Deep artifact
    # includes the real Tutor State learning trail and unresolved question.
    write_depth_projections(output, scholar, project)
    after = factual_hashes(scholar, project)
    integrity = {"before": before, "after": after, "same": before == after}
    write_json(receipt_root / "factual-integrity-after.json", integrity)
    tutor = read_json(project / "tutor-state.json")
    study = read_json(project / "study-state.json")
    report = {
        "paper": "SWE-Touch: Benchmarking Coding Agents When Users Touch the Code",
        "paper_sha256": before["pdf"],
        "full_analysis": {
            "records_in_memory": len(full_records),
            "bridge_result": full_result,
            "receipt": full_result.get("receipt"),
        },
        "qa": qa_results,
        "tutor_state": {"schema_version": tutor.get("schema_version"), "nodes": len(tutor.get("nodes", {})), "map_items": sum(len(n.get("map_items", [])) for n in tutor.get("nodes", {}).values()), "unresolved_items": len(tutor.get("unresolved_items", []))},
        "study_state": {"schema_version": study.get("schema_version"), "learning_nodes": sum(1 for n in study.get("nodes", {}).values() if n.get("status") == "learning")},
        "factual_integrity": integrity,
        "no_records_json_created": not (project / "records.json").exists(),
    }
    write_json(receipt_root / "qa-report.json", report)
    write_json(receipt_root / "observability-report.json", {"full_analysis": full_result.get("receipt"), "turns": [entry.get("receipt") for entry in qa_results], "entries": qa_results})
    if not integrity["same"]:
        raise SystemExit("factual layer hash changed during Tutor sync")
    if not report["no_records_json_created"]:
        raise SystemExit("forbidden manual records.json exists")
    if tutor.get("schema_version") != "1.1" or report["tutor_state"]["map_items"] <= 0:
        raise SystemExit("Full Analysis did not create valid Tutor items")
    if not any(entry["id"] == "Q5" and entry["unresolved_added"] == 1 for entry in qa_results):
        raise SystemExit("ambiguous Q5 was not recorded as unresolved")
    if not any(entry["id"] == "duplicate" and entry["items_deduped"] >= 1 for entry in qa_results):
        raise SystemExit("near-duplicate question was not observed as deduped")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
