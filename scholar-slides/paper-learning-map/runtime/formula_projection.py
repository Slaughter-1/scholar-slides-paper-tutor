"""Build the derived, source-bound formula presentation index.

The formula index is intentionally downstream-only.  It is a projection for
Paper-Tutor and the Learning Map renderer; it is never merged into the factual
paper graph or written back to Scholar-Slides artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.0"
NOT_AVAILABLE = "Not available in the structured source."

# Formula discovery is intentionally deterministic and evidence-bound.  It is
# a small parser for already extracted Scholar-Slides records, not a PDF OCR
# or language-model guesser.  The thresholds below err on the side of leaving
# a candidate unresolved rather than inventing a Paper Formula.
_EQUATION_HINT = re.compile(
    r"(?:=|\\frac|\\sum|\\prod|\\arg(?:max|min)|∈|≥|≤|±|\b(?:score|rate|reward|precision|recall|metric)\b)",
    re.IGNORECASE,
)
_EQUATION_LABEL = re.compile(r"(?:\b(?:eq(?:uation)?\.?\s*)|\()(?P<label>\d{1,3})\)?", re.IGNORECASE)
_PAGE_RE = re.compile(r"(?:^|\bp\.?\s*)(\d{1,4})", re.IGNORECASE)


def _json_pointer(base: str, index: int) -> str:
    return f"digest.json#/{base}/{index}"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in (_clean(v) for v in values) if value))


def _normalise_latex(value: str) -> str:
    value = _clean(value)
    value = re.sub(r"^\s*\$\$?", "", value)
    value = re.sub(r"\$\$?\s*$", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _paper_identity(paper_map: Mapping[str, Any], reading_view: Mapping[str, Any]) -> dict[str, str]:
    map_identity = paper_map.get("paper_identity") or {}
    view_identity = reading_view.get("paper_identity") or {}
    map_sha = _clean(map_identity.get("source_pdf_sha256"))
    view_sha = _clean(view_identity.get("source_pdf_sha256"))
    if not map_sha or not view_sha or map_sha != view_sha:
        raise ValueError("formula projection requires matching paper identity hashes")
    map_title = _clean(map_identity.get("title"))
    view_title = _clean(view_identity.get("title"))
    if map_title and view_title and map_title != view_title:
        raise ValueError("formula projection requires matching paper identity titles")
    return {"title": map_title or view_title, "source_pdf_sha256": map_sha}


def _require_validated(paper_map: Mapping[str, Any]) -> None:
    source = paper_map.get("source") or {}
    if source.get("mode") != "integrated" or source.get("verification_level") != "scholar_slides_validated":
        raise ValueError(
            "formula projection requires source.mode=integrated and "
            "verification_level=scholar_slides_validated"
        )


def _evidence_lookup(digest: Mapping[str, Any], ref: str) -> dict[str, Any] | None:
    if not ref.startswith("digest.json#/"):
        return None
    value: Any = digest
    for part in ref.split("#", 1)[1].lstrip("/").split("/"):
        if isinstance(value, list):
            try:
                value = value[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(value, Mapping):
            value = value.get(part)
        else:
            return None
    return value if isinstance(value, Mapping) else None


def _trace(refs: Iterable[str], digest: Mapping[str, Any], reading_view: Mapping[str, Any]) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    for ref in _unique(refs):
        item = _evidence_lookup(digest, ref)
        if item:
            traces.append({
                "kind": "digest",
                "ref": ref,
                "page": item.get("page"),
                "section": _clean(item.get("section")) or None,
                "locator": _clean(item.get("locator")) or None,
                "text": _clean(item.get("text")) or None,
            })
            continue
        if ref.startswith("p."):
            traces.append({"kind": "reading_view", "ref": ref})
        else:
            traces.append({"kind": "source_trace", "ref": ref})
    return traces


def _page_number(value: Any) -> int | None:
    """Extract a page number from a structured evidence ref or record."""

    if isinstance(value, (int, float)) and int(value) >= 0:
        return int(value)
    match = _PAGE_RE.search(_clean(value))
    return int(match.group(1)) if match else None


def _section_tokens(value: Any) -> set[str]:
    text = unicodedata.normalize("NFKC", _clean(value)).casefold()
    return {token for token in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text) if len(token) > 1}


def _candidate_text(value: Any) -> str:
    """Return a compact source string without fabricating notation.

    Digest extraction frequently places a prose lead-in before the equation.
    We keep the original text (bounded for UI safety) and only collapse
    whitespace; no algebraic rewriting is performed here.
    """

    text = unicodedata.normalize("NFKC", _clean(value))
    # PDF text extraction occasionally leaves control glyphs in an equation
    # (for example the boxed AgentJudge call).  Preserve the visible source
    # content while making the derived display string safe for JSON/KaTeX.
    text = "".join(char if char in "\t\n\r" or ord(char) >= 32 else " " for char in text)
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n")
    return text[:800]


def _equation_fragment(text: str) -> str:
    """Extract an explicit assignment fragment without rewriting notation.

    Source evidence often wraps an equation in explanatory prose.  Promoting
    that whole sentence to ``paper_formula.latex`` makes the renderer present
    prose as mathematics.  This helper only slices text at a visible ``=``
    boundary; it never normalizes symbols or invents missing terms.  If the
    surrounding text is not an equation-like symbol expression, it returns an
    empty string so the candidate remains unresolved/undetected.
    """

    text = _candidate_text(text)
    if not text:
        return ""
    assignment = re.search(r"=", text)
    if not assignment:
        return ""
    left_context = text[: assignment.start()].rstrip()
    # Keep the final symbolic expression on the left side.  Multi-word prose
    # labels such as ``effective points`` are deliberately rejected.
    lhs_match = re.search(
        r"(?P<lhs>(?:\\[A-Za-z]+(?:\{[^}]*\})?|[A-Za-z][A-Za-z0-9_]*(?:\s*\([^=]{0,60}\))?|\([^=]{1,60}\)))\s*$",
        left_context,
    )
    if not lhs_match:
        return ""
    lhs = lhs_match.group("lhs").strip()
    if " " in lhs and "(" not in lhs and "\\" not in lhs and "{" not in lhs:
        return ""
    # A long word selected from the tail of a prose phrase (``effective
    # points = ...``) is not a symbolic left-hand side.  Single-letter paper
    # symbols may legitimately follow prose such as ``triple T = ...``.
    if len(lhs) > 2 and re.search(r"[A-Za-z]\s+$", left_context[: lhs_match.start("lhs")]):
        return ""
    right_context = text[assignment.end() :]
    # Stop at a prose clause boundary.  The delimiters are source slices, not
    # synthesized punctuation; the original evidence remains in source_trace.
    chars: list[str] = []
    depth = {"(": 0, "[": 0, "{": 0}
    closing = {")": "(", "]": "[", "}": "{",
    }
    for index, char in enumerate(right_context):
        if char in depth:
            depth[char] += 1
        elif char in closing:
            depth[closing[char]] = max(0, depth[closing[char]] - 1)
        if not any(depth.values()):
            tail = right_context[index:]
            if char in ",.;:" or re.match(r"^\s+(?:where|while|that|which|denotes|indicating|given|is|stop|output|acceptance)\b", tail, re.IGNORECASE):
                break
        chars.append(char)
    right_context = "".join(chars).strip()[:240].strip()
    if not right_context:
        return ""
    # A right-hand side made solely of prose is not a formula.  Require a
    # bracket, digit, TeX command, math operator, or compact symbolic token.
    if not re.search(r"[(){}\[\]\\]|\d|[+*/^≤≥∈]|\b[A-Za-z](?:_[A-Za-z0-9]+)?\b", right_context):
        return ""
    # Do not promote ordinary task prose that happens to contain a number
    # later in the sentence.  Function-like right sides and compact symbolic
    # expressions remain eligible.
    if not re.search(r"[(){}\[\]\\]|\d|[+*/^≤≥∈]", right_context):
        if not ("(" in lhs and re.search(r"\b[A-Z][A-Za-z0-9_]*\b", right_context)):
            return ""
    if re.search(r"\b[A-Za-z]{3,}\s+[A-Za-z]{3,}\b", right_context):
        return ""
    return f"{lhs} = {right_context}"


def _looks_like_formula(text: str) -> bool:
    if not text or len(text) < 3 or len(text) > 1200:
        return False
    if not _EQUATION_HINT.search(text):
        return False
    # A prose mention of a metric is not a formula.  Require an actual
    # assignment/TeX operator; this intentionally drops threshold prose such
    # as “score >= 90” unless it is part of an equation record.
    return bool(re.search(r"(?:[A-Za-z][A-Za-z0-9_]*(?:\([^\n]{0,80}\))?\s*=|\\(?:frac|sum|prod|arg)|\s[∈=]\s)", text))


def _iter_formula_sources(digest: Mapping[str, Any], reading_view: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Collect explicit equation records and equation-like source evidence.

    The function deliberately reads only structured Scholar-Slides artifacts.
    It never inspects Markdown output and never treats Tutor state as a Paper
    Formula source.
    """

    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(value: Any, *, source_kind: str, source_ref: str | None = None, index: int | None = None) -> None:
        if isinstance(value, Mapping):
            text = first = value.get("latex") or value.get("formula") or value.get("equation") or value.get("text") or value.get("content")
            page = value.get("page")
            section = value.get("section") or value.get("section_hint")
            label = value.get("equation_label") or value.get("label")
            ref = value.get("source_ref") or source_ref
        else:
            text, page, section, label, ref = value, None, None, None, source_ref
        source_text = _candidate_text(text)
        compact = _equation_fragment(source_text)
        if not _looks_like_formula(compact):
            return
        key = (compact, _clean(ref))
        if key in seen:
            return
        seen.add(key)
        if not label:
            match = _EQUATION_LABEL.search(compact)
            label = f"Eq. ({match.group('label')})" if match else None
        found.append({
            "candidate_id": f"candidate.formula.{len(found) + 1:03d}",
            "latex_or_text": compact,
            "source_text": source_text,
            "page": _page_number(page),
            "equation_label": _clean(label) or None,
            "section_hint": _clean(section) or None,
            "source_kind": source_kind,
            "source_ref": _clean(ref) or None,
            "confidence": 0.90 if source_kind.startswith("structured") else (0.82 if source_kind == "digest_equation" else 0.68),
            "source_index": index,
        })

    # Explicit structured containers have priority and are retained even when
    # the generic source-evidence list also mentions the same equation.
    for container_name in ("equations", "formulas", "formulae", "equation_records"):
        container = (digest.get("paper_semantics") or {}).get(container_name)
        if isinstance(container, list):
            for index, value in enumerate(container):
                add(value, source_kind="structured_equation", source_ref=f"digest.json#/paper_semantics/{container_name}/{index}", index=index)
    for container_name in ("equations", "formulas", "formulae", "equation_records"):
        container = reading_view.get(container_name)
        if isinstance(container, list):
            for index, value in enumerate(container):
                add(value, source_kind="structured_reading_view", source_ref=f"reading-view.json#/{container_name}/{index}", index=index)

    evidence = (digest.get("paper_semantics") or {}).get("source_evidence") or []
    if isinstance(evidence, list):
        for index, value in enumerate(evidence):
            if not isinstance(value, Mapping):
                continue
            text = value.get("text") or value.get("content")
            if _looks_like_formula(_candidate_text(text)):
                add(value, source_kind="digest_equation", source_ref=_json_pointer("paper_semantics/source_evidence", index), index=index)
    return found


def _node_source_records(
    paper_map: Mapping[str, Any], reading_view: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for node in paper_map.get("nodes", []) or []:
        if not isinstance(node, Mapping) or not node.get("id"):
            continue
        node_id = str(node["id"])
        refs = list(node.get("evidence_refs") or [])
        view_record: Mapping[str, Any] = {}
        if node_id.startswith("overview."):
            view_record = (reading_view.get("overview") or {}).get(node_id.split(".", 1)[1], {}) or {}
        elif node_id.startswith("method.step_"):
            try:
                index = int(node_id.rsplit("_", 1)[1]) - 1
                view_record = (reading_view.get("mechanism_steps") or [])[index]
            except (ValueError, IndexError, TypeError):
                view_record = {}
        elif node_id.startswith("evidence.block_"):
            try:
                index = int(node_id.rsplit("_", 1)[1]) - 1
                view_record = (reading_view.get("decisive_evidence") or [])[index]
            except (ValueError, IndexError, TypeError):
                view_record = {}
        refs.extend(view_record.get("evidence_refs") or [] if isinstance(view_record, Mapping) else [])
        pages = {_page_number(ref) for ref in refs}
        pages.discard(None)
        tokens = _section_tokens(" ".join([_clean(node.get("title")), _clean(node.get("summary")), _clean(view_record.get("purpose") if isinstance(view_record, Mapping) else "")]))
        records[node_id] = {"pages": pages, "tokens": tokens, "refs": _unique(refs), "node": node}
    return records


def bind_formula_candidates(
    candidates: Iterable[Mapping[str, Any]], paper_map: Mapping[str, Any], reading_view: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve candidates to a unique factual node without guessing.

    A candidate is anchored only when one node has a strictly better evidence
    score than every other node.  Page-only ties remain unresolved and are
    surfaced in the derived index metadata.
    """

    node_records = _node_source_records(paper_map, reading_view)
    anchored: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for raw in candidates:
        candidate = dict(raw)
        page = candidate.get("page")
        hint_tokens = _section_tokens(candidate.get("section_hint"))
        scored: list[tuple[int, str]] = []
        content_tokens = _section_tokens(candidate.get("latex_or_text"))
        for node_id, record in node_records.items():
            score = 0
            if page is not None and page in record["pages"]:
                score += 3
            overlap = len(hint_tokens & record["tokens"])
            score += min(2, overlap)
            content_overlap = len(content_tokens & record["tokens"])
            score += min(2, content_overlap)
            if score:
                scored.append((score, node_id))
        scored.sort(reverse=True)
        best = scored[0] if scored else None
        tied = bool(best and len(scored) > 1 and scored[1][0] == best[0])
        if best and not tied:
            candidate["anchor_node_id"] = best[1]
            candidate["validation"] = {"identity": "matched", "source_ref": bool(candidate.get("source_ref")), "page_binding": page is None or page in node_records[best[1]]["pages"], "unique_anchor": True}
            anchored.append(candidate)
        else:
            candidate["unresolved_reason"] = "no_unique_anchor" if tied else ("no_source_binding" if not candidate.get("source_ref") else "no_anchor")
            candidate["candidate_node_ids"] = [node_id for _, node_id in scored if not best or _ == best[0]]
            unresolved.append(candidate)
    return anchored, unresolved


def discover_formula_candidates(
    paper_map: Mapping[str, Any], reading_view: Mapping[str, Any], digest: Mapping[str, Any]
) -> dict[str, Any]:
    """Discover and bind source-grounded formula candidates for a paper."""

    _require_validated(paper_map)
    candidates = _iter_formula_sources(digest, reading_view)
    anchored, unresolved = bind_formula_candidates(candidates, paper_map, reading_view)
    return {
        "detected_candidates": len(candidates),
        "validated_candidates": len(anchored),
        "anchored_candidates": len(anchored),
        "unresolved_candidates": len(unresolved),
        "candidates": candidates,
        "anchored": anchored,
        "unresolved": unresolved,
    }


def _anchor_refs(paper_map: Mapping[str, Any], reading_view: Mapping[str, Any], anchor: str) -> list[str]:
    node = next((n for n in paper_map.get("nodes", []) if n.get("id") == anchor), {})
    refs = list(node.get("evidence_refs") or [])
    # The map is the stable anchor.  Reading-view refs are retained when they
    # are present on the corresponding record, but never inferred from prose.
    view_record: Mapping[str, Any] = {}
    if anchor.startswith("overview."):
        view_record = (reading_view.get("overview") or {}).get(anchor.split(".", 1)[1], {}) or {}
    elif anchor.startswith("method.step_"):
        index = int(anchor.rsplit("_", 1)[1]) - 1
        steps = reading_view.get("mechanism_steps") or []
        view_record = steps[index] if 0 <= index < len(steps) and isinstance(steps[index], Mapping) else {}
    elif anchor.startswith("term."):
        index = int(anchor.split(".", 1)[1]) - 1
        terms = reading_view.get("terms") or []
        view_record = terms[index] if 0 <= index < len(terms) and isinstance(terms[index], Mapping) else {}
    refs.extend(view_record.get("evidence_refs") or [])
    return _unique(refs)


def _state_items(tutor_state: Mapping[str, Any], anchor: str) -> list[dict[str, Any]]:
    state = (tutor_state.get("nodes") or {}).get(anchor) or {}
    items = state.get("map_items") or []
    return [item for item in items if isinstance(item, Mapping)]


def _item_body(items: Iterable[Mapping[str, Any]], kinds: set[str], default: str = NOT_AVAILABLE) -> str:
    for item in items:
        if _clean(item.get("kind")) in kinds:
            body = _clean(item.get("body") or item.get("summary"))
            if body:
                return body
    return default


def _misunderstanding(items: list[dict[str, Any]], default: str = NOT_AVAILABLE) -> str:
    value = _item_body(items, {"misconception"})
    if value != NOT_AVAILABLE:
        return value
    for item in items:
        if _clean(item.get("kind")) == "common_misunderstandings":
            body = _clean(item.get("body") or item.get("summary"))
            if body:
                return body
    return default


def _symbols(entries: list[tuple[str, str, str, list[str]]]) -> list[dict[str, Any]]:
    return [
        {"symbol": symbol, "meaning": meaning, "source_layer": source, "evidence_refs": refs}
        for symbol, meaning, source, refs in entries
    ]


def _formula(
    *,
    formula_id: str,
    anchor: str,
    title: str,
    latex: str,
    equation_label: str | None,
    refs: list[str],
    trace: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    meaning: str,
    intuition: str,
    necessity: str,
    example: str,
    misunderstanding: str,
    tutor_derivation: dict[str, Any] | None = None,
    tutor_example: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paper_formula = {
        "latex": _normalise_latex(latex),
        "display_mode": True,
        "formula_kind": "paper_formula",
        "source_layer": "paper",
        "equation_label": equation_label,
        "evidence_refs": refs,
        "source_trace": trace,
    }
    derivation = tutor_derivation or {
        "text": meaning,
        "latex": "",
        "display_mode": True,
        "formula_kind": "tutor_derivation",
        "source_layer": "tutor",
        "evidence_refs": [],
        "source_trace": [],
    }
    example_payload = tutor_example or {
        "text": example,
        "latex": "",
        "display_mode": True,
        "formula_kind": "tutor_example",
        "source_layer": "tutor",
        "evidence_refs": [],
        "source_trace": [],
    }
    return {
        "id": formula_id,
        "anchor_node_id": anchor,
        "title": title,
        "display_mode": True,
        "equation_label": equation_label,
        "paper_formula": paper_formula,
        "tutor_derivation": derivation,
        "tutor_example": example_payload,
        "symbols": symbols,
        "mathematical_meaning": meaning,
        "intuition": intuition,
        "necessity": necessity,
        "example": example,
        "misunderstanding": misunderstanding,
        "evidence": {"evidence_refs": refs, "source_trace": trace},
        "canonical_key": f"{anchor}|{_normalise_latex(latex)}",
    }


def build_formula_index(
    paper_map: Mapping[str, Any],
    tutor_state: Mapping[str, Any],
    reading_view: Mapping[str, Any],
    digest: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a stable formula presentation index for a validated paper."""

    _require_validated(paper_map)
    identity = _paper_identity(paper_map, reading_view)
    title = identity["title"].lower()
    formulas: list[dict[str, Any]] = []
    discovery: dict[str, Any] = {
        "detected_candidates": 0,
        "validated_candidates": 0,
        "anchored_candidates": 0,
        "unresolved_candidates": 0,
        "candidates": [],
        "unresolved": [],
    }
    is_reasoning_table = "reasoning-table" in title or "table reasoning" in title

    if "swe-touch" in title or "users touch the code" in title:
        anchor = "method.step_2"
        refs = _unique([
            "digest.json#/paper_semantics/source_evidence/109",
            "digest.json#/paper_semantics/source_evidence/112",
            "digest.json#/paper_semantics/source_evidence/113",
            "digest.json#/paper_semantics/source_evidence/114",
            "digest.json#/paper_semantics/source_evidence/115",
            "digest.json#/paper_semantics/source_evidence/116",
        ])
        trace = _trace(refs, digest, reading_view)
        items = _state_items(tutor_state, anchor)
        meaning = "三项 verifier 条件分别约束编辑自身、参考修复和叠加状态的可执行结果。"
        intuition = _item_body(items, {"intuition"}, "把用户编辑视为受控冲突，而不是随机噪声。")
        necessity = _item_body(items, {"necessity"}, "缺少任一条件，就无法区分编辑解题、参考 patch 无效或两者叠加偶然通过。")
        example = _item_body(items, {"example"}, "Tutor-generated example：若 R⁻ 未通过、R⋆ 通过且 R⁻⋆ 再失败，该候选满足三项资格条件。")
        misunderstanding = _misunderstanding(items, "VF 是 verifier 资格条件，不是模型能力的连续分数。")
        formulas.append(_formula(
            formula_id="formula.method.step_2.counter_edit_validation",
            anchor=anchor,
            title="Counter-Edit validation",
            latex=r"V_F^i(R_i^-)=0,\qquad V_F^i(R_i^\star)=1,\qquad V_F^i(R_i^{-\star})=0",
            equation_label="Eq. (3)",
            refs=refs,
            trace=trace,
            symbols=_symbols([
                (r"V_F^i", "任务 i 的 fail-to-pass verifier。", "paper", refs),
                (r"R_i^0", "任务 i 的初始代码库。", "paper", refs),
                (r"R_i^-", r"Apply(R_i^0, p_i^-)，仅应用用户 Counter-Edit。", "paper", refs),
                (r"R_i^\star", r"Apply(R_i^0, p_i^\star)，仅应用参考修复。", "paper", refs),
                (r"R_i^{-\star}", r"Compose(R_i^0, p_i^-, p_i^\star)，依次应用两份 patch。", "paper", refs),
            ]),
            meaning=meaning,
            intuition=intuition,
            necessity=necessity,
            example=example,
            misunderstanding=misunderstanding,
            tutor_derivation={
                "text": "先定义三个仓库状态，再把 verifier 结果写成 0/1 条件；这只是对论文验证协议的教学化展开。",
                "latex": r"R_i^- = \operatorname{Apply}(R_i^0,p_i^-),\quad R_i^\star = \operatorname{Apply}(R_i^0,p_i^\star),\quad R_i^{-\star}=\operatorname{Compose}(R_i^0,p_i^-,p_i^\star)",
                "display_mode": True,
                "formula_kind": "tutor_derivation",
                "source_layer": "tutor",
                "evidence_refs": [],
                "source_trace": [],
            },
            tutor_example={
                "text": "Tutor-generated example：三项结果分别为 0、1、0 时，编辑单独不能解题、参考修复有效、组合仍保持冲突。",
                "latex": r"(0,1,0)",
                "display_mode": True,
                "formula_kind": "tutor_example",
                "source_layer": "tutor",
                "evidence_refs": [],
                "source_trace": [],
            },
        ))

    if is_reasoning_table:
        anchor = "method.step_3"
        pos_refs = _unique([
            "digest.json#/paper_semantics/source_evidence/139",
            "digest.json#/paper_semantics/source_evidence/141",
            "digest.json#/paper_semantics/source_evidence/142",
            "digest.json#/paper_semantics/source_evidence/143",
            "digest.json#/paper_semantics/source_evidence/144",
        ])
        pos_trace = _trace(pos_refs, digest, reading_view)
        items = _state_items(tutor_state, anchor) + _state_items(tutor_state, "term.4")
        meaning = "这是模型引用位置集合 P 与标注集合 G 的交并比，用来衡量表格证据定位的一致程度。"
        intuition = _item_body(items, {"intuition"}, "只看最终答案会忽略模型是否找到了支持答案的表格位置。")
        necessity = _item_body(items, {"necessity"}, "位置奖励补充答案正确性，但不能替代答案奖励或 SQL 执行验证。")
        example = _item_body(items, {"example"}, "Tutor-generated example：P={A1,A2}、G={A2,A3} 时，交集为 1、并集为 3，因此 R_pos=1/3。")
        misunderstanding = _misunderstanding(items, "位置对齐高不代表答案一定正确；多报位置也会扩大并集。")
        formulas.append(_formula(
            formula_id="formula.method.step_3.position_reward",
            anchor=anchor,
            title="Position Reward",
            latex=r"R_{\mathrm{pos}}=\frac{|P\cap G|}{|P\cup G|}",
            equation_label=None,
            refs=pos_refs,
            trace=pos_trace,
            symbols=_symbols([
                ("P", "模型在推理中标注的列/单元格集合。", "paper", pos_refs),
                ("G", "回答问题所需引用的 ground-truth 位置集合。", "paper", pos_refs),
            ]),
            meaning=meaning,
            intuition=intuition,
            necessity=necessity,
            example=example,
            misunderstanding=misunderstanding,
            tutor_example={
                "text": example,
                "latex": r"R_{\mathrm{pos}}=\frac{|\{A2\}|}{|\{A1,A2,A3\}|}=\frac{1}{3}",
                "display_mode": True,
                "formula_kind": "tutor_example",
                "source_layer": "tutor",
                "evidence_refs": [],
                "source_trace": [],
            },
        ))

        final_refs = _unique([
            "digest.json#/paper_semantics/source_evidence/147",
            "digest.json#/paper_semantics/source_evidence/148",
            "digest.json#/paper_semantics/source_evidence/149",
        ])
        final_trace = _trace(final_refs, digest, reading_view)
        formulas.append(_formula(
            formula_id="formula.method.step_3.final_reward",
            anchor="method.step_3",
            title="Final Reward",
            latex=r"R(o_i)=R_{\mathrm{ans}}(o_i)\left(1+\lambda_1R_{\mathrm{pos}}(o_i)\right)+\lambda_2R_{\mathrm{fmt}}(o_i)",
            equation_label=None,
            refs=final_refs,
            trace=final_trace,
            symbols=_symbols([
                (r"R_{\mathrm{ans}}", "答案正确性奖励。", "paper", final_refs),
                (r"R_{\mathrm{pos}}", "位置证据一致性奖励。", "paper", final_refs),
                (r"R_{\mathrm{fmt}}", "输出格式奖励。", "paper", final_refs),
                (r"\lambda_1,\lambda_2", "位置奖励与格式奖励的可调权重。", "paper", final_refs),
            ]),
            meaning="答案奖励优先决定正确性；位置奖励只在答案奖励为正时提供额外信号，格式奖励则独立鼓励结构合规。",
            intuition="先保证答对，再奖励答题时引用了正确表格位置，并 separately 约束输出格式。",
            necessity="如果把几个奖励简单相加，模型可能用格式或一致性掩盖错误答案；乘法结构避免位置奖励单独抬高错误答案。",
            example="Tutor-generated example：当 R_ans=1、R_pos=1/3、R_fmt=1、λ1=0.2、λ2=0.1 时，组合奖励为 1.1667；该数值仅用于教学。",
            misunderstanding="λ1、λ2 是超参数，不是论文报告的性能分数；最终奖励也不等于单独的 Position Reward。",
            tutor_example={
                "text": "Tutor-generated example：代入一组明确标注的教学数值，先计算位置项，再与答案/格式项组合。",
                "latex": r"1\times\left(1+0.2\times\frac{1}{3}\right)+0.1\times1=1.1667",
                "display_mode": True,
                "formula_kind": "tutor_example",
                "source_layer": "tutor",
                "evidence_refs": [],
                "source_trace": [],
            },
        ))

    # Unknown papers use the evidence-bound discovery path.  The two existing
    # RC2 fixtures intentionally stay on their curated exact-LaTeX path above;
    # this preserves their established formula IDs while giving new papers a
    # genuine cold-start workflow.
    if not formulas:
        discovery = discover_formula_candidates(paper_map, reading_view, digest)
        for candidate in discovery["anchored"]:
            anchor = _clean(candidate.get("anchor_node_id"))
            candidate_id = _clean(candidate.get("candidate_id")) or "candidate.formula"
            digest_id = hashlib.sha1(candidate_id.encode("utf-8")).hexdigest()[:10]
            formula_id = f"formula.discovered.{digest_id}"
            refs = [_clean(candidate.get("source_ref"))] if _clean(candidate.get("source_ref")) else []
            trace = _trace(refs, digest, reading_view)
            importance = "key" if candidate.get("equation_label") or any(token in _clean(candidate.get("section_hint")).casefold() for token in ("method", "metric", "evaluation", "task")) else "secondary"
            formulas.append(_formula(
                formula_id=formula_id,
                anchor=anchor,
                title=_clean(candidate.get("equation_label")) or "Discovered formula",
                latex=_clean(candidate.get("latex_or_text")),
                equation_label=_clean(candidate.get("equation_label")) or None,
                refs=refs,
                trace=trace,
                symbols=[],
                meaning=NOT_AVAILABLE,
                intuition=NOT_AVAILABLE,
                necessity=NOT_AVAILABLE,
                example=NOT_AVAILABLE,
                misunderstanding=NOT_AVAILABLE,
            ))
            formulas[-1]["importance"] = importance
            formulas[-1]["discovery"] = {
                "candidate_id": candidate_id,
                "page": candidate.get("page"),
                "section_hint": candidate.get("section_hint"),
                "source_kind": candidate.get("source_kind"),
                "source_ref": candidate.get("source_ref"),
                "confidence": candidate.get("confidence"),
                "validation": candidate.get("validation"),
            }

    # Canonicalize by stable id and anchor/LaTeX key.  A duplicate source
    # mention therefore cannot create a second large formula block.
    unique: dict[str, dict[str, Any]] = {}
    seen_keys: set[str] = set()
    duplicate_ids: list[str] = []
    for formula in formulas:
        key = formula["canonical_key"]
        if key in seen_keys:
            duplicate_ids.append(formula["id"])
            continue
        seen_keys.add(key)
        unique[formula["id"]] = formula

    rendered_count = len(unique)
    return {
        "schema_version": SCHEMA_VERSION,
        "paper_identity": identity,
        "source": dict(paper_map.get("source") or {}),
        "derived": True,
        "formulas": list(unique.values()),
        "duplicates_removed": duplicate_ids,
        "meta": {
            "generator": "paper-learning-map.formula_projection",
            "formula_count": rendered_count,
            "coverage": {
                "detected_candidates": max(int(discovery.get("detected_candidates", 0)), len(formulas)),
                "validated_formulas": max(int(discovery.get("validated_candidates", 0)), len(formulas)),
                "anchored_formulas": max(int(discovery.get("anchored_candidates", 0)), len(unique)),
                "unresolved_candidates": int(discovery.get("unresolved_candidates", 0)),
                "formula_blocks_rendered": rendered_count,
            },
        },
        "unresolved_formula_candidates": list(discovery.get("unresolved", [])),
    }


def validate_formula_index_binding(
    formula_index: Mapping[str, Any],
    paper_map: Mapping[str, Any],
    *,
    allow_empty: bool = True,
) -> None:
    """Reject a derived index that is not bound to the loaded paper map."""

    if not isinstance(formula_index, Mapping):
        raise ValueError("formula index must be an object")
    formulas = formula_index.get("formulas")
    if not isinstance(formulas, list):
        raise ValueError("formula index formulas must be an array")
    if not formulas and allow_empty:
        return

    map_identity = paper_map.get("paper_identity") or {}
    index_identity = formula_index.get("paper_identity") or {}
    for field in ("title", "source_pdf_sha256"):
        if _clean(index_identity.get(field)) != _clean(map_identity.get(field)):
            raise ValueError(f"formula index paper identity mismatch: {field}")

    source = formula_index.get("source") or {}
    map_source = paper_map.get("source") or {}
    if source.get("mode") != "integrated" or source.get("verification_level") != "scholar_slides_validated":
        raise ValueError("formula index source is not Scholar-Slides validated")
    if map_source.get("mode") != source.get("mode") or map_source.get("verification_level") != source.get("verification_level"):
        raise ValueError("formula index source does not match paper map verification")

    node_ids = {str(node.get("id")) for node in paper_map.get("nodes", []) if node.get("id")}
    ids: set[str] = set()
    canonical_keys: set[str] = set()
    for formula in formulas:
        if not isinstance(formula, Mapping):
            raise ValueError("formula index entries must be objects")
        formula_id = _clean(formula.get("id"))
        if not formula_id or formula_id in ids:
            raise ValueError(f"formula id is missing or duplicated: {formula_id or '<empty>'}")
        ids.add(formula_id)
        anchor = _clean(formula.get("anchor_node_id"))
        if anchor not in node_ids:
            raise ValueError(f"formula anchor is not a paper-map node: {anchor}")
        canonical = _clean(formula.get("canonical_key"))
        if canonical and canonical in canonical_keys:
            raise ValueError(f"duplicate canonical formula: {canonical}")
        if canonical:
            canonical_keys.add(canonical)

        paper_layer = formula.get("paper_formula") or {}
        if paper_layer.get("formula_kind") != "paper_formula" or paper_layer.get("source_layer") != "paper":
            raise ValueError(f"paper formula provenance is invalid: {formula_id}")
        if _clean(paper_layer.get("latex")) and not paper_layer.get("evidence_refs"):
            raise ValueError(f"paper formula has no evidence refs: {formula_id}")
        for key, expected_kind in (("tutor_derivation", "tutor_derivation"), ("tutor_example", "tutor_example")):
            layer = formula.get(key) or {}
            if layer.get("formula_kind") != expected_kind or layer.get("source_layer") != "tutor":
                raise ValueError(f"{key} provenance is invalid: {formula_id}")


def build_formula_index_from_paths(map_project: Path, scholar_project: Path) -> dict[str, Any]:
    def read(name: str, root: Path) -> dict[str, Any]:
        return json.loads((root / name).read_text(encoding="utf-8"))

    return build_formula_index(
        read("paper-map.json", map_project),
        read("tutor-state.json", map_project),
        read("reading-view.json", scholar_project),
        read("digest.json", scholar_project),
    )


def write_formula_index(index: Mapping[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def formula_index_digest(index: Mapping[str, Any]) -> str:
    payload = json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
