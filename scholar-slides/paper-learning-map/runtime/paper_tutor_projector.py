"""Project structured Paper Learning Map data into compact or deep tutoring Markdown.

The projector is deliberately downstream-only.  It reads the factual map, the
Tutor State, and the source-bound reading view/digest; it never parses an
existing Markdown file and it refuses to project an unverified source.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from formula_projection import (
    build_formula_index,
    formula_index_digest,
    validate_formula_index_binding,
    write_formula_index,
)
from katex_bundle import load_katex_assets


NOT_VERIFIABLE = "Not verifiable from available evidence."


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def first_nonempty(*values: Any, default: str = NOT_VERIFIABLE) -> str:
    for value in values:
        text = clean(value)
        if text:
            return text
    return default


def refs_text(refs: Iterable[str]) -> str:
    values = [clean(ref) for ref in refs if clean(ref)]
    return "; ".join(f"`{value}`" for value in dict.fromkeys(values)) or NOT_VERIFIABLE


def claim_label(claim_type: str | None) -> str:
    return {
        "paper_fact": "Paper Fact",
        "explanation": "Tutor Explanation",
        "analysis": "Tutor Analysis",
    }.get(claim_type or "", "Tutor Explanation")


def evidence_lookup(digest: dict[str, Any], ref: str) -> dict[str, Any] | None:
    """Resolve the small evidence references emitted by Scholar-Slides."""
    if not ref.startswith("digest.json#/"):
        return None
    value: Any = digest
    for part in ref.split("#/", 1)[1].split("/"):
        if isinstance(value, list):
            try:
                value = value[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value if isinstance(value, dict) else {"value": value}


def evidence_location(refs: list[str], digest: dict[str, Any]) -> tuple[str, str, str, str]:
    page = "Not specified"
    section = "Not specified"
    figure_table = "Not specified"
    evidence_id = "; ".join(refs) if refs else NOT_VERIFIABLE
    for ref in refs:
        match = re.search(r"p\.?\s*([0-9]+(?:[-–][0-9]+)?)", ref, re.I)
        if match:
            page = match.group(1)
        if "," in ref and not ref.startswith("digest.json#/"):
            section = ref.split(",", 1)[1].strip()
        item = evidence_lookup(digest, ref)
        if item:
            if item.get("page") is not None:
                page = clean(item.get("page"))
            section = first_nonempty(item.get("section"), section, default="Not specified")
            figure_table = first_nonempty(item.get("label"), figure_table, default="Not specified")
            evidence_id = first_nonempty(item.get("id"), ref)
    return page, section, figure_table, evidence_id


class Projection:
    def __init__(
        self,
        paper_map: dict[str, Any],
        tutor_state: dict[str, Any],
        reading_view: dict[str, Any],
        digest: dict[str, Any],
        formula_index: dict[str, Any] | None = None,
        sync_receipts: list[dict[str, Any]] | None = None,
    ):
        self.paper_map = paper_map
        self.tutor_state = tutor_state
        self.view = reading_view
        self.digest = digest
        self.sync_receipts = list(sync_receipts or [])
        self.nodes = {node.get("id"): node for node in paper_map.get("nodes", []) if node.get("id")}
        self.state_nodes = tutor_state.get("nodes", {}) or {}
        self.view_nodes: dict[str, dict[str, Any]] = {}
        for key, value in (reading_view.get("overview") or {}).items():
            self.view_nodes[f"overview.{key}"] = value
        for index, value in enumerate(reading_view.get("mechanism_steps") or [], 1):
            self.view_nodes[f"method.step_{index}"] = value
        for index, value in enumerate(reading_view.get("decisive_evidence") or [], 1):
            self.view_nodes[f"evidence.block_{index}"] = value
        for index, value in enumerate(reading_view.get("terms") or [], 1):
            self.view_nodes[f"term.{index}"] = value
        for index, value in enumerate(reading_view.get("takeaways") or [], 1):
            self.view_nodes[f"takeaway.{index}"] = value

        source = paper_map.get("source") or {}
        if source.get("mode") != "integrated" or source.get("verification_level") != "scholar_slides_validated":
            raise ValueError(
                "Paper-Tutor projection requires source.mode=integrated and "
                "verification_level=scholar_slides_validated"
            )
        self.formula_index = formula_index or build_formula_index(paper_map, tutor_state, reading_view, digest)
        validate_formula_index_binding(self.formula_index, paper_map)
        self.formulas = {formula.get("id"): formula for formula in self.formula_index.get("formulas", []) if formula.get("id")}

    @property
    def title(self) -> str:
        return first_nonempty(
            (self.paper_map.get("paper_identity") or {}).get("title"),
            self.view.get("paper_identity", {}).get("title"),
            self.digest.get("title"),
        )

    @property
    def paper_type(self) -> str:
        value = self.paper_map.get("paper_type")
        if isinstance(value, dict):
            value = value.get("kind")
        return clean(value).lower() or "general"

    def node(self, node_id: str) -> dict[str, Any]:
        return self.nodes.get(node_id, {})

    def view_node(self, node_id: str) -> dict[str, Any]:
        value = self.view_nodes.get(node_id, {})
        return value if isinstance(value, dict) else {"content": value}

    def state_items(self, node_id: str) -> list[dict[str, Any]]:
        return [item for item in (self.state_nodes.get(node_id, {}) or {}).get("map_items", []) if isinstance(item, dict)]

    def node_refs(self, node_id: str) -> list[str]:
        node = self.node(node_id)
        view = self.view_node(node_id)
        refs = list(node.get("evidence_refs") or [])
        refs.extend(view.get("evidence_refs") or [])
        return list(dict.fromkeys(clean(ref) for ref in refs if clean(ref)))

    def node_content(self, node_id: str) -> str:
        node = self.node(node_id)
        view = self.view_node(node_id)
        return first_nonempty(
            view.get("content"),
            node.get("paper_fact", {}).get("statement") if isinstance(node.get("paper_fact"), dict) else None,
            node.get("summary"),
        )

    @staticmethod
    def _anchor_slug(value: str) -> str:
        """Stable URL fragment for a node/formula (no random IDs)."""

        return re.sub(r"[^a-zA-Z0-9-]+", "-", clean(value).replace("_", "-")).strip("-").lower()

    def deep_section_id(self, node_id: str, section_suffix: str | None = None) -> str:
        suffix = f".{section_suffix}" if section_suffix else ""
        return f"deep.section.{clean(node_id)}{suffix}"

    def deep_anchor_id(self, node_id: str, formula_id: str | None = None) -> str:
        base = formula_id or node_id
        return f"node-{self._anchor_slug(base)}"

    def map_href(self, node_id: str, formula_id: str | None = None) -> str:
        """Return a single-fragment Learning Map target.

        Formula targets use ``#formula=...`` directly; appending a second
        hash to a node URL would make the browser ignore the formula target.
        """

        fragment = f"formula={clean(formula_id)}" if formula_id else f"node={clean(node_id)}"
        return f"paper-learning-map.html#{fragment}"

    def deep_href(self, node_id: str, formula_id: str | None = None) -> str:
        fragment = f"formula={clean(formula_id)}" if formula_id else f"node-{self._anchor_slug(node_id)}"
        return f"paper-tutor-deep-v2.html#{fragment}"

    def markdown_nav(self, node_id: str, *, formula_id: str | None = None) -> list[str]:
        """Emit auditable navigation metadata alongside every deep block."""

        section_id = self.deep_section_id(node_id, formula_id.split("formula.", 1)[-1] if formula_id else None)
        target = formula_id or node_id
        return [
            f"<!-- section_id={section_id} anchor_node_id={node_id} -->",
            f"[View in Learning Map]({self.map_href(node_id)}) · `anchor_node_id={node_id}`" if not formula_id else f"[View formula in Learning Map]({self.map_href(node_id, formula_id)}) · `anchor_node_id={node_id}`",
        ]

    def state_field(self, node_id: str, field: str) -> list[str]:
        state = self.state_nodes.get(node_id, {}) or {}
        values: list[str] = []
        if field == "common_misunderstandings":
            values.extend(clean(value) for value in state.get(field) or [])
        else:
            value = clean(state.get(field))
            if value:
                values.append(value)
        return [value for value in values if value]

    def item_groups(self, node_id: str) -> dict[str, list[dict[str, Any]]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in self.state_items(node_id):
            groups[clean(item.get("kind"))].append(item)
        return groups

    def item_texts(self, node_id: str, kind: str) -> list[str]:
        return [clean(item.get("body") or item.get("summary")) for item in self.item_groups(node_id).get(kind, []) if clean(item.get("body") or item.get("summary"))]

    def all_items(self) -> list[tuple[str, dict[str, Any]]]:
        return [(node_id, item) for node_id in self.state_nodes for item in self.state_items(node_id)]

    def status_line(self, depth: str) -> str:
        return f"来源：Scholar-Slides integrated；CKPT-1 scholar_slides_validated；讲解深度：{depth}；Learning Map: {self.sync_status()}"

    def sync_status(self) -> str:
        if not self.sync_receipts:
            return "not synced"
        latest = self.sync_receipts[-1]
        if latest.get("status") == "failed":
            return "sync failed"
        if latest.get("status") == "skipped":
            return "not synced"
        if int(latest.get("unresolved_total", 0) or 0) > 0 or int(latest.get("unresolved_added", 0) or 0) > 0:
            return "unresolved"
        return "synced"

    def status_block(self, depth: str) -> str:
        source = self.paper_map.get("source") or {}
        return "\n".join([
            "## 来源与验证状态",
            "- Mode: Integrated",
            f"- Paper identity：{self.title}；source PDF SHA-256：{first_nonempty((self.paper_map.get('paper_identity') or {}).get('source_pdf_sha256'))}",
            "- Analysis source：Scholar-Slides-backed Paper-Tutor analysis。",
            "- Evidence source：approved evidence, quantitative, figure/table, and CKPT-1 artifacts。",
            f"- Verification：Scholar-Slides CKPT-1 {first_nonempty(source.get('verification_level'))}；本状态来自 user-authorized Codex review，不等同于自然人签署。",
            f"- Paper map：source.mode={first_nonempty(source.get('mode'))}；verification_level={first_nonempty(source.get('verification_level'))}。",
            "- Tutor records are downstream only (source_layer=tutor)；本投影不回写 Scholar-Slides factual layer。",
            f"- Depth: {depth}",
            f"- Learning Map: {self.sync_status()} (receipt-driven; no receipt is treated as not synced).",
        ])

    def paper_fact_block(self, node_id: str) -> str:
        node = self.node(node_id)
        content = self.node_content(node_id)
        label = claim_label(node.get("claim_type"))
        return f"#### Paper Fact\n{label}：{content}\n\n证据：{refs_text(self.node_refs(node_id))}"

    def teaching_block(self, node_id: str, heading: str | None = None) -> str:
        title = heading or first_nonempty(self.node(node_id).get("title"), self.view_node(node_id).get("title"), node_id)
        lines = [*self.markdown_nav(node_id), f"### {title}", self.paper_fact_block(node_id)]
        labels = {
            "tutor_explanation": "Tutor Explanation",
            "mathematical_meaning": "Mathematical Meaning",
            "intuition": "Intuition",
            "necessity": "Necessity",
            "prerequisite": "Prerequisite",
            "example": "Example",
            "analogy": "Analogy",
            "misconception": "Common Misunderstanding",
            "reader_analysis": "Tutor Analysis",
            "comprehension_check": "Comprehension Check",
            "verification_question": "Verification Question",
        }
        groups = self.item_groups(node_id)
        for kind, label in labels.items():
            for item in groups.get(kind, []):
                body = first_nonempty(item.get("body"), item.get("summary"))
                lines.extend([f"#### {label}", body])
        for field, label in (
            ("mathematical_meaning", "Mathematical Meaning"),
            ("intuition", "Intuition"),
            ("necessity", "Necessity"),
            ("example", "Example"),
            ("analogy", "Analogy"),
        ):
            for body in self.state_field(node_id, field):
                if body not in [clean(item.get("body")) for item in groups.get(field, [])]:
                    lines.extend([f"#### {label}", body])
        misunderstandings = self.state_field(node_id, "common_misunderstandings")
        for body in misunderstandings:
            if body not in [clean(item.get("body")) for item in groups.get("misconception", [])]:
                lines.extend(["#### Common Misunderstanding", body])
        questions = [item for item in groups.get("user_question", [])]
        for question in (self.state_nodes.get(node_id, {}) or {}).get("questions", []) or []:
            if not any(clean(question) == clean(item.get("title")) for item in questions):
                questions.append({"title": question, "body": NOT_VERIFIABLE})
        for item in questions:
            lines.extend([
                "#### 你问过的问题",
                f"Q：{first_nonempty(item.get('title'), item.get('question'))}",
                f"A：{first_nonempty(item.get('body'), item.get('summary'))}",
            ])
        return "\n\n".join(lines)

    def state_notes(self, node_id: str) -> str:
        """Keep experiment-specific Tutor State context without repeating Paper Facts."""
        labels = {
            "tutor_explanation": "Tutor Explanation",
            "mathematical_meaning": "Mathematical Meaning",
            "intuition": "Intuition",
            "necessity": "Necessity",
            "prerequisite": "Prerequisite",
            "example": "Example",
            "analogy": "Analogy",
            "misconception": "Common Misunderstanding",
            "reader_analysis": "Tutor Analysis",
            "comprehension_check": "Comprehension Check",
            "verification_question": "Verification Question",
        }
        lines = ["#### Tutor State Notes"]
        for item in self.state_items(node_id):
            kind = clean(item.get("kind"))
            body = first_nonempty(item.get("body"), item.get("summary"))
            if kind == "user_question":
                lines.append(f"- 你问过的问题：Q：{first_nonempty(item.get('title'))}；A：{body}")
            else:
                lines.append(f"- {labels.get(kind, kind)}：{body}")
        for unresolved in self.state_field(node_id, "common_misunderstandings"):
            lines.append(f"- Common Misunderstanding：{unresolved}")
        return "\n".join(lines)

    def formula_block(self, name: str, original: str, symbols: str, meaning: str, intuition: str, necessity: str, example: str, misunderstanding: str, refs: list[str]) -> str:
        """Legacy formatter retained for callers outside the RC2 projector."""
        return "\n".join([
            f"### Formula: {name}",
            "",
            "#### Original Formula",
            original,
            "",
            "#### Symbols",
            symbols,
            "",
            "#### Mathematical Meaning",
            meaning,
            "",
            "#### Step-by-step",
            "先计算候选集合或验证条件，再把结果作为答案/冲突判定的约束；具体步骤以论文给出的任务协议为准。",
            "",
            "#### Intuition",
            intuition,
            "",
            "#### Necessity",
            necessity,
            "",
            "#### Example",
            example,
            "",
            "#### Misunderstanding",
            misunderstanding,
            "",
            "#### Evidence",
            refs_text(refs),
        ])

    def formula_block_for_id(self, formula_id: str) -> str:
        """Render a Formula Block exclusively from the structured formula IR."""
        formula = self.formulas.get(formula_id)
        if not formula:
            return self.formula_block(
                formula_id,
                NOT_VERIFIABLE,
                NOT_VERIFIABLE,
                NOT_VERIFIABLE,
                NOT_VERIFIABLE,
                NOT_VERIFIABLE,
                NOT_VERIFIABLE,
                NOT_VERIFIABLE,
                [],
            )
        paper = formula.get("paper_formula") or {}
        derivation = formula.get("tutor_derivation") or {}
        example_layer = formula.get("tutor_example") or {}
        latex = clean(paper.get("latex")) or NOT_VERIFIABLE
        label = clean(formula.get("equation_label"))
        original = f"{label}:\n$$\n{latex}\n$$" if label else f"$$\n{latex}\n$$"
        symbols = "; ".join(
            f"{clean(symbol.get('symbol'))}：{clean(symbol.get('meaning'))}"
            for symbol in formula.get("symbols", [])
            if isinstance(symbol, dict)
        ) or NOT_VERIFIABLE
        derivation_text = clean(derivation.get("text"))
        derivation_latex = clean(derivation.get("latex"))
        step = derivation_text or "No source-bound Tutor derivation was recorded for this formula."
        if derivation_latex:
            step = f"{step}\n\nTutor derivation（source_layer=tutor）：\n$$\n{derivation_latex}\n$$"
        example = clean(formula.get("example")) or clean(example_layer.get("text")) or "No source-bound Tutor example was recorded for this formula."
        example_latex = clean(example_layer.get("latex"))
        if example_latex:
            example = f"{example}\n\nTutor example（source_layer=tutor）：\n$$\n{example_latex}\n$$"
        anchor_node = clean(formula.get("anchor_node_id"))
        anchor_title = first_nonempty(self.node(anchor_node).get("title"), anchor_node)
        role = f"This formula is anchored to **{anchor_title}** in the source-bound learning map. {first_nonempty(self.node_content(anchor_node), default='No additional source-bound role was recorded.') }"
        return "\n".join([
            *self.markdown_nav(clean(formula.get("anchor_node_id")), formula_id=formula_id),
            f"### Formula: {clean(formula.get('title')) or formula_id}",
            "",
            "#### Original Formula",
            "[Paper Formula]",
            original,
            "",
            "#### Symbols",
            symbols if symbols != NOT_VERIFIABLE else "No source-bound symbol glossary was recorded for this formula.",
            "",
            "#### Mathematical Meaning",
            clean(formula.get("mathematical_meaning")) or "No source-bound mathematical interpretation was recorded for this formula.",
            "",
            "#### Step-by-step",
            "[Tutor Explanation / Derivation]",
            step,
            "",
            "#### Intuition",
            clean(formula.get("intuition")) or "No source-bound Tutor intuition was recorded for this formula.",
            "",
            "#### Necessity",
            clean(formula.get("necessity")) or "No source-bound necessity explanation was recorded for this formula.",
            "",
            "#### Role in This Paper",
            role,
            "",
            "#### Example",
            "[Tutor Example]",
            example,
            "",
            "#### Misunderstanding",
            clean(formula.get("misunderstanding")) or "No source-bound misconception note was recorded for this formula.",
            "",
            "#### Evidence",
            refs_text((formula.get("evidence") or {}).get("evidence_refs") or paper.get("evidence_refs") or []),
        ])

    def experiment_block(self, evidence: dict[str, Any], index: int) -> str:
        question = first_nonempty(evidence.get("question"), f"实验 {index} 要回答什么？")
        comparison = first_nonempty(evidence.get("comparison"))
        metric = first_nonempty(evidence.get("metric"))
        result = first_nonempty(evidence.get("result"))
        supports = first_nonempty(evidence.get("can_support"))
        boundary = first_nonempty(evidence.get("cannot_support"))
        refs = evidence.get("evidence_refs") or []
        if not refs:
            refs = self.node_refs(f"evidence.block_{index}")
        node_id = f"evidence.block_{index}"
        return "\n".join([
            *self.markdown_nav(node_id),
            f"### Experiment: {question}",
            "",
            "#### Question",
            question,
            "",
            "#### Setup",
            "在论文给出的任务、数据和运行协议下进行成对比较；完整设置见证据定位。",
            "",
            "#### Comparison",
            comparison,
            "",
            "#### Metric",
            metric,
            "",
            "#### Result",
            result,
            "",
            "#### Meaning",
            supports,
            "",
            "#### How to Read",
            f"先确认比较条件和指标分母，再把该数值解释为受测设置中的差异：{result}",
            "",
            "#### What It Supports",
            supports,
            "",
            "#### What It Does NOT Prove",
            boundary,
            "",
            "#### Boundary",
            boundary,
            "",
            "#### Tutor Analysis",
            f"该实验把一个局部问题连接到论文主张，但不能脱离其样本、预算、基线和验证器外推。证据：{refs_text(refs)}",
        ])

    def benchmark_card(self) -> list[tuple[str, str]]:
        if "swe-touch" in self.title.lower() or "swe-touch" in self.title.replace(" ", "-").lower():
            return [
                ("Motivation", "既有仓库级 benchmark 多为独立修复或 message-only 交互，缺少用户直接修改可执行共享代码后的适应性评测。"),
                ("Capability", "状态变化检测、冲突协调和受影响行为的重新验证；不等同于一般自治编码能力。"),
                ("Task", "SWE-bench Verified 仓库修复；补充 SWE-Bench Pro 与 DeepSWE 长时程修复。"),
                ("Input / Output", "输入为 issue、初始仓库、verifier、用户编辑和上下文消息；输出为继续修复后的仓库状态与轨迹。"),
                ("Dataset", "主评测为带种子的 200 个 SWE-bench Verified 任务；SWE-Bench Pro 与 DeepSWE 各 25 个长时程任务。"),
                ("Environment", "Mini-SWE-Agent shell；主实验 100-step、每条件 3 次，重叠区域触发，默认最多 K=3；长时程 500-step。"),
                ("Models", "Claude Opus 4.8、GPT 5.5、GLM 5.1、MiniMax M2.7/M2.5、Qwen 3.7 Max、Qwen3-Coder-480B-A35B、Kimi K2.6、DeepSeek V4 Pro。"),
                ("Agent", "9 个 coding agent；区域挖掘使用 GPT 5.5、GLM 5.1、MiniMax M2.7 的完整轨迹，评测比较 Vanilla 与 Counter-Edit。"),
                ("Baseline", "同任务同模型的 Vanilla；Co-Edit 用来区分一般外部改动与任务冲突。"),
                ("Metric", "Resolve rate 要求完整 verifier 通过；同时报告 retention、steps、tokens 和 Counter-Edit−Vanilla 差值。"),
                ("Result", "SWE-bench Verified 平均 resolve rate 下降 7.7 个百分点，模型级损失 1.3–16.5 个百分点。"),
                ("Scaling", "K=1/3/5 不是统一剂量反应；更长时程增加调用但不稳定恢复 resolve rate。"),
                ("Failure", "失败审计中 63.3% 保留冲突、13.9% 错误替换、11.6% 协调不完整、5.5% off-target；还存在验证不足。"),
                ("Validity", "成对 Vanilla/Counter-Edit、统一 verifier 和 Co-Edit 支持内部公平；模拟的任务相关编辑限制外部真实性，污染不能由本实验单独证明。"),
                ("Conclusion", "在受测任务、模型、预算和触发协议下，自治 resolve rate 不能替代共享工作空间鲁棒性。"),
                ("Research Gap", "如何把变化检测、冲突协调、目标行为验证和更真实的双向用户模拟分别控制并改善失败？这是 Tutor Analysis。"),
            ]
        overview = self.view.get("overview") or {}
        mechanism = self.view.get("mechanism_steps") or []
        evidence = self.view.get("decisive_evidence") or []
        step = mechanism[0] if mechanism else {}
        finding = evidence[0] if evidence else {}
        return [
            ("Motivation", first_nonempty(overview.get("gap", {}).get("content"))),
            ("Capability", first_nonempty(overview.get("insight", {}).get("content"))),
            ("Task", first_nonempty(step.get("purpose"))),
            ("Input / Output", f"Input: {first_nonempty(step.get('input'))}; Output: {first_nonempty(step.get('output'))}"),
            ("Dataset", first_nonempty(finding.get("result"))),
            ("Environment", first_nonempty(step.get("input"))),
            ("Models", NOT_VERIFIABLE),
            ("Agent", NOT_VERIFIABLE),
            ("Baseline", first_nonempty(finding.get("comparison"))),
            ("Metric", first_nonempty(finding.get("metric"))),
            ("Result", first_nonempty(finding.get("result"))),
            ("Scaling", NOT_VERIFIABLE),
            ("Failure", first_nonempty(overview.get("boundary", {}).get("content"))),
            ("Validity", first_nonempty(overview.get("boundary", {}).get("content"))),
            ("Conclusion", first_nonempty(overview.get("findings", {}).get("content"))),
            ("Research Gap", first_nonempty(overview.get("gap", {}).get("content"))),
        ]

    def compact(self) -> str:
        overview = self.view.get("overview") or {}
        lines = [f"# {self.title}", "", self.status_line("compact"), "", "## 30 秒主线"]
        lines.append(" ".join(first_nonempty((overview.get(key) or {}).get("content")) for key in ("problem", "gap", "approach", "findings", "boundary")))
        if self.paper_type == "benchmark":
            lines.extend(["", "## Benchmark Card"])
            lines.append("| Field | Answer |\n|---|---|")
            lines.extend(f"| {field} | {answer} |" for field, answer in self.benchmark_card())
        else:
            lines.extend(["", "## Method Summary"])
            for step in self.view.get("mechanism_steps") or []:
                lines.append(f"- **{first_nonempty(step.get('title'))}**：{first_nonempty(step.get('purpose'))} Input: {first_nonempty(step.get('input'))}; Output: {first_nonempty(step.get('output'))}.")
        lines.extend(["", "## Main Results"])
        for evidence in self.view.get("decisive_evidence") or []:
            lines.append(f"- {first_nonempty(evidence.get('result'))}（能支持：{first_nonempty(evidence.get('can_support'))}；边界：{first_nonempty(evidence.get('cannot_support'))}）")
        lines.extend(["", "## Limitations", first_nonempty((overview.get("boundary") or {}).get("content"))])
        lines.extend(["", self.evidence_appendix(), "", self.status_block("compact")])
        lines.extend(["", "## Verification Questions"])
        for node_id, item in self.all_items():
            if item.get("kind") in {"user_question", "verification_question"}:
                lines.append(f"- {first_nonempty(item.get('title'))}（节点：{node_id}）")
        return "\n".join(lines).rstrip() + "\n"

    def benchmark_deep(self) -> list[str]:
        card = self.benchmark_card()
        lines = ["## Benchmark Card（Overview Index）", "", "| 问题你必须回答 | 回答 |", "| --- | --- |"]
        lines.extend(f"| **{field}** | {answer} |" for field, answer in card)
        lines.extend(["", "## Task → Input / Output Map", "", "| Task | Capability | Input / Observation | Output / Action | Success criterion |", "| --- | --- | --- | --- | --- |"])
        if "swe-touch" in self.title.lower() or "swe-touch" in self.title.replace(" ", "-").lower():
            lines.extend([
                "| SWE-bench Verified + Vanilla | 自治仓库修复 | issue、仓库、测试、shell | 读/改/测并提交最终仓库 | 完整 verifier 通过 |",
                "| SWE-bench Verified + Counter-Edit | 共享状态冲突协调 | 同类任务 + 局部 Counter-Edit + 上下文消息 | 检查当前代码、修复冲突、运行针对性测试 | verifier 通过且 pass-to-pass 不回退 |",
                "| SWE-Bench Pro / DeepSWE | 长时程状态适应 | 更大仓库、更长轨迹、按协议注入 | 500-step 预算内继续修复 | 同一 verifier 条件下 resolve |",
            ])
        else:
            for index, step in enumerate(self.view.get("mechanism_steps") or [], 1):
                lines.append(f"| Task {index}: {first_nonempty(step.get('title'))} | {first_nonempty(step.get('purpose'))} | {first_nonempty(step.get('input'))} | {first_nonempty(step.get('output'))} | 论文给出的验证条件 |")
        lines.extend(["", "## Benchmark 一句公式"])
        lines.append("**作者认为现有 Benchmark 无法评估用户直接修改共享可执行代码后代理的状态感知与冲突协调，因此构建了包含 200 个 SWE-bench Verified 任务及长时程任务的数据和 Counter-Edit 任务，使用 resolve rate、retention、steps 与 tokens 指标评估 9 个 coding 模型/Agent，最终发现当前模型主要在检测外部变化、协调冲突和重新验证受影响行为上存在明显不足。**" if "swe-touch" in self.title.lower() else "**作者把问题、任务、数据、指标和结论边界压缩为一个可复述的 benchmark 论证链；具体字段见上方索引和下方教学模块。**")
        return lines

    def source_bound_protocol_block(self) -> str:
        """Render protocol fields from the evidence actually present in the reading view.

        Some benchmark reading views intentionally contain only decisive evidence blocks.
        The projector must not invent an ``evidence.block_3`` protocol node just because
        an older template expected one.
        """
        evidence = (self.view.get("decisive_evidence") or [{}])[0]
        refs = evidence.get("evidence_refs") or self.node_refs("evidence.block_1")
        return "\n".join([
            "### Evaluation Protocol",
            "#### Setup",
            first_nonempty(evidence.get("comparison")),
            "",
            "#### Metric",
            first_nonempty(evidence.get("metric")),
            "",
            "#### Source Evidence",
            first_nonempty(evidence.get("result")),
            "",
            "#### Evidence",
            refs_text(refs),
        ])

    def source_bound_failure_block(self) -> str:
        """Summarize observed outcomes and their boundaries without a fake failure node."""
        lines = ["### Observed Failure Boundary"]
        evidence_blocks = self.view.get("decisive_evidence") or []
        for index, evidence in enumerate(evidence_blocks, 1):
            refs = evidence.get("evidence_refs") or self.node_refs(f"evidence.block_{index}")
            lines.extend([
                f"#### Evidence {index}: {first_nonempty(evidence.get('question'))}",
                f"Result: {first_nonempty(evidence.get('result'))}",
                f"What it supports: {first_nonempty(evidence.get('can_support'))}",
                f"Boundary: {first_nonempty(evidence.get('cannot_support'))}",
                f"Evidence: {refs_text(refs)}",
                "",
            ])
        overview = self.view.get("overview") or {}
        boundary = overview.get("boundary") or {}
        lines.extend([
            "#### Overall Boundary",
            first_nonempty(boundary.get("content")),
            f"Evidence: {refs_text(boundary.get('evidence_refs') or self.node_refs('overview.boundary'))}",
        ])
        return "\n".join(lines).rstrip()

    def swe_counter_edit(self) -> list[str]:
        if "swe-touch" not in self.title.lower():
            return []
        lines = ["## Counter-Edit Deep Dive", "", "### What it is", "Counter-Edit 是靠近任务关键代码、看似合理但与任务完成冲突的局部用户代码修改；它不是随机噪声，也不是能够独立解题的参考 patch。", "", "### Why it is needed", "它把‘共享状态发生变化’与‘变化和任务目标冲突’同时固定下来，使失败可以和 Vanilla 成对比较。", "", "### 与普通代码修改的区别", "普通代码修改可能正确、无关或改变需求；Counter-Edit 刻意保持局部合理性，同时通过 verifier 条件确认其与任务完成冲突。", "", "### How it is generated", "先从多条代理轨迹的 Read/Edit 覆盖中挖出关键区域，再由 User Patch Generator 生成局部编辑。"]
        lines.extend(["", self.teaching_block("method.step_1", "Critical Region Mining"), "", self.teaching_block("method.step_2", "Counter-Edit Generation")])
        lines.extend(["", "### Three Validation Conditions", "VF(R−)=0 排除编辑单独解题；VF(R⋆)=1 确认参考修复有效；VF(R−⋆)=0 排除编辑与参考修复简单叠加即可通过。", "", self.formula_block_for_id("formula.method.step_2.counter_edit_validation"), "", self.teaching_block("method.step_3", "Injection Mechanism"), "", "### 它测什么能力", "它测变化检测、冲突协调和受影响行为的重新验证。它不测所有真实用户协作、需求变化或任意代码质量。"])
        return lines

    def method_deep(self) -> list[str]:
        overview = self.view.get("overview") or {}
        lines = ["## Problem & Setting", self.teaching_block("overview.problem", "Problem"), "", "## Research Gap", self.teaching_block("overview.gap", "Gap"), "", "## Core Insight", self.teaching_block("overview.insight", "Insight"), "", "## Overall Pipeline"]
        for index, step in enumerate(self.view.get("mechanism_steps") or [], 1):
            lines.append(f"{index}. **{first_nonempty(step.get('title'))}**：{first_nonempty(step.get('purpose'))} Input: {first_nonempty(step.get('input'))}; Output: {first_nonempty(step.get('output'))}; Necessity: {first_nonempty(step.get('necessity'))}。")
        lines.extend(["", "## Components"])
        for index in range(1, len(self.view.get("mechanism_steps") or []) + 1):
            lines.extend([self.teaching_block(f"method.step_{index}"), ""])
        lines.extend(["## Training Objective", first_nonempty((overview.get("approach") or {}).get("content")), "", "## Formula Blocks"])
        if "reasoning-table" in self.title.lower():
            lines.extend([
                self.formula_block_for_id("formula.method.step_3.position_reward"),
                "",
                self.formula_block_for_id("formula.method.step_3.final_reward"),
                "",
                "GRPO 的组内相对优势只在结构化证据明确支持的范围内解释；完整 clipped objective 不在当前 formula-index 中。",
            ])
        elif "swe-touch" in self.title.lower():
            lines.append(self.formula_block_for_id("formula.method.step_2.counter_edit_validation"))
        elif self.formulas:
            for formula_id in self.formulas:
                lines.extend([self.formula_block_for_id(formula_id), ""])
        else:
            lines.append("No source-bound formula candidates were available for this paper.")
        lines.extend(["", "## Experiments"])
        for index, evidence in enumerate(self.view.get("decisive_evidence") or [], 1):
            evidence = dict(evidence)
            evidence.setdefault("evidence_refs", self.node_refs(f"evidence.block_{index}"))
            lines.extend([self.experiment_block(evidence, index), self.state_notes(f"evidence.block_{index}"), ""])
        if "reasoning-table" in self.title.lower():
            lines.extend(["## Ablation"])
            lines.append(self.experiment_block({"question": "四种训练分支隔离了什么变量？", "comparison": "No-Reason SFT、Reason-SFT、RL-zero、Reason-SFT+RL", "metric": "tableQA AVG", "result": "49.80、56.72、60.12、62.62；组合训练最高。", "can_support": "教师轨迹冷启动与 RL 探索在受测设置下具有互补信号。", "cannot_support": "不能把全部提升归因给 GRPO 或任一奖励组件。", "evidence_refs": self.node_refs("evidence.block_1")}, 1))
            lines.extend(["", self.teaching_block("evidence.block_2", "Reward Ablation")])
        else:
            # A generic method paper has no license for a synthetic ablation section.
            # Only source evidence explicitly labelled as an ablation may appear here.
            pass
        lines.extend(["", "## Key Terms and Learning Trace"])
        for node_id in [node_id for node_id in self.nodes if node_id.startswith("term.")]:
            lines.extend([self.teaching_block(node_id), ""])
        for node_id in ["overview.approach", "takeaway.1", "takeaway.2", "takeaway.3", "takeaway.4", "takeaway.5"]:
            if node_id in self.nodes:
                lines.extend([self.teaching_block(node_id), ""])
        lines.extend(["", "## Robustness"])
        if "reasoning-table" in self.title.lower():
            lines.append(self.teaching_block("evidence.block_3", "Generalization and Robustness"))
        elif any(token in json.dumps(self.view.get("mechanism_steps") or [], ensure_ascii=False).lower() for token in ("gaia", "transfer", "generalization")):
            lines[-1] = "## Transfer / Generalization"
            lines.append(self.teaching_block("method.step_3", "External Transfer"))
        else:
            lines.pop()
        lines.extend(["", "## Main Results"])
        lines.append(self.teaching_block("overview.findings", "Main Results"))
        lines.extend(["", "## Failure Analysis"])
        if "swe-touch" in self.title.lower():
            lines.extend(["### Failure taxonomy", "- **Retained conflict**：代理保留了仍与目标冲突的用户编辑。\n- **Incorrect replacement**：尝试反抗编辑但替换错误。\n- **Incomplete reconciliation**：只协调了一部分受影响行为。\n- **Off-target / insufficient verification**：修改偏离关键区域或没有充分验证。", "", self.teaching_block("evidence.block_4", "What Failure Rates Mean")])
        else:
            lines.append(self.source_bound_failure_block())
        lines.extend(["", "## Limitations & Boundary", self.teaching_block("overview.boundary", "Limitations"), "", "## Research Perspective", "### Reader Analysis"])
        for node_id, item in self.all_items():
            if item.get("kind") == "reader_analysis":
                lines.append(f"- {clean(item.get('body') or item.get('summary'))}（节点：{node_id}；Tutor Analysis）")
        lines.extend(["", "### Open Questions"])
        for unresolved in self.tutor_state.get("unresolved_items") or []:
            lines.append(f"- {first_nonempty(unresolved.get('title'))}：{first_nonempty(unresolved.get('body'))}（Open Question；{unresolved.get('reason', 'unresolved')}）")
        for node_id, item in self.all_items():
            if item.get("kind") in {"verification_question", "user_question"}:
                lines.append(f"- {first_nonempty(item.get('title'))}（节点：{node_id}）")
        lines.extend(["", "### Tutor-generated research direction", "把论文已观察到的检测、协调、验证或奖励差异拆成可控变量，使用同一数据、预算、基线和证据协议做配对复现实验；这是 Tutor Analysis，不是 Paper Fact。", "", "## Full Argument Chain"])
        chain = self.view.get("argument_chain") or []
        if chain:
            for index, entry in enumerate(chain):
                lines.append(f"{index + 1}. **{first_nonempty(entry.get('node'))}** — {first_nonempty(entry.get('relation'))}（{claim_label(entry.get('claim_type'))}；{refs_text(entry.get('evidence_refs') or [])}）")
        else:
            lines.extend(["Problem", "↓", "Gap", "↓", "Insight", "↓", "Method", "↓", "Evidence", "↓", "Boundary"])
        lines.extend(["", "## Verification Questions"])
        seen: set[str] = set()
        for node_id, item in self.all_items():
            if item.get("kind") not in {"user_question", "verification_question"}:
                continue
            question = first_nonempty(item.get("title"))
            if question in seen:
                continue
            seen.add(question)
            lines.append(f"- {question}（节点：{node_id}）")
        return lines

    def evidence_appendix(self) -> str:
        rows: list[str] = ["## Claim → Evidence Appendix", "", "| Claim | Source | Page | Section | Figure/Table | Evidence ID |", "| --- | --- | --- | --- | --- | --- |"]
        seen: set[tuple[str, str]] = set()
        for index, evidence in enumerate(self.view.get("decisive_evidence") or [], 1):
            refs = list(evidence.get("evidence_refs") or self.node_refs(f"evidence.block_{index}"))
            page, section, figure_table, evidence_id = evidence_location(refs, self.digest)
            claim = first_nonempty(evidence.get("result"), evidence.get("question"))
            key = (claim, evidence_id)
            if key in seen:
                continue
            seen.add(key)
            rows.append(f"| {claim} | Scholar-Slides reading view / source PDF | {page} | {section} | {figure_table} | {evidence_id} |")
        for node_id, node in self.nodes.items():
            fact = node.get("paper_fact")
            if not isinstance(fact, dict):
                continue
            refs = self.node_refs(node_id)
            if not refs:
                continue
            page, section, figure_table, evidence_id = evidence_location(refs, self.digest)
            claim = first_nonempty(fact.get("statement"), node.get("summary"))
            key = (claim, evidence_id)
            if key in seen:
                continue
            seen.add(key)
            rows.append(f"| {claim} | Scholar-Slides reading view / source PDF | {page} | {section} | {figure_table} | {evidence_id} |")
        return "\n".join(rows)

    def deep(self) -> str:
        overview = self.view.get("overview") or {}
        lines = [f"# {self.title}", "", self.status_line("deep"), "", "## 30 秒主线"]
        lines.append(" ".join(first_nonempty((overview.get(key) or {}).get("content")) for key in ("problem", "gap", "approach", "findings", "boundary")))
        if self.paper_type == "benchmark":
            lines.extend(["", *self.benchmark_deep(), "", *self.swe_counter_edit(), "", "## Problem & Motivation", self.teaching_block("overview.problem", "Problem"), "", "## Research Gap", self.teaching_block("overview.gap", "Gap"), "", "## Capability Under Test", self.teaching_block("overview.insight", "Insight"), "", "## Method / Benchmark Design"])
            lines.extend([self.teaching_block(f"method.step_{index}") for index in range(1, len(self.view.get("mechanism_steps") or []) + 1)])
            if "swe-touch" not in self.title.lower():
                lines.extend(["", "## Formula Blocks"])
                if self.formulas:
                    for formula_id in self.formulas:
                        lines.extend([self.formula_block_for_id(formula_id), ""])
                else:
                    lines.append("No source-bound formula candidates were available for this benchmark.")
            lines.extend(["", "## Experimental Setup", self.source_bound_protocol_block(), "", "## Experiments"])
            for index, evidence in enumerate(self.view.get("decisive_evidence") or [], 1):
                evidence = dict(evidence)
                evidence.setdefault("evidence_refs", self.node_refs(f"evidence.block_{index}"))
                lines.extend([self.experiment_block(evidence, index), self.teaching_block(f"evidence.block_{index}"), ""])
            lines.extend(["## Key Terms and Learning Trace"])
            for node_id in [node_id for node_id in self.nodes if node_id.startswith("term.")]:
                lines.extend([self.teaching_block(node_id), ""])
            for node_id in ["overview.approach", "takeaway.1", "takeaway.2", "takeaway.3", "takeaway.4", "takeaway.5"]:
                if node_id in self.nodes:
                    lines.extend([self.teaching_block(node_id), ""])
            lines.extend(["## Main Results", self.teaching_block("overview.findings", "Findings")])
            lines.extend(["", "## Scaling", "该 benchmark 的运行规模、重复次数和步数上限由来源证据给出；不要把这些设置外推为所有现实工作流的复杂度规律。", "", "## Failure Analysis", self.source_bound_failure_block(), "", "## Validity", "内部比较应结合来源给出的统一 harness、任务集合与评分口径理解；外部真实性仍受来源边界限制。", "", "## Limitations", self.teaching_block("overview.boundary", "Boundary"), "", "## Research Perspective", "### Reader Analysis", "阅读时应把平均分、严格成功率和 harness 比较分别解释；这是基于来源证据的阅读提示，不是额外实验结论。", "", "## Full Argument Chain"])
            for index, entry in enumerate(self.view.get("argument_chain") or [], 1):
                lines.append(f"{index}. **{first_nonempty(entry.get('node'))}** → {first_nonempty(entry.get('relation'))}（{claim_label(entry.get('claim_type'))}）")
            lines.extend(["", "## Verification Questions"])
            for node_id, item in self.all_items():
                if item.get("kind") in {"user_question", "verification_question"}:
                    lines.append(f"- {first_nonempty(item.get('title'))}（节点：{node_id}）")
        else:
            lines.extend(self.method_deep())
        lines.extend(["", self.evidence_appendix(), "", self.status_block("deep")])
        return "\n".join(lines).rstrip() + "\n"

    def _html_node(self, node_id: str, heading: str | None = None) -> str:
        """Render a teaching node from structured map/Tutor fields."""
        title = heading or first_nonempty(self.node(node_id).get("title"), node_id)
        node = self.node(node_id)
        body = self.node_content(node_id)
        anchor_id = self.deep_anchor_id(node_id)
        parts = [f"<article id=\"{html.escape(anchor_id, quote=True)}\" data-section-id=\"{html.escape(self.deep_section_id(node_id), quote=True)}\" data-anchor-node-id=\"{html.escape(node_id, quote=True)}\" class=\"teaching-node\"><h3>{html.escape(title)}</h3>"]
        parts.append(f"<nav class=\"deep-map-nav\"><a href=\"{html.escape(self.map_href(node_id), quote=True)}\">View in Learning Map</a> <code>anchor_node_id={html.escape(node_id)}</code></nav>")
        parts.append(f"<div class=\"claim paper-fact\"><strong>Paper Fact</strong><p>{html.escape(body)}</p></div>")
        refs = self.node_refs(node_id)
        parts.append(f"<p class=\"evidence-line\"><strong>Evidence</strong> {html.escape('; '.join(refs) or NOT_VERIFIABLE)}</p>")
        labels = {
            "tutor_explanation": "Tutor Explanation",
            "mathematical_meaning": "Mathematical Meaning",
            "intuition": "Intuition",
            "necessity": "Necessity",
            "prerequisite": "Prerequisite",
            "example": "Example",
            "analogy": "Analogy",
            "misconception": "Common Misunderstanding",
            "reader_analysis": "Tutor Analysis",
            "user_question": "User Question",
            "verification_question": "Verification Question",
        }
        for item in self.state_items(node_id):
            kind = clean(item.get("kind"))
            text = first_nonempty(item.get("body"), item.get("summary"))
            parts.append(f"<div class=\"claim tutor\"><strong>{html.escape(labels.get(kind, kind))}</strong><p>{html.escape(text)}</p></div>")
        parts.append("</article>")
        return "".join(parts)

    @staticmethod
    def _html_paragraphs(text: str) -> str:
        chunks = [chunk.strip() for chunk in str(text or "").split("\n") if chunk.strip()]
        return "".join(f"<p>{html.escape(chunk)}</p>" for chunk in chunks) or "<p class=\"muted\">Not available in the structured source.</p>"

    def _html_formula_layer(self, layer: dict[str, Any], formula_id: str, name: str) -> str:
        if not layer:
            return ""
        label = {"paper_formula": "[Paper Formula]", "tutor_derivation": "[Tutor Explanation]", "tutor_example": "[Tutor Example]"}.get(clean(layer.get("formula_kind")), "[Formula]")
        latex = clean(layer.get("latex"))
        text = clean(layer.get("text"))
        raw = ""
        rendered = ""
        if latex:
            render_id = f"formula-{formula_id.replace('.', '-')}-{name}"
            rendered = f"<div id=\"{html.escape(render_id)}\" class=\"formula-render\" data-tex=\"{html.escape(latex, quote=True)}\" data-display=\"{str(layer.get('display_mode', True)).lower()}\"></div>"
            raw = f"<details class=\"formula-source\"><summary>Show LaTeX</summary><pre class=\"raw-tex\">{html.escape(latex)}</pre><button type=\"button\" class=\"copy-tex\" data-copy-tex=\"{html.escape(latex, quote=True)}\">Copy LaTeX</button></details>"
        return f"<div class=\"formula-layer {html.escape(name)}\"><div class=\"formula-badge\">{html.escape(label)}</div>{rendered}{self._html_paragraphs(text) if text else ''}{raw}</div>"

    def _html_formula(self, formula: dict[str, Any]) -> str:
        paper = formula.get("paper_formula") or {}
        evidence = formula.get("evidence") or {}
        formula_id = clean(formula.get("id"))
        node_id = clean(formula.get("anchor_node_id"))
        anchor_id = self.deep_anchor_id(node_id, formula_id)
        symbols = "".join(
            f"<li><code>{html.escape(clean(item.get('symbol')))}</code> {html.escape(clean(item.get('meaning')))} <small>{html.escape(clean(item.get('source_layer')))}</small></li>"
            for item in formula.get("symbols", []) if isinstance(item, dict)
        ) or "<li class=\"muted\">Symbols not fully available in structured analysis.</li>"
        refs = "; ".join(evidence.get("evidence_refs") or paper.get("evidence_refs") or []) or NOT_VERIFIABLE
        equation = f" · {html.escape(clean(formula.get('equation_label')))}" if clean(formula.get("equation_label")) else ""
        return "".join([
            f"<section id=\"{html.escape(anchor_id, quote=True)}\" data-section-id=\"{html.escape(self.deep_section_id(node_id, formula_id.split('formula.', 1)[-1]), quote=True)}\" data-anchor-node-id=\"{html.escape(node_id, quote=True)}\" class=\"formula-block\" data-formula-id=\"{html.escape(formula_id, quote=True)}\"><h3>Formula: {html.escape(clean(formula.get('title')))}{equation}</h3>",
            f"<nav class=\"deep-map-nav\"><a href=\"{html.escape(self.map_href(node_id, formula_id), quote=True)}\">View formula in Learning Map</a> <code>anchor_node_id={html.escape(node_id)}</code></nav>",
            self._html_formula_layer(paper, formula_id, "paper-formula"),
            self._html_formula_layer(formula.get("tutor_derivation") or {}, formula_id, "tutor-derivation"),
            self._html_formula_layer(formula.get("tutor_example") or {}, formula_id, "tutor-example"),
            f"<h4>Symbols</h4><ul class=\"formula-symbols\">{symbols}</ul>",
            f"<h4>Mathematical Meaning</h4>{self._html_paragraphs(clean(formula.get('mathematical_meaning')) or 'No source-bound mathematical interpretation was recorded for this formula.')}",
            f"<h4>Intuition</h4>{self._html_paragraphs(clean(formula.get('intuition')) or 'No source-bound Tutor intuition was recorded for this formula.')}",
            f"<h4>Necessity</h4>{self._html_paragraphs(clean(formula.get('necessity')) or 'No source-bound necessity explanation was recorded for this formula.')}",
            f"<h4>Role in This Paper</h4>{self._html_paragraphs(f'This formula is anchored to {first_nonempty(self.node(clean(formula.get('anchor_node_id'))).get('title'), clean(formula.get('anchor_node_id')))} in the source-bound learning map. {first_nonempty(self.node_content(clean(formula.get('anchor_node_id'))), default='No additional source-bound role was recorded.')}')}",
            f"<h4>Example</h4>{self._html_paragraphs(clean(formula.get('example')) or clean((formula.get('tutor_example') or {}).get('text')) or 'No source-bound Tutor example was recorded for this formula.')}",
            f"<h4>Misunderstanding</h4>{self._html_paragraphs(clean(formula.get('misunderstanding')) or 'No source-bound misconception note was recorded for this formula.')}",
            f"<h4>Evidence</h4><p class=\"evidence-line\">{html.escape(refs)}</p>",
            f"<h4>Source Trace</h4><pre class=\"source-trace\">{html.escape(json.dumps(paper.get('source_trace') or [], ensure_ascii=False, indent=2))}</pre>",
            "</section>",
        ])

    def _html_section(self, section_id: str, heading: str, body: str, anchor_node_id: str | None = None) -> str:
        """Wrap a Deep section with a stable, inspectable navigation anchor."""

        anchor = anchor_node_id or ""
        # Wrapper sections get their own stable IDs; the nested node/article
        # carries the canonical ``node-*`` target used by deep links.
        dom_id = f"section-{self._anchor_slug(section_id)}"
        nav = (
            f"<nav class=\"deep-map-nav\"><a href=\"{html.escape(self.map_href(anchor_node_id), quote=True)}\">View in Learning Map</a> <code>anchor_node_id={html.escape(anchor_node_id)}</code></nav>"
            if anchor_node_id else ""
        )
        return f"<section id=\"{html.escape(dom_id, quote=True)}\" data-section-id=\"{html.escape(section_id, quote=True)}\"{(' data-anchor-node-id=\"' + html.escape(anchor, quote=True) + '\"') if anchor else ''}><h2>{html.escape(heading)}</h2>{nav}{body}</section>"

    def _deep_html_legacy(self) -> str:
        """Render the Deep companion directly from the structured projection."""
        version, katex_js, katex_css = load_katex_assets()
        overview = self.view.get("overview") or {}
        sections: list[str] = []
        mainline = " ".join(first_nonempty((overview.get(key) or {}).get("content")) for key in ("problem", "gap", "approach", "findings", "boundary"))
        sections.append(self._html_section("deep.section.mainline", "30 秒主线", self._html_paragraphs(mainline), "paper"))
        if self.paper_type == "benchmark":
            rows = "".join(f"<tr><th>{html.escape(field)}</th><td>{html.escape(answer)}</td></tr>" for field, answer in self.benchmark_card())
            sections.append(self._html_section("deep.section.benchmark-card", "Benchmark Card (Overview Index)", f"<table><tbody>{rows}</tbody></table>", "paper"))
            sections.append(self._html_section("deep.section.task-dataset-metric-protocol", "Task / Dataset / Metric / Protocol", self._html_paragraphs("任务、数据、指标和协议在下方按独立实验块展开；Overview Card 只作索引。"), "paper"))
            sections.append(self._html_section("deep.section.problem-gap-insight-pipeline", "Problem / Gap / Insight / Pipeline", self._html_node("overview.problem", "Problem") + self._html_node("overview.gap", "Gap") + self._html_node("overview.insight", "Insight") + "".join(self._html_node(f"method.step_{i}") for i in range(1, len(self.view.get("mechanism_steps") or []) + 1)), "paper"))
            # Keep benchmark terms and takeaways as real Deep articles too.
            # Formula discovery may bind to a term node; without this section
            # a valid ``#node-term-*`` target would have no scrollable anchor.
            key_nodes = [node_id for node_id in self.nodes if node_id.startswith("term.")]
            key_nodes.extend(node_id for node_id in ("overview.approach", "takeaway.1", "takeaway.2", "takeaway.3", "takeaway.4", "takeaway.5") if node_id in self.nodes)
            sections.append(self._html_section("deep.section.key-terms-learning-trace", "Key Terms and Learning Trace", "".join(self._html_node(node_id) for node_id in key_nodes), "paper"))
        else:
            sections.append(self._html_section("deep.section.problem", "Problem", self._html_node("overview.problem", "Problem"), "overview.problem"))
            sections.append(self._html_section("deep.section.gap", "Gap", self._html_node("overview.gap", "Gap"), "overview.gap"))
            sections.append(self._html_section("deep.section.insight", "Insight", self._html_node("overview.insight", "Insight"), "overview.insight"))
            pipeline = "".join(f"<li><strong>{html.escape(first_nonempty(step.get('title')))}</strong>：{html.escape(first_nonempty(step.get('purpose')))}</li>" for step in self.view.get("mechanism_steps") or [])
            sections.append(self._html_section("deep.section.pipeline-components", "Pipeline / Components", f"<ol>{pipeline}</ol>{''.join(self._html_node(f'method.step_{i}') for i in range(1, len(self.view.get('mechanism_steps') or []) + 1))}", "method"))
            sections.append(self._html_section("deep.section.objective", "Objective", self._html_node("overview.approach", "Training Objective"), "overview.approach"))
        if self.formulas:
            sections.append(self._html_section("deep.section.formula-blocks", "Formula Blocks", "".join(self._html_formula(formula) for formula in self.formulas.values()), "method"))
        experiment_html = []
        for index, evidence in enumerate(self.view.get("decisive_evidence") or [], 1):
            refs = evidence.get("evidence_refs") or self.node_refs(f"evidence.block_{index}")
            experiment_html.append(f"<article class=\"experiment-block\"><h3>Experiment: {html.escape(first_nonempty(evidence.get('question'), f'Experiment {index}'))}</h3><h4>Question</h4>{self._html_paragraphs(first_nonempty(evidence.get('question')))}<h4>Setup</h4>{self._html_paragraphs('论文给出的任务、数据和运行协议。')}<h4>Comparison</h4>{self._html_paragraphs(first_nonempty(evidence.get('comparison')))}<h4>Metric</h4>{self._html_paragraphs(first_nonempty(evidence.get('metric')))}<h4>Result</h4>{self._html_paragraphs(first_nonempty(evidence.get('result')))}<h4>Meaning</h4>{self._html_paragraphs(first_nonempty(evidence.get('can_support')))}<h4>Boundary</h4>{self._html_paragraphs(first_nonempty(evidence.get('cannot_support')))}<p class=\"evidence-line\"><strong>Evidence</strong> {html.escape('; '.join(refs))}</p></article>")
        sections.append(self._html_section("deep.section.experiments-ablation-robustness", "Experiments / Ablation / Robustness", "".join(experiment_html), "evidence"))
        sections.append(self._html_section("deep.section.main-results", "Main Results", self._html_node("overview.findings", "Main Results") + self._html_section("deep.section.limitations", "Limitations", self._html_node("overview.boundary", "Limitations"), "overview.boundary"), "overview.findings"))
        chain = "".join(f"<li><strong>{html.escape(first_nonempty(entry.get('node')))}</strong> → {html.escape(first_nonempty(entry.get('relation')))}</li>" for entry in self.view.get("argument_chain") or [])
        questions = "".join(f"<li>{html.escape(first_nonempty(item.get('title')))} <small>({html.escape(node_id)})</small></li>" for node_id, item in self.all_items() if item.get("kind") in {"user_question", "verification_question"})
        sections.append(self._html_section("deep.section.argument-chain", "Full Argument Chain / Verification Questions", f"<ol>{chain}</ol><ul>{questions}</ul>", "paper"))
        sections.append(self._html_section("deep.section.evidence-appendix", "Claim → Evidence Appendix", "<p>See evidence references attached to each Paper Fact and Formula Block.</p>", "paper"))
        nav_css = ".deep-map-nav{display:flex;gap:8px;align-items:center;font-size:12px;margin:4px 0 10px}.deep-map-nav a{color:#176b87}.deep-map-nav code{color:#64748b}.deep-highlight{outline:3px solid #d97706;box-shadow:0 0 0 6px rgba(217,119,6,.18);transition:box-shadow .2s}"
        nav_script = """<script>(function(){function focusTarget(){var hash=decodeURIComponent(location.hash||'');var target=null;if(hash.indexOf('#formula=')===0){var id=hash.slice(9);target=document.querySelector('[data-formula-id=\\"'+CSS.escape(id)+'\\"]')}else if(hash.indexOf('#node=')===0){var node=hash.slice(6).replace(/[^a-zA-Z0-9_-]+/g,'-').replace(/^-|-$/g,'').toLowerCase();target=document.getElementById('node-'+node)}if(!target)return;target.scrollIntoView({block:'start'});target.classList.add('deep-highlight');setTimeout(function(){target.classList.remove('deep-highlight')},1800)}window.addEventListener('hashchange',focusTarget);if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',focusTarget);else focusTarget()})();</script>"""
        return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(self.title)} · Deep</title><style>{katex_css}body{{margin:0;background:#f4f7fb;color:#17212b;font:15px/1.6 system-ui,Microsoft YaHei,sans-serif}}main{{max-width:1100px;margin:0 auto;padding:28px 34px}}h1{{font-size:28px;margin:0 0 4px}}h2{{margin-top:34px;border-bottom:2px solid #176b87;padding-bottom:5px}}h3{{margin-top:18px}}h4{{margin:12px 0 3px;color:#176b87}}.status,.claim,.formula-layer,.experiment-block{{background:#fff;border:1px solid #d5dee9;padding:12px;margin:10px 0;border-radius:6px}}.claim.tutor{{border-left:4px solid #6b4ea2}}.claim.paper-fact{{border-left:4px solid #176b87}}.formula-badge{{font-weight:700;color:#176b87}}.formula-render{{padding:12px;overflow:auto;text-align:center;min-height:34px}}.formula-source{{margin-top:8px}}pre{{white-space:pre-wrap;overflow:auto;background:#f4f7fb;padding:8px;font:12px ui-monospace,Consolas,monospace}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #d5dee9;padding:7px;text-align:left;vertical-align:top}}.evidence-line{{color:#64748b;font-size:13px}}.muted{{color:#64748b}}.formula-error{{color:#b42318;border:1px solid #e8aaa2;padding:6px}}button{{padding:5px 8px}}@media(prefers-color-scheme:dark){{body{{background:#121923;color:#e8eef5}}.status,.claim,.formula-layer,.experiment-block{{background:#1b2633;border-color:#344354}}pre{{background:#10171f}}th,td{{border-color:#344354}}}} </style></head><body><main><h1>{html.escape(self.title)}</h1><p class=\"status\">{html.escape(self.status_line('deep'))} · KaTeX {html.escape(version)} · offline bundle</p>{''.join(sections)}</main><script>{katex_js}</script><script>window.__formulaRenderErrors=[];function renderFormula(node){{try{{window.katex.render(node.dataset.tex,node,{{displayMode:node.dataset.display!=='false',throwOnError:true,trust:false,strict:'warn',output:'htmlAndMathml'}});node.dataset.rendered='true'}}catch(error){{window.__formulaRenderErrors.push({{latex:node.dataset.tex,message:String(error.message||error)}});node.dataset.rendered='false';node.innerHTML='<pre class=\\"raw-tex formula-fallback\\">'+node.dataset.tex.replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]))+'</pre><div class=\\"formula-error\\">Formula rendering unavailable</div>'}}}}document.querySelectorAll('[data-tex]').forEach(renderFormula);document.querySelectorAll('.copy-tex').forEach(button=>button.addEventListener('click',()=>navigator.clipboard?.writeText(button.dataset.copyTex||'')));</script></body></html>"""

    def deep_html(self) -> str:
        """Return the legacy Deep document with stable navigation behavior."""

        document = self._deep_html_legacy()
        nav_css = ".deep-map-nav{display:flex;gap:8px;align-items:center;font-size:12px;margin:4px 0 10px}.deep-map-nav a{color:#176b87}.deep-map-nav code{color:#64748b}.deep-highlight{outline:3px solid #d97706;box-shadow:0 0 0 6px rgba(217,119,6,.18);transition:box-shadow .2s}"
        nav_script = """<script>(function(){function focusTarget(){var hash=decodeURIComponent(location.hash||'');var target=null;if(hash.indexOf('#formula=')===0){var id=hash.slice(9);target=document.querySelector('[data-formula-id=\\"'+CSS.escape(id)+'\\"]')}else if(hash.indexOf('#node=')===0){var node=hash.slice(6).replace(/[^a-zA-Z0-9_-]+/g,'-').replace(/^-|-$/g,'').toLowerCase();target=document.getElementById('node-'+node)}if(!target)return;target.scrollIntoView({block:'start'});target.classList.add('deep-highlight');setTimeout(function(){target.classList.remove('deep-highlight')},1800)}window.addEventListener('hashchange',focusTarget);if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',focusTarget);else focusTarget()})();</script>"""
        document = document.replace("<style>", f"<style>{nav_css}", 1)
        compact_node_script = """<script>(function(){function focusCompact(){var hash=decodeURIComponent(location.hash||'');if(hash.indexOf('#node-')!==0)return;var target=document.getElementById(hash.slice(1));if(!target)return;target.scrollIntoView({block:'start'});target.classList.add('deep-highlight');setTimeout(function(){target.classList.remove('deep-highlight')},1800)}window.addEventListener('hashchange',focusCompact);if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',focusCompact);else focusCompact()})();</script>"""
        document = document.replace("</body></html>", nav_script + compact_node_script + "</body></html>", 1)
        return document

    def coverage(self, deep_markdown: str) -> dict[str, Any]:
        counts = Counter()
        represented = Counter()
        entries = []
        for node_id, item in self.all_items():
            kind = clean(item.get("kind"))
            counts[kind] += 1
            title = first_nonempty(item.get("title"), item.get("summary"), default="untitled")
            hit = title in deep_markdown or clean(item.get("body")) in deep_markdown
            if hit:
                represented[kind] += 1
            entries.append({"node_id": node_id, "kind": kind, "title": title, "importance": item.get("importance"), "represented": hit})
        unresolved = self.tutor_state.get("unresolved_items") or []
        formula_meta = (self.formula_index.get("meta") or {}).get("coverage") or {}
        anchor_sections = [
            {"section_id": self.deep_section_id(node_id), "anchor_node_id": node_id, "deep_id": self.deep_anchor_id(node_id), "map_href": self.map_href(node_id)}
            for node_id in self.nodes
            if node_id not in {"paper", "method", "evidence", "terms", "takeaways"}
        ]
        formula_anchors = [
            {"formula_id": clean(formula.get("id")), "anchor_node_id": clean(formula.get("anchor_node_id")), "deep_id": self.deep_anchor_id(clean(formula.get("anchor_node_id")), clean(formula.get("id"))), "deep_href": self.deep_href(clean(formula.get("anchor_node_id")), clean(formula.get("id")))}
            for formula in self.formula_index.get("formulas", [])
            if isinstance(formula, dict)
        ]
        return {
            "title": self.title,
            "paper_type": self.paper_type,
            "depth": "deep",
            "source": self.paper_map.get("source"),
            "tutor_state_schema": self.tutor_state.get("schema_version"),
            "total_items": sum(counts.values()),
            "represented_items": sum(represented.values()),
            "by_kind": {kind: {"total": counts[kind], "represented": represented[kind]} for kind in sorted(counts)},
            "high_importance_total": sum(1 for _, item in self.all_items() if item.get("importance") == "high"),
            "high_importance_represented": sum(1 for _, item in self.all_items() if item.get("importance") == "high" and (first_nonempty(item.get("title"), item.get("summary"), default="untitled") in deep_markdown or clean(item.get("body")) in deep_markdown)),
            "unresolved_items": len(unresolved),
            "unresolved_titles": [first_nonempty(item.get("title")) for item in unresolved],
            "items": entries,
            "anchor_sections": anchor_sections,
            "formula_anchors": formula_anchors,
            "formula_coverage": {
                "detected_candidates": int(formula_meta.get("detected_candidates", len(self.formulas))),
                "validated_formulas": int(formula_meta.get("validated_formulas", len(self.formulas))),
                "anchored_formulas": int(formula_meta.get("anchored_formulas", len(self.formulas))),
                "unresolved_candidates": int(formula_meta.get("unresolved_candidates", 0)),
                "formula_blocks_rendered": int(formula_meta.get("formula_blocks_rendered", len(self.formulas))),
            },
            "sync_status": self.sync_status(),
            "dedupe_report": self.tutor_state.get("dedupe_report") or {"exact_dedupes": 0, "canonical_intent_dedupes": 0, "similarity_lite_dedupes": 0, "rejected_merges": 0},
        }


def project_files(
    map_project: Path,
    scholar_project: Path,
    compact_path: Path,
    deep_path: Path,
    coverage_path: Path,
    formula_index_path: Path | None = None,
    deep_html_path: Path | None = None,
) -> dict[str, Any]:
    paper_map = load_json(map_project / "paper-map.json")
    tutor_state = load_json(map_project / "tutor-state.json")
    reading_view = load_json(scholar_project / "reading-view.json")
    digest = load_json(scholar_project / "digest.json")
    # When CKPT-1 has already produced a source-bound formula index, project
    # that reviewed index verbatim.  Falling back to discovery preserves the
    # existing cold-start behavior for projects without one.
    reviewed_formula_index = None
    map_formula_path = map_project / "formula-index.json"
    if map_formula_path.is_file():
        reviewed_formula_index = load_json(map_formula_path)
    sync_receipts: list[dict[str, Any]] = []
    receipt_dir = map_project / "sync-receipts"
    if receipt_dir.is_dir():
        for receipt_path in sorted(receipt_dir.glob("*.json")):
            try:
                value = load_json(receipt_path)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            sync_receipts.append(value)
    projection = Projection(paper_map, tutor_state, reading_view, digest, formula_index=reviewed_formula_index, sync_receipts=sync_receipts)
    compact = projection.compact()
    deep = projection.deep()
    compact_path.parent.mkdir(parents=True, exist_ok=True)
    deep_path.parent.mkdir(parents=True, exist_ok=True)
    compact_path.write_text(compact, encoding="utf-8")
    deep_path.write_text(deep, encoding="utf-8")
    formula_target = (formula_index_path or (deep_path.parent / "formula-index.json")).resolve()
    write_formula_index(projection.formula_index, formula_target)
    html_target = (deep_html_path or (deep_path.parent / "paper-tutor-deep-v2.html")).resolve()
    html_target.parent.mkdir(parents=True, exist_ok=True)
    html_target.write_text(projection.deep_html(), encoding="utf-8")
    report = projection.coverage(deep)
    report["compact_characters"] = len(compact)
    report["deep_characters"] = len(deep)
    report["compact_sections"] = len(re.findall(r"^## ", compact, re.M))
    report["deep_sections"] = len(re.findall(r"^## ", deep, re.M))
    report["formula_blocks"] = len(re.findall(r"^### Formula:", deep, re.M))
    report["experiment_blocks"] = len(re.findall(r"^### Experiment:", deep, re.M))
    report["formula_count"] = len(projection.formulas)
    report["formula_index"] = str(formula_target)
    report["formula_index_sha256"] = formula_index_digest(projection.formula_index)
    report["formula_coverage"] = report.get("formula_coverage", {})
    report["anchor_integrity"] = {
        "section_count": len(report.get("anchor_sections", [])),
        "formula_anchor_count": len(report.get("formula_anchors", [])),
        "dangling_node_anchors": [item["anchor_node_id"] for item in report.get("anchor_sections", []) if item.get("anchor_node_id") not in projection.nodes],
        "dangling_formula_anchors": [item["formula_id"] for item in report.get("formula_anchors", []) if item.get("anchor_node_id") not in projection.nodes],
    }
    report["deep_html"] = str(html_target)
    report["deep_html_characters"] = len(html_target.read_text(encoding="utf-8"))
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Project Paper-Tutor compact/deep Markdown from structured state")
    parser.add_argument("--map-project", required=True)
    parser.add_argument("--scholar-project", required=True)
    parser.add_argument("--compact-output", required=True)
    parser.add_argument("--deep-output", required=True)
    parser.add_argument("--coverage-output", required=True)
    parser.add_argument("--formula-index-output")
    parser.add_argument("--deep-html-output")
    args = parser.parse_args()
    report = project_files(
        Path(args.map_project).resolve(),
        Path(args.scholar_project).resolve(),
        Path(args.compact_output).resolve(),
        Path(args.deep_output).resolve(),
        Path(args.coverage_output).resolve(),
        Path(args.formula_index_output).resolve() if args.formula_index_output else None,
        Path(args.deep_html_output).resolve() if args.deep_html_output else None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
