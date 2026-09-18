#!/usr/bin/env python3
"""Validate and load the source-bound, model-authored reading view.

The reading view is a human-readable projection prepared by Codex.  This
module performs deterministic validation only; it never translates, invents,
or upgrades paper claims.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from schema_validation import create_schema_validator, resolve_skill_schema_path


class ReadingViewError(ValueError):
    """Raised when a reading view is missing, malformed, or source-stale."""


_PLACEHOLDER_TERM = "保留论文原文术语，结合对应方法或实验语境理解"
_PAGE_REF_RE = re.compile(r"^\s*(?:p(?:age)?\.?\s*)(\d+)(?:\s*[,;:]\s*(.+?))?\s*$", re.IGNORECASE)
_POINTER_REF_RE = re.compile(r"^\s*([^#]+)#(\/.*|)\s*$")

try:
    import pymupdf  # type: ignore
except ImportError:  # pragma: no cover - depends on the runtime image
    pymupdf = None  # type: ignore


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadingViewError(f"cannot read reading view {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadingViewError("reading view must be a JSON object")
    return value


def _resolve_binding(project: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (project / path).resolve()


def _digest_source_hash(digest: Mapping[str, Any] | None) -> str | None:
    if not isinstance(digest, Mapping):
        return None
    source = digest.get("source")
    if isinstance(source, Mapping):
        for key in ("source_sha256", "pdf_sha256"):
            value = source.get(key)
            if isinstance(value, str) and len(value) == 64:
                return value.lower()
    metadata = digest.get("paper_metadata")
    if isinstance(metadata, Mapping):
        value = metadata.get("pdf_sha256")
        if isinstance(value, str) and len(value) == 64:
            return value.lower()
    return None


def _digest_title(digest: Mapping[str, Any] | None) -> str | None:
    if not isinstance(digest, Mapping):
        return None
    metadata = digest.get("paper_metadata")
    if isinstance(metadata, Mapping) and isinstance(metadata.get("title"), str):
        return metadata["title"].strip()
    if isinstance(digest.get("title"), str):
        return str(digest["title"]).strip()
    return None


def _walk_texts(value: Any):
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _walk_texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_texts(child)
    elif isinstance(value, str):
        yield value


def _normalise_locator(value: str) -> str:
    """Fold a human locator to a comparison-safe token string."""
    return "".join(char.casefold() for char in value if char.isalnum())


def _locator_in_text(locator: str, text: str) -> bool:
    """Check numbered labels without matching Table 1 to Table 10."""
    numbered = re.fullmatch(r"(table|tab\.?|figure|fig\.?|section)\s+(\d+(?:\.\d+)*)", locator, re.I)
    if numbered:
        kind, number = numbered.groups()
        label = r"(?:table|tab\.?)" if kind.lower().startswith("tab") else r"(?:figure|fig\.?)"
        if kind.lower() == "section":
            return bool(re.search(r"(?:\bsection\s+|(?m:^)[ \t]*)" + re.escape(number) + r"(?![\d.])\s+\S", text, re.I))
        return bool(re.search(r"\b" + label + r"\s*" + re.escape(number) + r"(?!\d)", text, re.I))
    return _normalise_locator(locator) in _normalise_locator(text)


def _iter_evidence_records(value: Any):
    """Yield digest mappings that carry a source page and evidence metadata."""
    if isinstance(value, Mapping):
        page = value.get("page", value.get("source_page"))
        if isinstance(page, int):
            yield value
        for child in value.values():
            yield from _iter_evidence_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_evidence_records(child)


def _digest_locator_matches(digest: Mapping[str, Any] | None, page: int, locator: str) -> bool:
    if not isinstance(digest, Mapping):
        return False
    needle = _normalise_locator(locator)
    if not needle:
        return True
    for record in _iter_evidence_records(digest):
        record_page = record.get("page", record.get("source_page"))
        if record_page != page:
            continue
        for key in ("section", "locator", "label", "id", "source_ref", "caption", "figure_table_equation"):
            value = record.get(key)
            if isinstance(value, str):
                haystack = _normalise_locator(value)
                if haystack and needle == haystack:
                    return True
    return False


def _digest_evidence_ids(digest: Mapping[str, Any] | None) -> set[str]:
    ids: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key.casefold() in {"id", "evidence_id", "ref_id", "source_id", "locator_id"} and isinstance(child, str):
                    ids.add(child.strip())
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(digest)
    return ids


def _resolve_json_pointer(document: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON pointer, raising KeyError for missing paths."""
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise KeyError(pointer)
    return current


def _source_page_texts(source_path: Path | None) -> list[str] | None:
    if source_path is None or pymupdf is None:
        return None
    try:
        document = pymupdf.open(str(source_path))
        try:
            return [page.get_text() for page in document]
        finally:
            document.close()
    except Exception:  # The caller must reject page references when parsing fails.
        return None


def _validate_evidence_refs(
    payload: Mapping[str, Any],
    project: Path,
    *,
    digest: Mapping[str, Any] | None,
    bound_sources: list[Path],
    paper_source: Path | None,
) -> None:
    """Reject references that cannot resolve to the bound digest or source PDF."""
    refs: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            raw_refs = value.get("evidence_refs")
            if isinstance(raw_refs, list):
                refs.extend(item.strip() for item in raw_refs if isinstance(item, str) and item.strip())
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(payload)
    page_texts = _source_page_texts(paper_source)
    known_ids = _digest_evidence_ids(digest)
    for reference in dict.fromkeys(refs):
        page_match = _PAGE_REF_RE.match(reference)
        if page_match:
            page = int(page_match.group(1))
            if page_texts is None:
                raise ReadingViewError(f"cannot verify page reference: bound paper PDF is unreadable: {reference}")
            if page < 1:
                raise ReadingViewError(f"reading view evidence reference has an invalid page: {reference}")
            if page_texts is not None and page > len(page_texts):
                raise ReadingViewError(f"reading view evidence reference points past the PDF: {reference}")
            locator = (page_match.group(2) or "").strip()
            if locator and page_texts is not None:
                page_text = _normalise_locator(page_texts[page - 1]) if page <= len(page_texts) else ""
                locator_token = _normalise_locator(locator)
                if (
                    locator_token
                    and not _locator_in_text(locator, page_texts[page - 1])
                    and not _digest_locator_matches(digest, page, locator)
                ):
                    raise ReadingViewError(f"reading view evidence locator cannot be resolved: {reference}")
            continue

        pointer_match = _POINTER_REF_RE.match(reference)
        if pointer_match and pointer_match.group(1).strip().casefold().endswith("digest.json"):
            if digest is None:
                raise ReadingViewError(f"reading view digest pointer requires a digest: {reference}")
            pointer_path = _resolve_binding(project, pointer_match.group(1).strip())
            digest_path = (project / "digest.json").resolve()
            if pointer_path != digest_path or pointer_path not in bound_sources:
                raise ReadingViewError(f"reading view digest pointer is not bound to the project digest: {reference}")
            try:
                _resolve_json_pointer(digest, pointer_match.group(2))
            except KeyError as exc:
                raise ReadingViewError(f"reading view digest pointer cannot be resolved: {reference}") from exc
            continue

        if reference in known_ids:
            continue
        raise ReadingViewError(f"reading view evidence reference cannot be resolved: {reference}")


def _validate_semantic_units(payload: Mapping[str, Any]) -> None:
    if any(_PLACEHOLDER_TERM in text for text in _walk_texts(payload.get("terms", []))):
        raise ReadingViewError("reading view contains a placeholder term explanation")

    def check_record(record: Mapping[str, Any], label: str) -> None:
        claim_type = record.get("claim_type")
        availability = record.get("availability")
        refs = record.get("evidence_refs")
        if availability == "supported" and claim_type == "paper_fact" and not refs:
            raise ReadingViewError(f"supported Paper Fact {label} has no evidence reference")
        if isinstance(refs, list) and any(not isinstance(item, str) or not item.strip() for item in refs):
            raise ReadingViewError(f"reading view has an empty evidence reference in {label}")

    overview = payload.get("overview", {})
    if isinstance(overview, Mapping):
        for name, record in overview.items():
            if isinstance(record, Mapping):
                check_record(record, f"overview.{name}")
    for name in ("mechanism_steps", "argument_chain", "decisive_evidence", "terms", "takeaways"):
        values = payload.get(name, [])
        if isinstance(values, list):
            for index, record in enumerate(values):
                if isinstance(record, Mapping):
                    check_record(record, f"{name}[{index}]")


def validate_reading_view(
    payload: Mapping[str, Any],
    project_dir: str | Path,
    *,
    digest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a reading view and all declared source bindings."""
    if not isinstance(payload, Mapping):
        raise ReadingViewError("reading view must be an object")
    try:
        schema_path = resolve_skill_schema_path("reading-view.schema.json", anchor=__file__)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = sorted(create_schema_validator(schema).iter_errors(dict(payload)), key=lambda error: list(error.path))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ReadingViewError(f"cannot load reading-view schema: {exc}") from exc
    if errors:
        path = ".".join(str(item) for item in errors[0].path) or "."
        raise ReadingViewError(f"reading view schema error at {path}: {errors[0].message}")

    project = Path(project_dir).resolve()
    identity = payload["paper_identity"]
    identity_hash = str(identity["source_pdf_sha256"]).lower()
    title = str(identity["title"]).strip()
    digest_hash = _digest_source_hash(digest)
    if digest_hash and digest_hash != identity_hash:
        raise ReadingViewError("reading view paper identity does not match digest source PDF")
    digest_title = _digest_title(digest)
    if digest_title and not digest_hash and digest_title != title:
        raise ReadingViewError("reading view paper title does not match digest title")

    binding_hashes: set[str] = set()
    bound_sources: list[Path] = []
    paper_source: Path | None = None
    for binding in payload["source_bindings"]:
        target = _resolve_binding(project, binding["path"])
        if not target.is_file():
            raise ReadingViewError(f"reading view source binding does not exist: {target}")
        actual = _sha256(target)
        expected = str(binding["sha256"]).lower()
        if actual != expected:
            raise ReadingViewError(f"reading view source binding is stale: {target}")
        binding_hashes.add(actual)
        bound_sources.append(target)
        if actual == identity_hash and target.suffix.casefold() == ".pdf":
            paper_source = target
    digest_path = project / "digest.json"
    if digest is not None and digest_path.is_file():
        digest_bound = any(
            _resolve_binding(project, binding["path"]) == digest_path
            for binding in payload["source_bindings"]
        )
        if not digest_bound:
            raise ReadingViewError("reading view must bind the project digest when digest validation is requested")
    if paper_source is None:
        raise ReadingViewError("reading view does not bind the paper source PDF")

    _validate_semantic_units(payload)
    _validate_evidence_refs(payload, project, digest=digest, bound_sources=bound_sources, paper_source=paper_source)
    return json.loads(json.dumps(payload, ensure_ascii=False))


def load_reading_view(
    project_dir: str | Path,
    *,
    digest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read and validate ``reading-view.json`` from a project directory."""
    project = Path(project_dir).resolve()
    path = project / "reading-view.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return validate_reading_view(_read_json(path), project, digest=digest)
