#!/usr/bin/env python3
"""Generic, fail-closed evidence locator parsing and verification.

The resolver deliberately keeps three page coordinate systems separate:

* ``pdf_page_index`` is zero based and addresses the PDF object;
* ``printed_page_label`` is the label printed by the paper (when available);
* ``source_page_reference`` is the human-facing, one-based ``p. N`` reference
  used by Scholar-Slides source evidence.

Parsing is intentionally independent from verification.  A syntactically
valid locator is never accepted until the requested page/structure has a
verified text span in the bound source (or in a digest structure that was
derived from that source).  Ambiguous and unresolved results are retained as
such and are never reduced to a guessed page.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence


STATUSES = {"exact", "normalized", "fuzzy", "partial", "ambiguous", "unresolved"}

_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2212"
_PAGE_PREFIX = re.compile(
    r"^\s*(?P<prefix>pdf\s+page\s+index|pdf\s+page|source\s+page|printed\s+page|pages?|pp?\.)\s*"
    r"(?P<first>\d+)\s*(?:(?P<dash>[-\u2010\u2011\u2012\u2013\u2014\u2212]|to)\s*(?P<last>\d+))?"
    r"(?P<tail>.*)$",
    re.IGNORECASE,
)
_SECTION_PREFIX = re.compile(r"^\s*(?:section|sec\.?|§)\s*(?P<value>[A-Za-z]?\d+(?:\.\d+)*)(?:\s*[:.)-]\s*|\s+)?(?P<title>.*)$", re.I)
_FIGURE_PREFIX = re.compile(r"^\s*(?:figure|fig\.?)\s*(?P<value>[A-Za-z]?\d+(?:\.\d+)*)(?:\s*[:.)-]\s*|\s+)?(?P<title>.*)$", re.I)
_TABLE_PREFIX = re.compile(r"^\s*(?:table|tab\.?)\s*(?P<value>[A-Za-z]?\d+(?:\.\d+)*)(?:\s*[:.)-]\s*|\s+)?(?P<title>.*)$", re.I)
_EQUATION_PREFIX = re.compile(r"^\s*(?:equation|eq\.?)\s*\(?\s*(?P<value>[A-Za-z]?\d+(?:\.\d+)*)\s*\)?(?:\s*[:.)-]\s*|\s+)?(?P<title>.*)$", re.I)
_APPENDIX_PREFIX = re.compile(r"^\s*(?:appendix|app\.?)\s*(?P<value>[A-Za-z]?\d*)(?:\s*[:.)-]\s*|\s+)?(?P<title>.*)$", re.I)
_NUMBERED_HEADING = re.compile(r"^\s*(?P<number>\d+(?:\.\d+)*)(?:[.)]|\s+)\s*(?P<title>[^.]{1,160}?)\s*$")
_SECTION_HEADING = re.compile(r"^\s*(?:section|sec\.?)\s*(?P<number>[A-Za-z]?\d+(?:\.\d+)*)\s*[:.)-]?\s*(?P<title>[^.]{0,160})\s*$", re.I)
_FIGURE_LINE = re.compile(r"^\s*(?:figure|fig\.?)\s*(?P<number>[A-Za-z]?\d+(?:\.\d+)*)\b(?P<rest>.*)$", re.I)
_TABLE_LINE = re.compile(r"^\s*(?:table|tab\.?)\s*(?P<number>[A-Za-z]?\d+(?:\.\d+)*)\b(?P<rest>.*)$", re.I)
_EQUATION_LINE = re.compile(r"^\s*(?:equation|eq\.?)\s*\(?\s*(?P<number>[A-Za-z]?\d+(?:\.\d+)*)\s*\)?(?P<rest>.*)$", re.I)
_APPENDIX_LINE = re.compile(r"^\s*(?:appendix|app\.?)\s*(?P<number>[A-Za-z]?\d*)\b(?P<rest>.*)$", re.I)


def normalize_text(value: str) -> str:
    """Normalize Unicode punctuation/whitespace for comparison only."""
    value = unicodedata.normalize("NFKC", str(value))
    value = value.translate(str.maketrans({_DASHES[i]: "-" for i in range(len(_DASHES))}))
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip().casefold()


def normalize_token(value: str) -> str:
    return "".join(ch for ch in normalize_text(value) if ch.isalnum())


@dataclass(frozen=True)
class LocatorComponent:
    kind: str
    value: str
    raw: str
    title: str = ""

    def as_dict(self) -> dict[str, Any]:
        result = {"kind": self.kind, "value": self.value, "raw": self.raw}
        if self.title:
            result["title"] = self.title
        return result


@dataclass(frozen=True)
class ParsedLocator:
    raw: str
    components: tuple[LocatorComponent, ...]
    parse_status: str = "exact"
    parse_errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "components": [item.as_dict() for item in self.components],
            "parse_status": self.parse_status,
            "parse_errors": list(self.parse_errors),
        }


@dataclass
class StructuralEntry:
    kind: str
    value: str
    page_index: int
    line_index: int
    text: str
    number: str = ""
    title: str = ""
    source: str = "pdf_text"

    @property
    def token(self) -> str:
        return normalize_token(self.value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "number": self.number,
            "title": self.title,
            "page_index": self.page_index,
            "source": self.source,
            "text": self.text,
        }


@dataclass
class DocumentIndex:
    page_texts: list[str]
    printed_page_labels: dict[str, list[int]] = field(default_factory=dict)
    source_page_references: dict[int, list[int]] = field(default_factory=dict)
    structures: list[StructuralEntry] = field(default_factory=list)
    digest: Mapping[str, Any] | None = None

    def page_candidates(self, component: LocatorComponent) -> list[int]:
        if component.kind == "source_page_reference":
            return list(self.source_page_references.get(int(component.value), []))
        if component.kind == "pdf_page_index":
            index = int(component.value)
            return [index] if 0 <= index < len(self.page_texts) else []
        if component.kind == "printed_page_label":
            return list(self.printed_page_labels.get(normalize_text(component.value), []))
        return list(range(len(self.page_texts)))


@dataclass
class Resolution:
    raw: str
    parsed: ParsedLocator
    status: str = "unresolved"
    confidence: float = 0.0
    method: list[str] = field(default_factory=list)
    pdf_page_indices: list[int] = field(default_factory=list)
    printed_page_labels: list[str] = field(default_factory=list)
    source_page_references: list[int] = field(default_factory=list)
    matched_components: list[dict[str, Any]] = field(default_factory=list)
    evidence_span: dict[str, Any] | None = None
    failure_reason_codes: list[str] = field(default_factory=list)
    unresolved_components: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_candidates: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "parsed": self.parsed.as_dict(),
            "status": self.status,
            "confidence": round(float(self.confidence), 4),
            "method": list(self.method),
            "pdf_page_indices": list(self.pdf_page_indices),
            "printed_page_labels": list(self.printed_page_labels),
            "source_page_references": list(self.source_page_references),
            "matched_components": list(self.matched_components),
            "evidence_span": self.evidence_span,
            "failure_reason_codes": list(dict.fromkeys(self.failure_reason_codes)),
            "unresolved_components": list(self.unresolved_components),
            "ambiguous_candidates": list(self.ambiguous_candidates),
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]


def _split_components(value: str) -> list[str]:
    # Commas/semicolons delimit mixed locators.  Keep a colon because it is
    # often part of a figure/table caption or section title.
    return [part.strip() for part in re.split(r"\s*[;,]\s*", value) if part.strip()]


def _component_from_segment(segment: str) -> LocatorComponent:
    value = segment.strip()
    match = _SECTION_PREFIX.match(value)
    if match:
        number = match.group("value")
        title = match.group("title").strip()
        return LocatorComponent("section", number, segment, title)
    # ``section Contributions`` is a valid title locator even when the paper
    # does not number that heading.  Keep the title as the value so it can be
    # verified as a page-local span without guessing a section number.
    title_match = re.match(r"^\s*(?:section|sec\.?)\s*[:\-]?\s*(?P<title>[^,;]+?)\s*$", value, re.I)
    if title_match:
        title = title_match.group("title").strip()
        return LocatorComponent("section", title, segment)
    for kind, pattern in (
        ("figure", _FIGURE_PREFIX),
        ("table", _TABLE_PREFIX),
        ("equation", _EQUATION_PREFIX),
        ("appendix", _APPENDIX_PREFIX),
    ):
        match = pattern.match(value)
        if match:
            number = match.group("value") or ""
            return LocatorComponent(kind, number, segment, match.group("title").strip())
    return LocatorComponent("section", value, segment)


def parse_locator(raw: str) -> ParsedLocator:
    """Parse a human locator without resolving it against a document."""
    if not isinstance(raw, str) or not raw.strip():
        return ParsedLocator(str(raw), (), "unresolved", ("EMPTY_LOCATOR",))
    original = raw.strip()
    components: list[LocatorComponent] = []
    remainder = original
    normalized_hint = False
    page_match = _PAGE_PREFIX.match(original)
    if page_match:
        prefix = normalize_text(page_match.group("prefix"))
        normalized_hint = prefix not in {"p.", "pp."}
        first = int(page_match.group("first"))
        last = page_match.group("last")
        if last is not None:
            last_int = int(last)
            if last_int < first:
                return ParsedLocator(original, (), "unresolved", ("INVALID_PAGE_RANGE",))
            page_value = f"{first}-{last_int}"
            if prefix.startswith("pdf page index"):
                page_kind = "pdf_page_index"
            elif prefix.startswith("printed page"):
                page_kind = "printed_page_label"
            else:
                page_kind = "source_page_reference"
        elif prefix.startswith("pdf page index"):
            page_value = str(first)
            page_kind = "pdf_page_index"
        elif prefix.startswith("printed page"):
            page_value = str(first)
            page_kind = "printed_page_label"
        elif prefix.startswith("source page"):
            page_value = str(first)
            page_kind = "source_page_reference"
        else:
            page_value = str(first)
            page_kind = "source_page_reference"
        components.append(LocatorComponent(page_kind, page_value, page_match.group(0)[: page_match.start("tail")].strip()))
        remainder = page_match.group("tail").strip()
        remainder = re.sub(r"^[,:;\-–—]+\s*", "", remainder)
    if remainder:
        components.extend(_component_from_segment(part) for part in _split_components(remainder))
    if not components:
        return ParsedLocator(original, (), "unresolved", ("UNRECOGNIZED_LOCATOR",))
    return ParsedLocator(original, tuple(components), "normalized" if normalized_hint or normalize_text(original) != original.casefold() else "exact")


def _printed_label_from_page(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines[-8:]):
        if re.fullmatch(r"[A-Za-z0-9IVXLCDMivxlcdm]{1,8}", line):
            # Avoid treating a short heading as a page label.
            if line.casefold() not in {"intro", "method", "results", "table", "figure"}:
                return line
    return None


def _entry_key(entry: StructuralEntry) -> tuple[str, str, int, str]:
    # A digest record and the corresponding PDF caption commonly carry
    # different descriptive text for the same structural item.  They must be
    # one candidate, otherwise a valid locator would become falsely
    # ambiguous.  Keep the PDF text when both are present because it is the
    # span that can be verified directly.
    return (entry.kind, normalize_token(entry.value), entry.page_index, "")


def _add_entry(entries: list[StructuralEntry], entry: StructuralEntry) -> None:
    for index, existing in enumerate(entries):
        if _entry_key(existing) != _entry_key(entry):
            continue
        if existing.source == "digest" and entry.source == "pdf_text":
            entries[index] = entry
        return
    entries.append(entry)


def _structure_entries(page_texts: Sequence[str]) -> list[StructuralEntry]:
    entries: list[StructuralEntry] = []
    for page_index, text in enumerate(page_texts):
        for line_index, raw_line in enumerate(text.splitlines()):
            line = raw_line.strip()
            if not line:
                continue
            figure = _FIGURE_LINE.match(line)
            if figure:
                number = figure.group("number")
                _add_entry(entries, StructuralEntry("figure", number, page_index, line_index, line, number, figure.group("rest").strip()))
                continue
            table = _TABLE_LINE.match(line)
            if table:
                number = table.group("number")
                _add_entry(entries, StructuralEntry("table", number, page_index, line_index, line, number, table.group("rest").strip()))
                continue
            equation = _EQUATION_LINE.match(line)
            if equation:
                number = equation.group("number")
                _add_entry(entries, StructuralEntry("equation", number, page_index, line_index, line, number, equation.group("rest").strip()))
                continue
            appendix = _APPENDIX_LINE.match(line)
            if appendix and (appendix.group("number") or line.casefold().startswith("appendix")):
                number = appendix.group("number") or ""
                _add_entry(entries, StructuralEntry("appendix", number, page_index, line_index, line, number, appendix.group("rest").strip()))
                continue
            section = _SECTION_HEADING.match(line)
            if section:
                number = section.group("number")
                title = section.group("title").strip()
                _add_entry(entries, StructuralEntry("section", number, page_index, line_index, line, number, title))
                continue
            numbered = _NUMBERED_HEADING.match(line)
            if numbered and len(line) <= 140:
                number = numbered.group("number")
                title = numbered.group("title").strip()
                _add_entry(entries, StructuralEntry("section", title, page_index, line_index, line, number, title))
                continue
            # A bare heading is accepted only when it is a short, punctuation-
            # free line.  This avoids turning a prose mention into a section.
            if len(line) <= 100 and len(line.split()) <= 12 and not re.search(r"[.!?]$", line):
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9/& _-]{1,100}", line):
                    _add_entry(entries, StructuralEntry("section", line, page_index, line_index, line, "", line))
    return entries


def _iter_digest_records(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if isinstance(value.get("page", value.get("source_page")), int):
            yield value
        for child in value.values():
            yield from _iter_digest_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_digest_records(child)


def _digest_entries(digest: Mapping[str, Any] | None, page_count: int) -> list[StructuralEntry]:
    entries: list[StructuralEntry] = []
    if not isinstance(digest, Mapping):
        return entries
    for record in _iter_digest_records(digest):
        page = record.get("page", record.get("source_page"))
        if not isinstance(page, int) or not 1 <= page <= page_count:
            continue
        page_index = page - 1
        for kind in ("figure", "table", "equation", "appendix", "section"):
            value: Any = record.get(kind)
            if value is None and kind in {"figure", "table", "equation"}:
                value = record.get(f"{kind}_id")
            if value is None:
                value = record.get("label") if kind in {"figure", "table"} else None
            if not isinstance(value, str) or not value.strip():
                continue
            title = ""
            for key in ("caption", "title", "locator", "source_ref"):
                if isinstance(record.get(key), str):
                    title = str(record[key]).strip()
                    break
            _add_entry(entries, StructuralEntry(kind, value.strip(), page_index, -1, title or value.strip(), value.strip(), title, "digest"))
    return entries


def build_document_index(
    page_texts: Sequence[str],
    *,
    printed_page_labels: Mapping[Any, Any] | Sequence[Any] | None = None,
    source_page_references: Mapping[Any, Any] | None = None,
    digest: Mapping[str, Any] | None = None,
) -> DocumentIndex:
    """Build a structural index without making any locator decisions."""
    texts = [str(value or "") for value in page_texts]
    labels: dict[str, list[int]] = {}
    if printed_page_labels is None:
        for index, text in enumerate(texts):
            label = _printed_label_from_page(text)
            if label is not None:
                labels.setdefault(normalize_text(label), []).append(index)
    elif isinstance(printed_page_labels, Mapping):
        for key, value in printed_page_labels.items():
            indices = value if isinstance(value, (list, tuple, set)) else [value]
            for index in indices:
                if isinstance(index, int) and 0 <= index < len(texts):
                    labels.setdefault(normalize_text(str(key)), []).append(index)
    else:
        for index, label in enumerate(printed_page_labels):
            if label is not None and index < len(texts):
                labels.setdefault(normalize_text(str(label)), []).append(index)
    references: dict[int, list[int]] = {}
    if source_page_references:
        for key, value in source_page_references.items():
            indices = value if isinstance(value, (list, tuple, set)) else [value]
            for index in indices:
                if isinstance(index, int) and 0 <= index < len(texts):
                    references.setdefault(int(key), []).append(index)
    else:
        references = {index + 1: [index] for index in range(len(texts))}
    entries = _structure_entries(texts)
    for entry in _digest_entries(digest, len(texts)):
        _add_entry(entries, entry)
    return DocumentIndex(texts, labels, references, entries, digest)


def _page_components(parsed: ParsedLocator) -> list[LocatorComponent]:
    return [component for component in parsed.components if component.kind in {"source_page_reference", "pdf_page_index", "printed_page_label"}]


def _range_page_candidates(component: LocatorComponent, index: DocumentIndex) -> list[int]:
    if "-" not in component.value:
        return index.page_candidates(component)
    first, last = (int(part) for part in component.value.split("-", 1))
    result: list[int] = []
    for value in range(first, last + 1):
        result.extend(index.page_candidates(LocatorComponent(component.kind, str(value), component.raw)))
    return list(dict.fromkeys(result))


def _structure_matches(component: LocatorComponent, index: DocumentIndex, pages: Sequence[int]) -> list[StructuralEntry]:
    candidates: list[StructuralEntry] = []
    wanted = normalize_token(component.value)
    title_wanted = normalize_token(component.title) if component.title else ""
    for entry in index.structures:
        if pages and entry.page_index not in pages:
            continue
        if entry.kind != component.kind:
            continue
        number_token = normalize_token(entry.number or entry.value)
        value_token = normalize_token(entry.value)
        title_token = normalize_token(entry.title)
        if component.kind in {"figure", "table", "equation", "appendix"}:
            if wanted and wanted not in {number_token, value_token} and value_token not in {wanted}:
                continue
            if title_wanted and title_wanted not in title_token and title_wanted not in normalize_token(entry.text):
                continue
            candidates.append(entry)
        else:
            # A numbered section can be addressed by number, title, or both.
            if wanted and wanted not in {number_token, value_token, title_token}:
                continue
            if title_wanted and title_wanted not in {title_token, value_token}:
                continue
            candidates.append(entry)
    if candidates:
        return candidates
    # Conservative fuzzy matching applies only to section headings and only
    # to a unique high-scoring candidate.  Captions and labels never guess.
    if component.kind == "section" and wanted:
        scored: list[tuple[float, StructuralEntry]] = []
        for entry in index.structures:
            if entry.kind != "section" or (pages and entry.page_index not in pages):
                continue
            score = difflib.SequenceMatcher(None, wanted, normalize_token(entry.value)).ratio()
            if score >= 0.86:
                scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored and (len(scored) == 1 or scored[0][0] > scored[1][0] + 0.05):
            return [scored[0][1]]
    return []


def _find_text_spans(text: str, needle: str) -> list[dict[str, Any]]:
    wanted = normalize_text(needle)
    if not wanted:
        return []
    spans: list[dict[str, Any]] = []
    for line_index, line in enumerate(text.splitlines()):
        normalized = normalize_text(line)
        if wanted in normalized:
            spans.append({"line_index": line_index, "text": line.strip(), "match": needle})
    return spans


def _component_display(component: LocatorComponent) -> str:
    if component.title:
        return f"{component.kind}:{component.value}:{component.title}"
    return f"{component.kind}:{component.value}"


def resolve_locator(raw: str, index: DocumentIndex) -> Resolution:
    """Resolve syntactic components against a document index.

    This function may return ``partial`` before span verification when a page
    is exact but a free-text section label has no standalone heading.  Callers
    must invoke :func:`verify_evidence_span` before accepting that result.
    """
    parsed = parse_locator(raw)
    result = Resolution(raw=str(raw), parsed=parsed)
    if parsed.parse_errors:
        result.failure_reason_codes.extend(parsed.parse_errors)
        return result
    pages: list[int] = list(range(len(index.page_texts)))
    page_parts = _page_components(parsed)
    if page_parts:
        page_sets = [_range_page_candidates(part, index) for part in page_parts]
        if any(not value for value in page_sets):
            for component, candidates in zip(page_parts, page_sets):
                if not candidates:
                    reason = "PAGE_LABEL_AMBIGUOUS" if component.kind == "printed_page_label" else "PAGE_NOT_FOUND"
                    result.failure_reason_codes.append(reason)
                    result.unresolved_components.append(component.as_dict())
            return result
        pages = sorted(set.intersection(*(set(values) for values in page_sets)))
        if not pages:
            result.status = "ambiguous"
            result.failure_reason_codes.append("MIXED_COMPONENT_MISMATCH")
            result.ambiguous_candidates = [{"component": part.as_dict(), "pages": values} for part, values in zip(page_parts, page_sets)]
            return result
        if len(pages) > 1 and not any("-" in part.value for part in page_parts):
            result.status = "ambiguous"
            result.failure_reason_codes.append("PAGE_REFERENCE_AMBIGUOUS")
            result.ambiguous_candidates = [{"pdf_page_index": page} for page in pages]
            return result
        result.method.append("page_exact")
        result.pdf_page_indices = pages
        result.source_page_references = [page + 1 for page in pages]
        result.printed_page_labels = [
            label for label, values in index.printed_page_labels.items() if any(page in values for page in pages)
        ]
    structural_parts = [component for component in parsed.components if component.kind not in {"source_page_reference", "pdf_page_index", "printed_page_label"}]
    matched: list[StructuralEntry] = []
    for component in structural_parts:
        candidates = _structure_matches(component, index, pages)
        if len(candidates) == 1:
            matched.append(candidates[0])
            result.matched_components.append({"requested": component.as_dict(), "matched": candidates[0].as_dict()})
            exact_value = normalize_token(component.value) in {
                normalize_token(candidates[0].number or candidates[0].value),
                normalize_token(candidates[0].title),
            }
            result.method.append(f"{component.kind}_{'exact' if exact_value else 'fuzzy'}")
            if not exact_value:
                result.status = "fuzzy"
            if not result.pdf_page_indices:
                result.pdf_page_indices = [candidates[0].page_index]
                result.source_page_references = [candidates[0].page_index + 1]
        elif len(candidates) > 1:
            result.status = "ambiguous"
            result.failure_reason_codes.append(f"{component.kind.upper()}_AMBIGUOUS")
            result.ambiguous_candidates.extend(candidate.as_dict() for candidate in candidates)
        else:
            result.failure_reason_codes.append(f"{component.kind.upper()}_NOT_FOUND")
            if pages and any(
                entry.kind == component.kind and _structure_matches(component, index, [])
                for entry in index.structures
            ):
                result.failure_reason_codes.append("MIXED_COMPONENT_MISMATCH")
            result.unresolved_components.append(component.as_dict())
    if result.status == "ambiguous":
        return result
    if structural_parts and not matched and result.pdf_page_indices:
        # Leave a page-local free-text section as partial until the required
        # span is checked.  Figure/table/equation labels are never accepted by
        # text mention alone and stay unresolved.
        only_sections = all(component.kind == "section" for component in structural_parts)
        if only_sections:
            result.status = "partial"
        else:
            result.status = "unresolved"
    elif result.unresolved_components:
        result.status = "partial" if matched else "unresolved"
    elif matched or result.pdf_page_indices:
        if result.status != "fuzzy":
            result.status = "normalized" if parsed.parse_status == "normalized" else "exact"
        result.confidence = 0.86 if result.status == "fuzzy" else (1.0 if result.status == "exact" else 0.96)
    else:
        result.status = "unresolved"
    return result


def verify_evidence_span(resolution: Resolution, index: DocumentIndex) -> Resolution:
    """Verify the final source text span after locator parsing/resolution."""
    if resolution.status in {"ambiguous", "unresolved"}:
        return resolution
    components = resolution.parsed.components
    spans: list[dict[str, Any]] = []
    pages = resolution.pdf_page_indices
    structural = [component for component in components if component.kind not in {"source_page_reference", "pdf_page_index", "printed_page_label"}]
    if structural:
        # Structural entries carry a caption/heading line.  For a partial
        # section, verify the requested phrase as a page-local evidence span.
        for component in structural:
            component_matches = [
                item for item in resolution.matched_components if item.get("requested", {}).get("kind") == component.kind
                and item.get("requested", {}).get("value") == component.value
            ]
            if component_matches:
                matched = component_matches[0]["matched"]
                # Digest inventories are useful for candidate generation, but
                # a digest label alone is not an evidence span.  Require a
                # corresponding span in the bound PDF; this prevents an
                # extracted ``Introduction`` tag on a continuation page from
                # becoming a guessed section heading.
                if matched.get("source") == "digest":
                    page = int(matched["page_index"])
                    pdf_entries = [
                        entry for entry in index.structures
                        if entry.source == "pdf_text"
                        and entry.page_index == page
                        and entry.kind == component.kind
                        and normalize_token(entry.number or entry.value) == normalize_token(component.value)
                    ]
                    if pdf_entries:
                        matched = pdf_entries[0].as_dict()
                    else:
                        phrase = component.title or component.value
                        target_pages = pages or [page]
                        candidates: list[dict[str, Any]] = []
                        for target_page in target_pages:
                            candidates.extend({"pdf_page_index": target_page, **span} for span in _find_text_spans(index.page_texts[target_page], phrase))
                        if component.kind == "section" and len(candidates) == 1:
                            resolution.status = "partial"
                            resolution.failure_reason_codes.append("SECTION_NOT_FOUND")
                            spans.extend(candidates)
                            continue
                        resolution.status = "unresolved"
                        resolution.failure_reason_codes.append("EVIDENCE_SPAN_NOT_FOUND")
                        continue
                spans.append({
                    "kind": component.kind,
                    "pdf_page_index": matched["page_index"],
                    "line_index": None,
                    "text": matched.get("text", ""),
                    "match": component.raw,
                })
                continue
            if component.kind == "section":
                target_pages = pages or list(range(len(index.page_texts)))
                candidates: list[dict[str, Any]] = []
                phrase = component.title or component.value
                for page in target_pages:
                    candidates.extend({"pdf_page_index": page, **span} for span in _find_text_spans(index.page_texts[page], phrase))
                if len(candidates) == 1:
                    spans.extend(candidates)
                elif len(candidates) > 1:
                    resolution.status = "ambiguous"
                    resolution.failure_reason_codes.append("EVIDENCE_SPAN_AMBIGUOUS")
                    resolution.ambiguous_candidates.extend(candidates)
                else:
                    resolution.status = "unresolved"
                    resolution.failure_reason_codes.append("EVIDENCE_SPAN_NOT_FOUND")
        if resolution.status == "ambiguous":
            return resolution
    elif pages:
        # Page-only locators still require a non-empty extracted page.
        for page in pages:
            if index.page_texts[page].strip():
                spans.append({"pdf_page_index": page, "line_index": None, "text": index.page_texts[page].splitlines()[0].strip(), "match": "page"})
    if not spans:
        resolution.status = "unresolved"
        resolution.failure_reason_codes.append("EVIDENCE_SPAN_NOT_FOUND")
        return resolution
    resolution.evidence_span = {"count": len(spans), "spans": spans}
    if resolution.status == "partial":
        resolution.confidence = 0.78
    elif resolution.status == "fuzzy":
        resolution.confidence = 0.86
    else:
        resolution.confidence = max(resolution.confidence, 0.94)
    return resolution


def resolve_and_verify(raw: str, index: DocumentIndex) -> Resolution:
    """Run parse -> structural resolution -> evidence-span verification."""
    return verify_evidence_span(resolve_locator(raw, index), index)


def resolve_many(locators: Iterable[str], index: DocumentIndex) -> list[Resolution]:
    return [resolve_and_verify(locator, index) for locator in dict.fromkeys(locators)]


__all__ = [
    "DocumentIndex",
    "LocatorComponent",
    "ParsedLocator",
    "Resolution",
    "STATUSES",
    "build_document_index",
    "normalize_text",
    "normalize_token",
    "parse_locator",
    "resolve_and_verify",
    "resolve_locator",
    "resolve_many",
    "verify_evidence_span",
]
