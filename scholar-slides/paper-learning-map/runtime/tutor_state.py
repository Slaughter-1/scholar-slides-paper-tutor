from __future__ import annotations

import copy
import difflib
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "paper-learning-map" / "schemas" / "tutor-state.schema.json"
STUDY_SCHEMA_PATH = ROOT / "paper-learning-map" / "schemas" / "study-state.schema.json"
ITEM_KINDS = {"tutor_explanation", "mathematical_meaning", "intuition", "necessity", "prerequisite", "example", "analogy", "misconception", "user_question", "comprehension_check", "reader_analysis", "verification_question"}

# Question deduplication is deliberately lexical and conservative.  It is
# useful for repeated follow-up wording, but it must never pretend to provide
# embedding-level semantic search.  Generic interrogative words are ignored
# when comparing questions; domain terms and intent words remain significant.
_QUESTION_STOPWORDS = {
    "是", "的", "了", "吗", "呢", "啊", "呀", "请问", "请", "能否", "是否", "可以", "能不能",
    "什么", "为何", "为什么", "怎么", "怎么样", "如何", "请解释", "解释一下", "告诉我",
    "what", "whats", "is", "are", "the", "a", "an", "of", "to", "does", "do", "can", "could",
    "why", "how", "please", "explain", "tell", "me", "mean", "means", "meaning", "define", "definition",
}
_QUESTION_INTENT_WORDS = {
    "作用", "用途", "目的", "意义", "含义", "定义", "直觉", "角色", "purpose", "role", "use", "usage", "intuition",
    "评估", "评价", "衡量", "指标", "测量", "evaluate", "evaluation", "metric", "measure",
    "机制", "原理", "工作", "流程", "步骤", "实现", "如何做", "mechanism", "process", "work", "works", "implement",
    "区别", "差异", "比较", "对比", "difference", "compare", "versus", "vs",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _question_intent(value: str) -> str:
    """Return a coarse intent bucket used to avoid unsafe cross-question merges."""
    text = _norm(unicodedata.normalize("NFKC", str(value or "")))
    if re.search(r"为什么|为何|何故|\bwhy\b", text):
        return "why"
    if re.search(r"如何|怎么|怎样|\bhow\b", text):
        return "how"
    if re.search(r"区别|差异|比较|对比|\bdifference\b|\bcompare\b|\bversus\b|\bvs\b", text):
        return "compare"
    if re.search(r"机制|原理|流程|步骤|实现|\bmechanism\b|\bprocess\b|\bimplement", text):
        return "mechanism"
    if re.search(r"评估|评价|衡量|指标|测量|\bevaluat\w*\b|\bmetric\b|\bmeasure\b", text):
        return "evaluation"
    if re.search(r"什么|何为|含义|意义|作用|用途|目的|定义|直觉|\bwhat\b|\bdefine\b|\bmeaning\b|\bpurpose\b|\brole\b|\bintuition\b", text):
        return "definition"
    return "other"


def _canonical_question_intent(value: str) -> str:
    """Map common bilingual question phrasings to a small intent vocabulary."""

    text = _norm(unicodedata.normalize("NFKC", str(value or "")))
    subject = re.sub(r"为什么|为何|如何|怎么|怎样|是什么|何为|作用|用途|目的|意义|含义|有用|有效|工作|机制|原理|请问|请解释|what(?:'s| is)?|why|how|meaning|purpose|role|use(?:ful)?|effective", " ", text, flags=re.I)
    subject_tokens = sorted(_question_tokens(subject))
    subject_key = "_".join(subject_tokens)
    if re.search(r"为什么|为何|why|有用|有效|作用|用途|purpose|role|use|effective|什么|何为|定义|含义|意义|what|define|meaning", text, re.I):
        # “X 是什么 / X 的作用是什么 / 为什么 X 有效” are treated as the
        # same explanatory intent, but only after the same-node boundary and
        # token-overlap guards are satisfied.
        return f"explain_effective({subject_key})"
    if re.search(r"区别|差异|比较|对比|difference|compare|versus|vs", text, re.I):
        return f"compare({subject_key})"
    if re.search(r"如何|怎么|怎样|机制|原理|流程|步骤|how|mechanism|process|implement", text, re.I):
        return f"how_works({subject_key})"
    return f"other({subject_key})"


def _question_tokens(value: str) -> set[str]:
    """Tokenize mixed Chinese/English questions deterministically.

    CJK characters are kept individually because this avoids introducing a
    hidden segmentation model.  A few common multi-character interrogatives
    are removed before tokenization; domain words remain intact.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    # Remove common interrogative phrases before splitting.  This allows
    # ``What is Agent Harness?`` and ``Agent Harness 是什么？`` to meet on the
    # same content signature while preserving their definition intent bucket.
    for phrase in sorted((
        "what's", "what is", "what does", "what are", "meaning of", "define", "definition of",
        "是什么", "是什麼", "甚麼", "何为", "何謂", "什么意思", "甚麼意思", "含义是什么", "含義是什麼",
        "为什么", "为何", "如何", "怎么", "怎样", "请解释", "解释一下", "请问", "能否", "是否",
    ), key=len, reverse=True):
        text = text.replace(phrase, " ")
    # Intent words are compared separately.  Removing them from the content
    # signature lets ``X 是什么`` and ``X 的作用是什么`` share the same
    # subject while the intent guard above still keeps evaluation/mechanism
    # questions separate.
    for phrase in sorted(_QUESTION_INTENT_WORDS, key=len, reverse=True):
        text = text.replace(phrase.casefold(), " ")
    text = re.sub(r"[^\w\u3400-\u9fff]+", " ", text, flags=re.UNICODE)
    raw = re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", text)
    stop_chars = {char for word in _QUESTION_STOPWORDS if len(word) == 1 for char in word}
    tokens: set[str] = set()
    for token in raw:
        if token in _QUESTION_STOPWORDS or token in stop_chars:
            continue
        # Keep meaningful English/CJK terms.  Very short ASCII fragments are
        # retained (e.g. ``R`` or ``M`` are often paper-defined symbols).
        tokens.add(token)
    return tokens


def _question_duplicate(left: str, right: str) -> bool:
    """Conservatively identify a repeated question.

    Exact normalized text always matches.  Otherwise the intent bucket must
    agree and the content token sets must have very high overlap.  This keeps
    ``what is X``/``X 是什么`` together while leaving ``why X`` and ``how X``
    as separate learning items.
    """
    a = _norm(unicodedata.normalize("NFKC", str(left or "")))
    b = _norm(unicodedata.normalize("NFKC", str(right or "")))
    if a == b:
        return True
    if _canonical_question_intent(a) != _canonical_question_intent(b):
        return False
    ta, tb = _question_tokens(a), _question_tokens(b)
    if not ta or not tb:
        return False
    intersection = len(ta & tb)
    union = len(ta | tb)
    # At least two shared content tokens prevents short, generic questions
    # (for example ``为什么？``) from collapsing into one another.
    jaccard = intersection / union if union else 0.0
    sequence = difflib.SequenceMatcher(None, a, b).ratio()
    return intersection >= 2 and (jaccard >= 0.82 or sequence >= 0.90)


def _question_duplicate_details(left: str, right: str) -> dict[str, Any]:
    """Explain the deterministic semantic-lite decision for audit reports."""

    a = _norm(unicodedata.normalize("NFKC", str(left or "")))
    b = _norm(unicodedata.normalize("NFKC", str(right or "")))
    ta, tb = _question_tokens(a), _question_tokens(b)
    intersection = len(ta & tb)
    union = len(ta | tb)
    jaccard = intersection / union if union else 0.0
    sequence = difflib.SequenceMatcher(None, a, b).ratio()
    canonical_left = _canonical_question_intent(a)
    canonical_right = _canonical_question_intent(b)
    if a == b:
        level, reason, duplicate = "exact", "normalized_exact", True
    elif canonical_left == canonical_right and intersection >= 2 and (jaccard >= 0.82 or sequence >= 0.90):
        level, reason, duplicate = ("canonical_intent" if canonical_left.startswith(("why_effective", "explain_effective")) else "similarity_lite"), "same_canonical_intent_and_high_overlap", True
    else:
        level, reason, duplicate = "rejected", "intent_or_overlap_guard", False
    return {"duplicate": duplicate, "level": level, "reason": reason, "similarity": round(max(jaccard, sequence), 4), "token_jaccard": round(jaccard, 4), "sequence_ratio": round(sequence, 4), "canonical_intent": canonical_left if canonical_left == canonical_right else None}


def _stable_id(prefix: str, *parts: str) -> str:
    # Replace malformed console surrogate fragments rather than allowing a
    # partially decoded pipe to crash the writer before validation can run.
    material = "|".join(_norm(p) for p in parts).encode("utf-8", errors="replace")
    digest = hashlib.sha1(material).hexdigest()[:10]
    return f"{prefix}.{digest}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(raw, path)
    finally:
        if os.path.exists(raw):
            os.unlink(raw)


def _validate(state: Mapping[str, Any]) -> None:
    schema = _load_json(SCHEMA_PATH)
    errors = sorted(Draft202012Validator(schema).iter_errors(state), key=lambda error: list(error.path))
    if errors:
        path = ".".join(str(part) for part in errors[0].path) or "$"
        raise ValueError(f"invalid tutor state at {path}: {errors[0].message}")


def _validate_study_state(state: Mapping[str, Any]) -> None:
    schema = _load_json(STUDY_SCHEMA_PATH)
    errors = sorted(Draft202012Validator(schema).iter_errors(state), key=lambda error: list(error.path))
    if errors:
        path = ".".join(str(part) for part in errors[0].path) or "$"
        raise ValueError(f"invalid study state at {path}: {errors[0].message}")


class TutorStateStore:
    """Controlled writer for the downstream tutor-state layer."""

    def __init__(self, project: str | Path):
        self.project = Path(project).resolve()
        self.map_path = self.project / "paper-map.json"
        self.state_path = self.project / "tutor-state.json"
        if not self.map_path.is_file() or not self.state_path.is_file():
            raise FileNotFoundError("project must contain paper-map.json and tutor-state.json")
        self.paper_map = _load_json(self.map_path)
        self.state = _load_json(self.state_path)
        expected = self.paper_map.get("paper_identity", {}).get("source_pdf_sha256")
        actual = self.state.get("paper_identity", {}).get("source_pdf_sha256")
        if not expected or not actual or expected != actual:
            raise ValueError("tutor-state paper identity does not match paper-map")
        self.state.setdefault("nodes", {})
        self.state.setdefault("unresolved_items", [])
        self.state.setdefault("dedupe_report", {"exact_dedupes": 0, "canonical_intent_dedupes": 0, "similarity_lite_dedupes": 0, "rejected_merges": 0, "events": []})
        self.state["schema_version"] = "1.1"
        self.node_by_id = {node["id"]: node for node in self.paper_map.get("nodes", [])}

    def _load_study_for_node(self, study_path: str | Path, node_id: str) -> dict[str, Any] | None:
        """Validate and update a study state without touching unresolved Q&A."""
        study_file = Path(study_path)
        study = _load_json(study_file)
        expected = self.paper_map.get("paper_identity", {}).get("source_pdf_sha256")
        actual = study.get("paper_identity", {}).get("source_pdf_sha256")
        if not expected or not actual or expected != actual:
            raise ValueError("study-state paper identity does not match paper-map")
        _validate_study_state(study)
        study_node = study.setdefault("nodes", {}).get(node_id)
        if study_node and study_node.get("status") == "unseen":
            study_node["status"] = "learning"
            study_node["last_reviewed_at"] = _now()
            _validate_study_state(study)
            _atomic_json(study_file, study)
        return study

    def resolve_node(self, node_id: str | None = None, title: str | None = None, aliases: list[str] | None = None) -> str | None:
        if node_id:
            if node_id in self.node_by_id:
                return node_id
            return None
        terms = {_norm(title), *(_norm(alias) for alias in (aliases or []))} - {""}
        if not terms:
            return None
        candidates: set[str] = set()
        for node in self.node_by_id.values():
            values = {_norm(node.get("title")), *(_norm(tag) for tag in node.get("tags", []))}
            if values & terms:
                candidates.add(node["id"])
        return next(iter(candidates)) if len(candidates) == 1 else None

    def _resolution(self, node_id: str | None, title: str | None, aliases: list[str] | None) -> tuple[str | None, str | None, list[str]]:
        if node_id and node_id not in self.node_by_id:
            return None, "stale_node_id", []
        if node_id:
            return node_id, None, []
        terms = {_norm(title), *(_norm(alias) for alias in (aliases or []))} - {""}
        if not terms:
            return None, "no_anchor", []
        candidates = []
        for node in self.node_by_id.values():
            values = {_norm(node.get("title")), *(_norm(tag) for tag in node.get("tags", []))}
            if values & terms:
                candidates.append(node["id"])
        if len(candidates) == 1:
            return candidates[0], None, candidates
        return None, "no_unique_anchor", candidates

    def _add_unresolved(self, kind: str, title: str, body: str, reason: str, candidates: list[str]) -> dict[str, Any]:
        item = {"id": _stable_id("unresolved", kind, title, body), "kind": kind, "title": title, "body": body, "candidate_node_ids": candidates, "reason": reason, "created_at": _now()}
        existing = {entry.get("id") for entry in self.state["unresolved_items"]}
        if item["id"] not in existing:
            self.state["unresolved_items"].append(item)
        return item

    def _record_dedupe(self, event: Mapping[str, Any]) -> None:
        report = self.state.setdefault("dedupe_report", {"exact_dedupes": 0, "canonical_intent_dedupes": 0, "similarity_lite_dedupes": 0, "rejected_merges": 0, "events": []})
        level = str(event.get("level", "rejected"))
        key = {"exact": "exact_dedupes", "canonical_intent": "canonical_intent_dedupes", "similarity_lite": "similarity_lite_dedupes"}.get(level, "rejected_merges")
        report[key] = int(report.get(key, 0)) + 1
        events = report.setdefault("events", [])
        if len(events) < 500:
            events.append(dict(event))

    def upsert_tutor_item(self, *, node_id: str | None = None, title_anchor: str | None = None, aliases: list[str] | None = None, kind: str, title: str, summary: str, body: str, map_visible: bool = False, importance: str = "medium", origin: str = "full_analysis", question_id: str | None = None, tags: list[str] | None = None, related_item_ids: list[str] | None = None) -> dict[str, Any]:
        if kind not in ITEM_KINDS:
            raise ValueError(f"unsupported tutor item kind: {kind}")
        if importance not in {"low", "medium", "high"}:
            raise ValueError(f"unsupported importance: {importance}")
        if origin not in {"full_analysis", "incremental_qa"}:
            raise ValueError(f"unsupported origin: {origin}")
        resolved, reason, candidates = self._resolution(node_id, title_anchor, aliases)
        if not resolved:
            return self._add_unresolved(kind, title, body, reason or "no_anchor", candidates)
        node_state = self.state["nodes"].setdefault(resolved, {})
        now = _now()
        items = node_state.setdefault("map_items", [])
        identity = (_norm(kind), _norm(title))
        existing = next((item for item in items if (_norm(item.get("kind")), _norm(item.get("title"))) == identity), None)
        # User questions often differ only by word order or a harmless intent
        # qualifier (for example ``Agent Harness 是什么？`` vs
        # ``Agent Harness 的作用是什么？``).  Reuse the existing item only
        # when the deterministic lexical guard is satisfied.  Other question
        # wording receives its own item and remains independently answerable.
        dedupe_event: dict[str, Any] | None = None
        if existing is not None:
            dedupe_event = {"node_id": resolved, "kind": kind, "incoming_title": title, "existing_item_id": existing.get("id"), "level": "exact", "reason": "normalized_exact", "similarity": 1.0, "canonical_intent": _canonical_question_intent(title) if kind == "user_question" else None}
        if existing is None and kind == "user_question":
            for candidate in items:
                if candidate.get("kind") != "user_question":
                    continue
                variants = [candidate.get("title", ""), *(candidate.get("question_variants") or [])]
                matches = [(variant, _question_duplicate_details(title, str(variant))) for variant in variants]
                match = next(((variant, details) for variant, details in matches if details["duplicate"]), None)
                if match:
                    existing = candidate
                    variant, details = match
                    dedupe_event = {"node_id": resolved, "kind": kind, "incoming_title": title, "existing_item_id": candidate.get("id"), "matched_title": variant, **details}
                    break
                elif matches:
                    # Keep a bounded rejected-merge audit.  No cross-node
                    # comparisons are ever attempted.
                    rejected = matches[0][1]
                    self._record_dedupe({"node_id": resolved, "kind": kind, "incoming_title": title, "existing_item_id": candidate.get("id"), **rejected})
        if existing is None:
            item = {"id": _stable_id(f"tutor.{resolved}.{kind}", resolved, kind, title), "kind": kind, "title": title.strip(), "summary": summary.strip(), "body": body.strip(), "map_visible": bool(map_visible), "importance": importance, "source_layer": "tutor", "created_at": now, "updated_at": now}
            if tags:
                item["tags"] = list(dict.fromkeys(tags))
            if question_id:
                item["question_id"] = question_id
            if related_item_ids:
                item["related_item_ids"] = list(dict.fromkeys(related_item_ids))
            items.append(item)
        else:
            # Keep the canonical first title for stable rendering/IDs while
            # retaining every distinct user wording for auditability.
            if kind == "user_question" and _norm(title) != _norm(existing.get("title", "")):
                variants = existing.setdefault("question_variants", [])
                if title.strip() and title.strip() not in variants:
                    variants.append(title.strip())
            if question_id:
                question_ids = existing.setdefault("question_ids", [])
                if question_id not in question_ids:
                    question_ids.append(question_id)
            existing.update({"summary": summary.strip(), "body": body.strip(), "map_visible": bool(map_visible), "importance": importance, "source_layer": "tutor", "updated_at": now, "origin": origin})
            item = existing
        item["origin"] = origin
        if dedupe_event:
            item.setdefault("dedupe_events", []).append(dedupe_event)
            self._record_dedupe(dedupe_event)
        node_state["updated_at"] = now
        return item

    def add_structured_item(self, **kwargs: Any) -> dict[str, Any]:
        """Shared entry point used by full analysis and incremental Q&A."""
        item = self.upsert_tutor_item(**kwargs)
        if item.get("id", "").startswith("unresolved."):
            return item
        node_id = kwargs.get("node_id")
        if not node_id:
            node_id = self.resolve_node(title=kwargs.get("title_anchor"), aliases=kwargs.get("aliases"))
        if node_id in self.node_by_id:
            state = self.state["nodes"].setdefault(node_id, {})
            kind = kwargs["kind"]
            text = str(kwargs.get("body", "")).strip()
            if kind == "prerequisite" and text and text not in state.setdefault("prerequisites", []):
                state["prerequisites"].append(text)
            elif kind == "misconception" and text and text not in state.setdefault("common_misunderstandings", []):
                state["common_misunderstandings"].append(text)
            elif kind == "comprehension_check" and text and text not in state.setdefault("comprehension_checks", []):
                state["comprehension_checks"].append(text)
        return item

    def set_legacy_explanation(self, node_id: str, field: str, text: str) -> None:
        if node_id not in self.node_by_id:
            self._add_unresolved("tutor_explanation", field, text, "stale_node_id", [])
            return
        if field not in {"mathematical_meaning", "intuition", "necessity", "example", "analogy"}:
            raise ValueError(f"unsupported legacy field: {field}")
        state = self.state["nodes"].setdefault(node_id, {})
        state[field] = text.strip()
        state["updated_at"] = _now()

    def add_user_question(self, *, node_id: str | None, question: str, answer: str, title_anchor: str | None = None, important: bool = True, study_path: str | Path | None = None) -> dict[str, Any]:
        resolved, reason, candidates = self._resolution(node_id, title_anchor, None)
        if not resolved:
            return self._add_unresolved("user_question", question, answer, reason or "no_anchor", candidates)
        if study_path:
            self._load_study_for_node(study_path, resolved)
        state = self.state["nodes"].setdefault(resolved, {})
        questions = state.setdefault("questions", [])
        if question not in questions:
            questions.append(question)
        qid = _stable_id("question", resolved, question)
        return self.add_structured_item(node_id=resolved, kind="user_question", title=question, summary=answer[:120], body=answer, map_visible=important, importance="high" if important else "medium", origin="incremental_qa", question_id=qid)

    def save(self) -> None:
        _validate(self.state)
        _atomic_json(self.state_path, self.state)


def sync_records(project: str | Path, records: list[Mapping[str, Any]], origin: str = "full_analysis") -> dict[str, Any]:
    store = TutorStateStore(project)
    for record in records:
        record = dict(record)
        node_id = record.pop("node_id", None)
        title_anchor = record.pop("title_anchor", None)
        legacy_field = record.pop("legacy_field", None)
        if legacy_field:
            if not node_id:
                raise ValueError("legacy_field requires exact node_id")
            store.set_legacy_explanation(node_id, legacy_field, str(record.pop("text", record.get("body", ""))))
        elif record.get("kind") == "user_question":
            # Incremental Q&A uses the same structured stdin bridge as Full
            # Analysis.  Route questions through add_user_question so the
            # validated study-state transition (unseen -> learning only) and
            # conservative lexical dedupe remain in one implementation.
            question = str(record.pop("question", record.get("title", "")))
            answer = str(record.pop("answer", record.get("body", "")))
            important = bool(record.pop("important", True))
            if not question.strip():
                raise ValueError("user_question record requires a non-empty question")
            store.add_user_question(
                node_id=node_id,
                title_anchor=title_anchor,
                question=question,
                answer=answer,
                important=important,
                study_path=Path(project) / "study-state.json",
            )
        else:
            record.setdefault("origin", origin)
            store.add_structured_item(node_id=node_id, title_anchor=title_anchor, **record)
    store.save()
    return copy.deepcopy(store.state)
