#!/usr/bin/env python3
"""Human-readable, source-bound projections for Mode A and Mode B.

The Markdown documents emitted here are projections only.  They never become an
input to the semantic, quantitative, checkpoint, or deck pipelines.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from audience_text import repair_pdf_hyphenation, sanitize_audience_text
from ckpt1_resolved import CKPT1ResolvedViewError, resolve_ckpt1_view
from ckpt1_review import ReviewCandidateError, canonicalize_review_candidate
from reading_view import ReadingViewError, load_reading_view


_MARKER_RE = re.compile(r"\[(?:MISSING|UNVERIFIED):[^\]]+\]", re.IGNORECASE)
_INTERNAL_RE = re.compile(
    r"(?:\baudit(?:ed|ing)?\b|\bcheckpoint\b|\bsha[- ]?256\b|\bjson\s+(?:path|pointer)\b|"
    r"\bmarker\s+ledger\b|\bplanner\s+instruction\b|\binternal\s+provenance\b|"
    r"\[(?:MISSING|UNVERIFIED):)",
    re.IGNORECASE,
)
_FORMULA_RE = re.compile(
    r"(?:\$(?:\\.|[^$])+\$|\\\((?:\\.|[^)])+\\\)|\\\[(?:\\.|[^]])+\\\]|"
    r"(?<![A-Za-z0-9_])(?:[A-Za-z][A-Za-z0-9_]*\s*:\s*)?"
    r"\([^\n，。；;]{1,160}\)\s*(?:→|->|↦|=>)\s*\[[^\]\n]{1,160}\])"
)
_TRADEOFF_RE = re.compile(
    r"(?:trade[- ]?off|negative|failure|limitation|latency|cost|下降|降低|失败|局限|权衡|代价|延迟)",
    re.IGNORECASE,
)


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clean(value: Any, fallback: str = "") -> str:
    text = repair_pdf_hyphenation(sanitize_audience_text(value, ""))
    text = _MARKER_RE.sub("", text)
    text = re.sub(r"\s+([，。；：,.!?])", r"\1", text).strip(" ，,；;：:")
    return text or fallback


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def _atomic_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content.rstrip() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _evidence(item: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(item, Mapping):
        return []
    records: list[Mapping[str, Any]] = []
    refs = item.get("source_refs")
    if isinstance(refs, list):
        records.extend(ref for ref in refs if isinstance(ref, Mapping))
    evidence = item.get("evidence")
    if isinstance(evidence, Mapping):
        records.append(evidence)
    records.append(item)
    output: list[dict[str, Any]] = []
    seen: set[tuple[Any, str]] = set()
    for record in records:
        page = record.get("source_page", record.get("page"))
        locator = _clean(
            record.get("locator"),
            _clean(record.get("figure_table_equation"), _clean(record.get("section"), "")),
        )
        if not isinstance(page, int) or page < 1 or not locator:
            continue
        key = (page, locator.casefold())
        if key in seen:
            continue
        seen.add(key)
        output.append({"page": page, "locator": locator, "section": _clean(record.get("section"), "")})
    return output


def _locator(item: Mapping[str, Any] | None) -> str:
    refs = _evidence(item)
    if not refs:
        return ""
    parts = []
    for ref in refs:
        locator = ref["locator"]
        parts.append(f"p. {ref['page']}" if locator.casefold() in {"p. " + str(ref['page']), "page " + str(ref['page'])} else f"p. {ref['page']}, {locator}")
    return "；".join(parts)


def _with_locator(text: Any, item: Mapping[str, Any] | None) -> str:
    cleaned = _clean(text)
    locator = _locator(item)
    if not cleaned:
        return ""
    return f"{cleaned}（{locator}）" if locator else cleaned


def _item_text(item: Mapping[str, Any] | None) -> str:
    if not isinstance(item, Mapping):
        return ""
    return _clean(item.get("summary"), _clean(item.get("text"), ""))


def _slots(view: Mapping[str, Any]) -> Mapping[str, Any]:
    semantics = view.get("reviewed_paper_semantics")
    if not isinstance(semantics, Mapping):
        semantics = view.get("paper_semantics")
    values = semantics.get("slots") if isinstance(semantics, Mapping) else None
    return values if isinstance(values, Mapping) else {}


def _list_items(view: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    values = view.get(name)
    return [item for item in values if isinstance(item, Mapping)] if isinstance(values, list) else []


def _section_record(slots: Mapping[str, Any], name: str, fallback: str = "该论文未明确报告这一项。") -> str:
    item = slots.get(name)
    if not isinstance(item, Mapping):
        return fallback
    return _with_locator(_item_text(item), item) or fallback


def _bullet_records(items: Sequence[Mapping[str, Any]], fallback: str) -> list[str]:
    values = [_with_locator(_item_text(item), item) for item in items]
    values = [value for value in values if value]
    return values or [fallback]


def _natural_unresolved_count(unresolved: Sequence[Any], *, chinese: bool = True) -> str:
    count = len([item for item in unresolved if _compact(item)])
    if chinese:
        return "当前没有待人工确认的证据。" if count == 0 else f"仍有 {count} 项证据需人工确认。"
    noun = "item" if count == 1 else "items"
    return "No evidence currently requires human confirmation." if count == 0 else f"{count} evidence {noun} still requires human confirmation."


def _assert_user_safe(document: str, *, allow_ckpt_status: bool = False) -> None:
    scan = document
    if allow_ckpt_status:
        scan = re.sub(r"^CKPT-1 状态：[^\n]+$", "", scan, flags=re.MULTILINE)
    match = _INTERNAL_RE.search(scan)
    if match:
        raise ValueError(f"user-facing document contains internal workflow language: {match.group(0)}")


_READING_CLAIM_LABELS = {
    "paper_fact": "论文事实",
    "explanation": "直观解释",
    "analysis": "读者分析",
}

_READING_CLAIM_LABELS_EN = {
    "paper_fact": "Paper fact",
    "explanation": "Plain-language explanation",
    "analysis": "Reader analysis",
}

_READING_STATUS_LABELS = {
    "pending_human_confirmation": "待人工确认",
    "pending": "待确认",
    "confirmed": "已确认",
    "approved": "已确认",
    "not_created": "尚未创建审阅记录",
}

_READING_STATUS_LABELS_EN = {
    "pending_human_confirmation": "pending human confirmation",
    "pending": "pending confirmation",
    "confirmed": "confirmed",
    "approved": "confirmed",
    "not_created": "review record not created",
}

_READING_KIND_LABELS = {
    "author_contribution": "作者贡献",
    "explicit_limitation": "作者局限",
    "reader_analysis": "读者分析",
    "research_question": "研究追问",
}

_READING_KIND_LABELS_EN = {
    "author_contribution": "Author contribution",
    "explicit_limitation": "Author limitation",
    "reader_analysis": "Reader analysis",
    "research_question": "Research question",
}


def _reading_record(
    record: Mapping[str, Any] | None,
    *,
    fallback: str = "当前证据未提供这一项。",
    chinese: bool = True,
) -> str:
    if not isinstance(record, Mapping):
        return fallback
    content = _clean(record.get("content"), fallback)
    labels = _READING_CLAIM_LABELS if chinese else _READING_CLAIM_LABELS_EN
    label = labels.get(_compact(record.get("claim_type")).casefold(), "说明" if chinese else "Note")
    availability = _compact(record.get("availability")).casefold()
    if availability == "not_reported":
        content = f"{content}（作者未报告）" if chinese else f"{content} (not reported by the authors)"
    elif availability == "unverifiable":
        content = f"{content}（当前证据无法核实）" if chinese else f"{content} (not verifiable from the current evidence)"
    refs = record.get("evidence_refs")
    references = "；".join(_clean(value) for value in refs if _clean(value)) if isinstance(refs, list) else ""
    suffix = (f"（证据：{references}）" if chinese else f" (evidence: {references})") if references else ""
    separator = "：" if chinese else ": "
    return f"{label}{separator}{content}{suffix}"


def _reading_step(step: Mapping[str, Any], index: int, *, chinese: bool = True) -> str:
    title = _clean(step.get("title"), f"步骤 {index}" if chinese else f"Step {index}")
    purpose = _clean(step.get("purpose"), "当前证据未说明这一步的作用。" if chinese else "The source does not explain this step.")
    input_text = _clean(step.get("input"), "当前证据未说明输入。" if chinese else "Input not reported by the source.")
    output_text = _clean(step.get("output"), "当前证据未说明输出。" if chinese else "Output not reported by the source.")
    necessity = _clean(step.get("necessity"), "当前证据未说明必要性。" if chinese else "Necessity not reported by the source.")
    labels = ("输入", "输出", "为什么需要") if chinese else ("Input", "Output", "Why it is needed")
    return (
        f"### {index}. {title}\n\n"
        f"{_reading_record(step, fallback=purpose, chinese=chinese)}\n"
        f"- {labels[0]}{':' if not chinese else '：'}{input_text}\n"
        f"- {labels[1]}{':' if not chinese else '：'}{output_text}\n"
        f"- {labels[2]}{':' if not chinese else '：'}{necessity}"
    )


def render_reading_analysis(
    reading_view: Mapping[str, Any],
    *,
    ckpt1_status: str = "pending_human_confirmation",
    unresolved: Sequence[Any] = (),
) -> str:
    """Render the compact, model-authored reading view in its declared language."""
    chinese = not str(reading_view.get("language", "zh-CN")).casefold().startswith("en")
    identity = reading_view.get("paper_identity") if isinstance(reading_view.get("paper_identity"), Mapping) else {}
    title = _clean(identity.get("title"), "未命名论文" if chinese else "Untitled paper")
    overview = reading_view.get("overview") if isinstance(reading_view.get("overview"), Mapping) else {}
    paper_type = reading_view.get("paper_type") if isinstance(reading_view.get("paper_type"), Mapping) else {}
    steps = [item for item in reading_view.get("mechanism_steps", []) if isinstance(item, Mapping)]
    chain = [item for item in reading_view.get("argument_chain", []) if isinstance(item, Mapping)]
    evidence = [item for item in reading_view.get("decisive_evidence", []) if isinstance(item, Mapping)]
    terms = [item for item in reading_view.get("terms", []) if isinstance(item, Mapping)]
    takeaways = [item for item in reading_view.get("takeaways", []) if isinstance(item, Mapping)]
    status_labels = _READING_STATUS_LABELS if chinese else _READING_STATUS_LABELS_EN
    status_text = status_labels.get(
        _compact(ckpt1_status).casefold(),
        _clean(ckpt1_status, "待确认" if chinese else "pending confirmation"),
    )

    def sep() -> str:
        return "：" if chinese else ": "

    def record(record: Mapping[str, Any] | None, fallback: str | None = None) -> str:
        default = fallback or ("当前证据未提供这一项。" if chinese else "The current evidence does not provide this item.")
        return _reading_record(record, fallback=default, chinese=chinese)

    overview_source_text = " ".join(
        _clean(overview.get(name, {}).get("content"), "")
        for name in ("problem", "gap", "approach", "findings", "boundary")
        if isinstance(overview.get(name), Mapping)
    )
    first_use_terms: list[str] = []
    for item in terms:
        term_name = _clean(item.get("term"), "")
        aliases = [part.strip() for part in re.split(r"/|,|（|）|\(|\)", term_name) if part.strip()]
        if not aliases or not any(alias.casefold() in overview_source_text.casefold() for alias in aliases):
            continue
        plain = _clean(item.get("plain"), "当前证据未提供定义。" if chinese else "No definition is available from the current evidence.")
        availability = _compact(item.get("availability")).casefold()
        if availability == "unverifiable":
            plain += "（当前证据无法核实）" if chinese else " (not verifiable from the current evidence)"
        elif availability == "not_reported":
            plain += "（作者未报告）" if chinese else " (not reported by the authors)"
        first_use_terms.append(f"{term_name}{sep()}{plain}")
        if len(first_use_terms) >= 4:
            break
    if first_use_terms:
        first_use_line = (
            f"- 先认识这些词：{'；'.join(first_use_terms)}"
            if chinese
            else f"- First-use terms: {'; '.join(first_use_terms)}"
        )
    else:
        first_use_line = ""

    overview_text = "\n".join(
        [
            f"- {'论文类型' if chinese else 'Paper type'}{sep()}{_clean(paper_type.get('kind'), '未分类' if chinese else 'uncategorized')}",
            f"- {'研究问题' if chinese else 'Research problem'}{sep()}{record(overview.get('problem'))}",
            f"- {'现有缺口' if chinese else 'Research gap'}{sep()}{record(overview.get('gap'))}",
            f"- {'核心做法' if chinese else 'Core approach'}{sep()}{record(overview.get('approach'))}",
            f"- {'主要发现' if chinese else 'Main finding'}{sep()}{record(overview.get('findings'))}",
            f"- {'结论边界' if chinese else 'Boundary'}{sep()}{record(overview.get('boundary'))}",
        ]
    )
    if first_use_line:
        overview_text = f"{overview_text}\n{first_use_line}"
    if chinese:
        problem_text = (
            f"- 关键改变：{record(overview.get('insight'), '本文把缺口转成一个可检验的设计选择。')}\n"
            "- 阅读重点：先按机制步骤理解这个改变如何作用，再用决定性证据判断它是否真的带来提升。\n"
            f"- 论证边界：{record(overview.get('boundary'))}"
        )
    else:
        problem_text = (
            f"- Key change: {record(overview.get('insight'), 'The paper turns the gap into a testable design choice.')}\n"
            "- Reading focus: follow how this change acts in the mechanism steps, then use decisive evidence to judge whether it improves the outcome.\n"
            f"- Argument boundary: {record(overview.get('boundary'))}"
        )
    chain_lines = []
    for index, node in enumerate(chain, start=1):
        refs = "；".join(_clean(value) for value in node.get("evidence_refs", []) if _clean(value))
        node_record = dict(node)
        node_record["content"] = _clean(node.get("node"), "论证节点" if chinese else "argument node")
        relation = _clean(node.get("relation"), "连接到下一步" if chinese else "connects to the next step")
        chain_lines.append(f"{index}. {record(node_record)} {'——' if chinese else '—'} {relation}。" if chinese else f"{index}. {record(node_record)} — {relation}.")
    evidence_blocks = []
    for index, item in enumerate(evidence, start=1):
        refs = "；".join(_clean(value) for value in item.get("evidence_refs", []) if _clean(value))
        result_record = dict(item)
        result_record["content"] = _clean(item.get("result"), "当前证据未提供结果。" if chinese else "The current evidence does not provide a result.")
        if chinese:
            evidence_blocks.append(
                f"### 证据 {index}：{_clean(item.get('question'), '实验问题')}\n\n"
                f"- 比较设置：{_clean(item.get('comparison'))}\n"
                f"- 指标：{_clean(item.get('metric'))}\n"
                f"- 结果：{record(result_record)}\n"
                f"- 能支持：{_clean(item.get('can_support'))}\n"
                f"- 不能支持：{_clean(item.get('cannot_support'))}\n"
                f"- 定位：{refs or '当前没有可展示的定位'}"
            )
        else:
            evidence_blocks.append(
                f"### Evidence {index}: {_clean(item.get('question'), 'Experimental question')}\n\n"
                f"- Comparison: {_clean(item.get('comparison'))}\n"
                f"- Metric: {_clean(item.get('metric'))}\n"
                f"- Result: {record(result_record)}\n"
                f"- Supports: {_clean(item.get('can_support'))}\n"
                f"- Does not support: {_clean(item.get('cannot_support'))}\n"
                f"- Locator: {refs or 'No locator is available.'}"
            )
    term_lines = []
    for item in terms:
        term_record = dict(item)
        term_record["content"] = _clean(item.get("plain"), "当前证据未提供定义。" if chinese else "The current evidence does not provide a definition.")
        plain = record(term_record)
        term = _clean(item.get("term"), "术语" if chinese else "term")
        role = _clean(item.get("role"), "—")
        confusions = _clean(item.get("confusions"), "—")
        term_lines.append(f"| {term} | {plain} | {role} | {confusions} |")
    takeaway_lines = []
    kind_labels = _READING_KIND_LABELS if chinese else _READING_KIND_LABELS_EN
    for item in takeaways:
        kind = kind_labels.get(_compact(item.get("kind")).casefold(), _clean(item.get("kind"), "要点" if chinese else "Takeaway"))
        takeaway_lines.append(f"- {kind}{sep()}{record(item)}")
    unresolved_text = _natural_unresolved_count(unresolved, chinese=chinese)
    if chinese:
        document = f"""# {title}

> 阅读状态：Scholar-Slides 来源；CKPT-1 {status_text}；讲解深度：深入。

## 1. 30 秒看懂

{overview_text}

## 2. 问题与核心思路

{problem_text}

## 3. 它具体怎么做

{chr(10).join(_reading_step(step, index, chinese=True) for index, step in enumerate(steps, start=1))}

## 4. 证据如何支持结论

{chr(10).join(evidence_blocks)}

## 5. 作者如何组织论证

{chr(10).join(chain_lines)}

## 6. 关键术语与前置知识

| 术语 | 一句话理解（含状态） | 在本文中的作用 | 常见混淆 |
| --- | --- | --- | --- |
{chr(10).join(term_lines) or '| 当前证据未标出关键术语 | 当前证据未提供定义 | — | — |'}

## 7. 贡献、局限与值得追问的问题

{chr(10).join(takeaway_lines)}

## 来源与状态

本文的事实、解释和分析分别标注在对应段落中；证据定位沿用上游记录。{unresolved_text}

CKPT-1 状态：{status_text}
"""
    else:
        document = f"""# {title}

> Reading status: Scholar-Slides source; CKPT-1 {status_text}; explanation depth: deep.

## 1. 30-Second Overview

{overview_text}

## 2. Problem and Core Idea

{problem_text}

## 3. How It Works

{chr(10).join(_reading_step(step, index, chinese=False) for index, step in enumerate(steps, start=1))}

## 4. How the Evidence Supports the Claim

{chr(10).join(evidence_blocks)}

## 5. How the Paper Builds Its Argument

{chr(10).join(chain_lines)}

## 6. Key Terms and Prerequisites

| Term | Plain-language meaning (with status) | Role in this paper | Common confusion |
| --- | --- | --- | --- |
{chr(10).join(term_lines) or '| No key terms were marked in the current evidence | No definition is available | — | — |'}

## 7. Contributions, Limits, and Questions to Pursue

{chr(10).join(takeaway_lines)}

## Sources and Status

Facts, explanations, and analyses are labeled in their respective paragraphs; evidence locators follow the upstream record. {unresolved_text}

CKPT-1 status: {status_text}
"""
    _assert_user_safe(document, allow_ckpt_status=True)
    return document.rstrip() + "\n"


def render_paper_analysis(
    resolved_view: Mapping[str, Any],
    *,
    language: str = "zh-CN",
    ckpt1_status: str = "pending_human_confirmation",
    unresolved: Sequence[Any] = (),
) -> str:
    """Project one reviewed semantic view into the configured user language."""
    chinese = str(language).casefold().startswith("zh")
    title = _clean(resolved_view.get("title"), "未命名论文" if chinese else "Untitled paper")
    slots = _slots(resolved_view)
    claims = _list_items(resolved_view, "claims")
    contributions = _list_items(resolved_view, "contributions")
    results = _list_items(resolved_view, "experimental_results")
    metrics = _list_items(resolved_view, "key_metrics")

    missing = "该论文未明确报告这一项。" if chinese else "The paper does not explicitly report this item."
    section = lambda name: _section_record(slots, name, missing)
    one_sentence = section("objective_or_research_question")
    approach = section("approach")
    main_result = section("main_results")
    limitation = section("limitations_or_failure_modes")

    method_lines = [section("approach")]
    method_item = slots.get("approach") if isinstance(slots.get("approach"), Mapping) else None
    if method_item:
        refs = _evidence(method_item)
        if len(refs) > 1:
            prefix = "补充方法依据" if chinese else "Additional method evidence"
            method_lines.extend(f"{prefix}: p. {ref['page']}, {ref['locator']}." for ref in refs[1:])

    metric_lines = []
    for metric in metrics:
        label = _clean(metric.get("label"), "关键指标" if chinese else "Key metric")
        value = _clean(metric.get("value"), "")
        if value:
            metric_lines.append(_with_locator(f"{label}：{value}", metric))
    result_lines = _bullet_records(results, main_result)
    for metric_line in metric_lines:
        if metric_line and metric_line not in result_lines:
            result_lines.append(metric_line)

    evidence_items = [*claims, *contributions, *results, *metrics]
    figure_lines: list[str] = []
    seen_locators: set[str] = set()
    for item in evidence_items:
        for ref in _evidence(item):
            if not re.search(r"(?:figure|fig\.?|table|图|表)", ref["locator"], re.IGNORECASE):
                continue
            key = f"{ref['page']}:{ref['locator'].casefold()}"
            if key in seen_locators:
                continue
            seen_locators.add(key)
            explanation = _item_text(item)
            punctuation = "：" if chinese else ": "
            figure_lines.append(f"- {ref['locator']}{punctuation}{explanation}（p. {ref['page']}, {ref['locator']}）")
    if not figure_lines:
        figure_lines.append("- 该论文未在当前来源视图中标出必须单独解读的核心图表。" if chinese else "- The current source-bound view does not identify a core figure or table that requires separate interpretation.")

    tradeoff = []
    for item in [*results, *claims]:
        text = _item_text(item)
        if text and _TRADEOFF_RE.search(text):
            tradeoff.append(_with_locator(text, item))
    if _TRADEOFF_RE.search(_item_text(slots.get("limitations_or_failure_modes") if isinstance(slots.get("limitations_or_failure_modes"), Mapping) else None)):
        tradeoff.append(limitation)
    tradeoff = list(dict.fromkeys(value for value in tradeoff if value)) or [
        "当前证据未单独报告 ablation、trade-off 或 negative result。"
        if chinese else
        "The current evidence does not separately report an ablation, trade-off, or negative result."
    ]

    terms_source = " ".join([title, *(_item_text(item) for item in evidence_items), *(_item_text(item) for item in slots.values() if isinstance(item, Mapping))])
    terms = []
    for token in re.findall(r"\b(?:[A-Z]{2,}[A-Za-z0-9-]*|[A-Z][A-Za-z]+(?:-[A-Za-z0-9]+)+)\b", terms_source):
        if token not in terms:
            terms.append(token)
    term_lines = [
        f"- {term}：当前旧项目未提供可核实的术语定义，请回到论文原文首次出现位置核对。"
        if chinese else
        f"- {term}: the legacy project does not provide a verifiable definition; check the term at its first occurrence in the paper."
        for term in terms[:8]
    ]
    if not term_lines:
        term_lines = ["- 当前来源视图未标出需要单独解释的英文缩写。" if chinese else "- The current source-bound view does not identify an abbreviation that needs separate explanation."]

    sources: list[str] = []
    for item in [*(value for value in slots.values() if isinstance(value, Mapping)), *evidence_items]:
        for ref in _evidence(item):
            value = f"- p. {ref['page']}, {ref['locator']}"
            if value not in sources:
                sources.append(value)

    contrib_lines = _bullet_records(contributions, section("contributions"))
    remember = [one_sentence, approach, main_result, limitation]
    if chinese:
        document = f"""# {title}

## 1. 一句话讲清这篇论文

{one_sentence}

## 2. 研究背景

{section('context')}

## 3. 论文要解决什么问题

{section('objective_or_research_question')}

{section('problem_setup')}

## 4. 为什么已有方法不够

{section('motivation_or_gap')}

## 5. 方法主线

{approach}

## 6. 方法拆解

{chr(10).join(f'- {line}' for line in method_lines)}

## 7. 主要贡献

{chr(10).join(f'- {line}' for line in contrib_lines)}

## 8. 实验设置

{section('experimental_setup')}

## 9. 核心结果

{chr(10).join(f'- {line}' for line in result_lines)}

## 10. 关键图表怎么读

{chr(10).join(figure_lines)}

## 11. Ablation / Trade-off / Negative Results

{chr(10).join(f'- {line}' for line in tradeoff)}

## 12. 局限与失败模式

{limitation}

## 13. 我应该如何理解这篇论文

可以把这篇论文理解为从“{_clean(_item_text(slots.get('objective_or_research_question') if isinstance(slots.get('objective_or_research_question'), Mapping) else None), '研究问题')}”出发，使用“{_clean(_item_text(slots.get('approach') if isinstance(slots.get('approach'), Mapping) else None), '论文方法')}”回答问题，并由核心实验检验其适用范围。这个理解是对上述来源内容的综合，不扩大论文结论。

## 14. 重要术语

{chr(10).join(term_lines)}

## 15. 组会 / 面试时最值得记住的内容

{chr(10).join(f'- {line}' for line in remember)}

## Sources / Evidence

{chr(10).join(sources) if sources else '- 当前没有可展示的自然页码定位。'}

---

Source status：source-bound reviewed projection

CKPT-1 状态：{_clean(ckpt1_status, 'pending')}
{_natural_unresolved_count(unresolved, chinese=True)}
"""
    else:
        objective_text = _clean(_item_text(slots.get("objective_or_research_question") if isinstance(slots.get("objective_or_research_question"), Mapping) else None), "the research question")
        approach_text = _clean(_item_text(slots.get("approach") if isinstance(slots.get("approach"), Mapping) else None), "the proposed method")
        document = f"""# {title}

## 1. The Paper in One Sentence

{one_sentence}

## 2. Research Background

{section('context')}

## 3. Research Question and Problem Setup

{section('objective_or_research_question')}

{section('problem_setup')}

## 4. Motivation and Research Gap

{section('motivation_or_gap')}

## 5. Method Overview

{approach}

## 6. Method Breakdown

{chr(10).join(f'- {line}' for line in method_lines)}

## 7. Main Contributions

{chr(10).join(f'- {line}' for line in contrib_lines)}

## 8. Experimental Setup

{section('experimental_setup')}

## 9. Core Results

{chr(10).join(f'- {line}' for line in result_lines)}

## 10. How to Read the Key Figures and Tables

{chr(10).join(figure_lines)}

## 11. Ablations, Trade-offs, and Negative Results

{chr(10).join(f'- {line}' for line in tradeoff)}

## 12. Limitations and Failure Modes

{limitation}

## 13. How to Interpret the Paper

The paper can be understood as starting from “{objective_text}”, answering it with “{approach_text}”, and using the core experiments to test the method's scope. This synthesis stays within the source-backed claims above.

## 14. Important Terms

{chr(10).join(term_lines)}

## 15. What to Remember for a Reading Group or Interview

{chr(10).join(f'- {line}' for line in remember)}

## Sources / Evidence

{chr(10).join(sources) if sources else '- No natural page locator is currently available.'}

---

Source status: source-bound reviewed projection

CKPT-1 status: {_clean(ckpt1_status, 'pending')}
{_natural_unresolved_count(unresolved, chinese=False)}
"""
    _assert_user_safe(document, allow_ckpt_status=True)
    return document.rstrip() + "\n"


def _slide_title(slide: Mapping[str, Any], index: int) -> str:
    return _clean(slide.get("action_title"), _clean(slide.get("title"), f"Slide {index}"))


def _slide_takeaway(slide: Mapping[str, Any], index: int) -> str:
    return _clean(slide.get("core_conclusion"), _slide_title(slide, index))


def _slide_source(slide: Mapping[str, Any]) -> str:
    value = _clean(slide.get("source_ref"), "")
    if value:
        return value.replace(" — ", ", ").replace("—", ", ")
    table = slide.get("table")
    if isinstance(table, Mapping) and isinstance(table.get("source_page"), int):
        return f"p. {table['source_page']}, {_clean(table.get('locator'), 'Table')}"
    return ""


def _slide_points(slide: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("points", "points2", "entries", "questions"):
        raw = slide.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, Mapping):
                text = "：".join(filter(None, (_clean(item.get("head"), ""), _clean(item.get("body"), ""))))
            else:
                text = _clean(item, "")
            if text and text not in values:
                values.append(text)
    return values


def _timings(deck: Mapping[str, Any]) -> list[float]:
    slides = deck.get("slides") if isinstance(deck.get("slides"), list) else []
    meta = deck.get("meta") if isinstance(deck.get("meta"), Mapping) else {}
    options = meta.get("options") if isinstance(meta.get("options"), Mapping) else {}
    target = options.get("talk_time_minutes", meta.get("talk_time_minutes", 30))
    target = float(target) if isinstance(target, (int, float)) and target > 0 else 30.0
    weights: list[float] = []
    for slide in slides:
        role = _compact(slide.get("role")).casefold() if isinstance(slide, Mapping) else ""
        layout = _compact(slide.get("layout")).casefold() if isinstance(slide, Mapping) else ""
        weight = 1.0
        if role == "title" or layout in {"title", "paper-title"}:
            weight = 0.65
        elif role == "references" or layout == "references":
            weight = 0.6
        elif layout == "results-table" or role in {"results-table", "analysis"}:
            weight = 1.35
        elif isinstance(slide, Mapping) and isinstance(slide.get("figure"), Mapping):
            weight = 1.25
        elif role in {"method-overview", "experiment", "comparison"}:
            weight = 1.2
        density = len(_slide_points(slide)) if isinstance(slide, Mapping) else 0
        weight += min(0.3, density * 0.04)
        weights.append(weight)
    if not weights:
        return []
    scale = target / sum(weights)
    minutes = [round(weight * scale, 1) for weight in weights]
    minutes[-1] = round(minutes[-1] + (target - sum(minutes)), 1)
    return minutes


def _formulas(slide: Mapping[str, Any]) -> list[str]:
    values = [
        slide.get("speaker_notes"),
        slide.get("action_title"),
        *_slide_points(slide),
    ]
    equations = slide.get("equations")
    if isinstance(equations, list):
        values.extend(equations)
    output: list[str] = []
    for value in values:
        for formula in _FORMULA_RE.findall(str(value or "")):
            if formula not in output:
                output.append(formula)
    return output


def _key_values(slide: Mapping[str, Any]) -> list[str]:
    output: list[str] = []
    for key in ("quantitative_key_numbers", "speaker_allowed_numbers"):
        values = slide.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            cleaned = _clean(value, "")
            if cleaned and cleaned not in output:
                output.append(cleaned)
    return output


def _purpose(slide: Mapping[str, Any], index: int) -> str:
    role = _compact(slide.get("role")).casefold()
    labels = {
        "title": "建立论文身份与整场汇报的核心问题。",
        "background": "交代研究背景，让听众理解问题为何重要。",
        "research-question": "明确论文真正要解决的问题与评价边界。",
        "method-overview": "讲清方法的组成、顺序与每个阶段的作用。",
        "experiment": "说明实验怎样检验方法，而不是只罗列设置。",
        "comparison": "比较关键方案并说明证据支持的差异。",
        "results-table": "用可核对的定量结果回答研究问题。",
        "analysis": "解释结果中的规律、边界与权衡。",
        "conclusion": "收束论文贡献、结果与局限。",
        "presenter-discussion": "把论文事实与汇报者讨论明确分开。",
        "references": "给出论文来源，便于会后追溯。",
    }
    return labels.get(role, f"讲清本页结论“{_slide_takeaway(slide, index)}”。")


def _table_guidance(slide: Mapping[str, Any]) -> str:
    table = slide.get("table")
    if not isinstance(table, Mapping):
        return ""
    columns = table.get("columns") if isinstance(table.get("columns"), list) else []
    labels = [_clean(column.get("label"), "") for column in columns if isinstance(column, Mapping)]
    labels = [label for label in labels if label]
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    row_names = [_clean(row[0], "") for row in rows if isinstance(row, list) and row]
    start = f"先看列 {'、'.join(labels)}" if labels else "先确认表格比较维度"
    if row_names:
        start += f"，再按行比较 {'、'.join(row_names[:6])}"
    takeaway = _slide_takeaway(slide, 1)
    return f"{start}。最关键的是把数字与“{takeaway}”对应起来。这个比较支持本页结论，但不能推出来源未报告的结论。"


def _figure_guidance(slide: Mapping[str, Any]) -> str:
    figure = slide.get("figure")
    if not isinstance(figure, Mapping):
        return ""
    caption = _clean(figure.get("caption"), _clean(figure.get("label"), "该图"))
    content = slide.get("speaker_content") if isinstance(slide.get("speaker_content"), Mapping) else {}
    guidance = _clean(content.get("visual_guidance"), "")
    lead = f"先定位图中的输入、处理阶段与输出，再观察各面板或坐标轴表达的关系；图注是“{caption}”。"
    if guidance:
        lead += f"讲解顺序可以是：{guidance}"
    return lead + "这张图用于支持本页陈述，不能替代论文未给出的定量比较。"


def render_presentation_script(deck: Mapping[str, Any]) -> str:
    slides = deck.get("slides") if isinstance(deck.get("slides"), list) else []
    if not slides or not all(isinstance(slide, Mapping) for slide in slides):
        raise ValueError("presentation script requires a non-empty deck")
    timings = _timings(deck)
    sections = [f"# {_clean(deck.get('meta', {}).get('title') if isinstance(deck.get('meta'), Mapping) else '', '汇报讲稿')} — 汇报讲稿"]
    for index, (slide, minutes) in enumerate(zip(slides, timings), start=1):
        title = _slide_title(slide, index)
        note = _clean(slide.get("speaker_notes"), _slide_takeaway(slide, index))
        guidance = _table_guidance(slide) or _figure_guidance(slide)
        points = _slide_points(slide)
        if not guidance and points:
            guidance = "本页按以下顺序展开：" + "；".join(points[:5]) + "。"
        explanation = "\n\n".join(part for part in (note, guidance) if part)
        source = _slide_source(slide)
        values = [*_key_values(slide), *_formulas(slide)]
        key_lines = [f"- {value}{f'（{source}）' if source else ''}" for value in dict.fromkeys(values)]
        if not key_lines:
            key_lines = ["- 本页没有需要单独记忆的数字或公式。"]
        if index < len(slides):
            transition = _clean(slide.get("narrative_next"), f"下一页转向“{_slide_title(slides[index], index + 1)}”。")
        else:
            transition = "用这一页收束汇报，并进入提问与讨论。"
        sections.append(f"""
## Slide {index} — {title}

**本页目的：**
{_purpose(slide, index)}

**建议时间：**
约 {minutes:.1f} 分钟

**建议讲法：**
{explanation}

**关键数字 / 公式：**
{chr(10).join(key_lines)}

**过渡：**
{transition}
""".rstrip())
    document = "\n\n".join(sections).rstrip() + "\n"
    _assert_user_safe(document)
    return document


def _important_visuals(slides: Sequence[Mapping[str, Any]]) -> list[str]:
    values: list[str] = []
    for index, slide in enumerate(slides, start=1):
        source = _slide_source(slide)
        figure = slide.get("figure")
        table = slide.get("table")
        if isinstance(figure, Mapping):
            label = _clean(figure.get("caption"), _clean(figure.get("label"), "Figure"))
        elif isinstance(table, Mapping):
            label = _clean(table.get("caption"), _clean(table.get("locator"), "Table"))
        else:
            continue
        values.append(f"- Slide {index}：{label}{f'（{source}）' if source else ''}")
    return values


def render_presentation_summary(deck: Mapping[str, Any]) -> str:
    slides = deck.get("slides") if isinstance(deck.get("slides"), list) else []
    if not slides or not all(isinstance(slide, Mapping) for slide in slides):
        raise ValueError("presentation summary requires a non-empty deck")
    title = _clean(deck.get("meta", {}).get("title") if isinstance(deck.get("meta"), Mapping) else "", _slide_title(slides[0], 1))
    takeaways = [f"- Slide {index} — {_slide_title(slide, index)}：{_slide_takeaway(slide, index)}" for index, slide in enumerate(slides, start=1)]
    narrative = " → ".join(_slide_title(slide, index) for index, slide in enumerate(slides, start=1))
    numbers: list[str] = []
    for slide in slides:
        source = _slide_source(slide)
        for value in _key_values(slide):
            line = f"- {value}{f'（{source}）' if source else ''}"
            if line not in numbers:
                numbers.append(line)
    if not numbers:
        numbers = ["- 这套 deck 没有要求单独背诵的定量数字。"]
    visuals = _important_visuals(slides) or ["- 这套 deck 没有单独使用 Figure 或 Table 页面。"]
    contribution_candidates = [
        _slide_takeaway(slide, index)
        for index, slide in enumerate(slides, start=1)
        if _compact(slide.get("role")).casefold() in {"contribution", "method-overview", "comparison", "results-table"}
    ]
    contributions = list(dict.fromkeys(contribution_candidates))[:3]
    while len(contributions) < 3:
        candidate = _slide_takeaway(slides[min(len(contributions) + 1, len(slides) - 1)], min(len(contributions) + 2, len(slides)))
        if candidate not in contributions:
            contributions.append(candidate)
        else:
            break
    limitations = []
    for index, slide in enumerate(slides, start=1):
        for value in [_slide_takeaway(slide, index), *_slide_points(slide)]:
            if _TRADEOFF_RE.search(value) and value not in limitations:
                limitations.append(value)
    if not limitations:
        limitations = ["当前 deck 未单独展示 limitation、negative result 或 trade-off。"]
    questions = []
    for slide in slides:
        raw = slide.get("questions")
        if isinstance(raw, list):
            questions.extend(_clean(value, "") for value in raw)
    questions = [value for value in dict.fromkeys(questions) if value]
    if not questions:
        questions = [
            "方法最关键的假设是什么，在哪些设置下可能失效？",
            "核心结果是否同时反映效果、成本与泛化能力？",
            "如果更换模型或数据，结论中哪些部分最需要重新验证？",
        ]
    method = next((_slide_takeaway(slide, index) for index, slide in enumerate(slides, start=1) if _compact(slide.get("role")).casefold() in {"method-overview", "experiment"}), "方法主线见逐页内容")
    result = next((_slide_takeaway(slide, index) for index, slide in enumerate(slides, start=1) if _compact(slide.get("role")).casefold() in {"results-table", "analysis", "comparison"}), "核心结果见逐页内容")
    document = f"""# 汇报速记

## 论文一句话

{title}：{_slide_takeaway(slides[1] if len(slides) > 1 else slides[0], 2 if len(slides) > 1 else 1)}

## 汇报主线

{narrative}

## 每页一句话

{chr(10).join(takeaways)}

## 必须记住的核心数字

{chr(10).join(numbers)}

## 最重要的图表

{chr(10).join(visuals)}

## 三个核心贡献

{chr(10).join(f'- {value}' for value in contributions)}

## 主要 limitation / trade-off

{chr(10).join(f'- {value}' for value in limitations)}

## 最可能被问的问题

{chr(10).join(f'- {value}' for value in questions[:5])}

## 30 秒总结

这篇论文围绕“{title}”展开。方法上，{method}；结果上，{result}。汇报时要同时说明来源支持的结论与 {limitations[0]}，避免把局部结果扩大为论文未报告的结论。
"""
    _assert_user_safe(document)
    return document.rstrip() + "\n"


def _pending_view(digest: Mapping[str, Any], review: Mapping[str, Any] | None) -> dict[str, Any]:
    candidate: Mapping[str, Any] = review or {}
    if review:
        try:
            candidate = canonicalize_review_candidate(review, digest)
        except ReviewCandidateError as exc:
            raise ValueError(f"CKPT-1 review candidate cannot be projected: {exc}") from exc
    metadata = digest.get("paper_metadata") if isinstance(digest.get("paper_metadata"), Mapping) else {}
    corrections = candidate.get("metadata_corrections") if isinstance(candidate.get("metadata_corrections"), Mapping) else {}
    title_change = corrections.get("title") if isinstance(corrections.get("title"), Mapping) else {}
    author_change = corrections.get("authors") if isinstance(corrections.get("authors"), Mapping) else {}
    semantics = candidate.get("reviewed_paper_semantics") or candidate.get("paper_semantics") or digest.get("reviewed_paper_semantics") or digest.get("paper_semantics") or {}
    return {
        "title": _clean(title_change.get("proposed"), _clean(metadata.get("title"), "未命名论文")),
        "authors": deepcopy(author_change.get("proposed") or metadata.get("authors") or []),
        "reviewed_paper_semantics": deepcopy(semantics),
        "claims": deepcopy(candidate.get("proposed_claims") or digest.get("reviewed_claims") or digest.get("claims") or []),
        "contributions": deepcopy(candidate.get("proposed_contributions") or digest.get("reviewed_contributions") or []),
        "experimental_results": deepcopy(candidate.get("proposed_experimental_results") or digest.get("reviewed_experimental_results") or []),
        "key_metrics": deepcopy(candidate.get("proposed_key_metrics") or digest.get("reviewed_key_metrics") or []),
    }


def write_paper_analysis(project_dir: str | Path, out_path: str | Path | None = None) -> Path:
    project = Path(project_dir).resolve()
    digest = _read_json(project / "digest.json", "digest")
    checkpoint_path = project / "checkpoint-1.json"
    checkpoint = _read_json(checkpoint_path, "CKPT-1 record") if checkpoint_path.is_file() else {"status": "not_created"}
    review_path = project / "ckpt1-review.json"
    review = _read_json(review_path, "CKPT-1 review") if review_path.is_file() else None
    if checkpoint.get("status") == "confirmed" and review is not None:
        try:
            view = resolve_ckpt1_view(digest, review, checkpoint)
        except CKPT1ResolvedViewError as exc:
            raise ValueError(f"confirmed CKPT-1 view cannot be projected: {exc}") from exc
    else:
        view = _pending_view(digest, review)
    unresolved: Sequence[Any] = []
    if review and isinstance(review.get("unresolved_markers"), list):
        unresolved = review["unresolved_markers"]
    elif isinstance(digest.get("flags"), list):
        unresolved = digest["flags"]
    options_path = project / "project-options.json"
    language = "zh-CN"
    if options_path.is_file():
        options = _read_json(options_path, "project options").get("options")
        if isinstance(options, Mapping):
            language = _compact(options.get("language")) or language
    reading_view_path = project / "reading-view.json"
    if reading_view_path.is_file():
        try:
            reading_view = load_reading_view(project, digest=digest)
        except ReadingViewError as exc:
            raise ValueError(f"reading view cannot be projected: {exc}") from exc
        configured_language = str(language).casefold()
        view_language = str(reading_view.get("language", "zh-CN")).casefold()
        if configured_language and view_language and configured_language != view_language:
            raise ValueError(
                f"reading view language {reading_view.get('language')} does not match project language {language}; regenerate the view in the bound project language"
            )
        document = render_reading_analysis(
            reading_view,
            ckpt1_status=_compact(checkpoint.get("status")) or "not_created",
            unresolved=unresolved,
        )
    else:
        document = render_paper_analysis(
            view,
            language=language,
            ckpt1_status=_compact(checkpoint.get("status")) or "not_created",
            unresolved=unresolved,
        )
    return _atomic_text(Path(out_path) if out_path else project / "paper-analysis.md", document)


def write_presentation_documents(project_dir: str | Path) -> dict[str, Path]:
    project = Path(project_dir).resolve()
    deck = _read_json(project / "deck.json", "deck")
    return {
        "script": _atomic_text(project / "presentation-script.md", render_presentation_script(deck)),
        "summary": _atomic_text(project / "presentation-summary.md", render_presentation_summary(deck)),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("paper-analysis", "presentation"))
    parser.add_argument("project")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    if args.mode == "paper-analysis":
        output = write_paper_analysis(args.project, args.out)
        print(f"Paper analysis -> {output}")
    else:
        if args.out:
            parser.error("--out is only valid for paper-analysis")
        outputs = write_presentation_documents(args.project)
        print(f"Presentation script -> {outputs['script']}")
        print(f"Presentation summary -> {outputs['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
