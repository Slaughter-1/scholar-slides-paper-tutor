"""Fail-closed validation for final Paper Learning Map HTML artifacts.

This validator is intentionally independent of the renderer's receipt.  It
reads the bytes of the candidate HTML, extracts the embedded runtime payloads,
and checks the same exact file that will be packaged or handed off.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


UNRESOLVED_MARKER_RE = re.compile(r"__[A-Z0-9_]+__")
PAYLOAD_NAMES = ("MAP", "TUTOR", "STUDY", "FORMULAS")


def _extract_json_constant(document: str, name: str) -> Any:
    prefix = f"const {name}="
    start = document.find(prefix)
    if start < 0:
        raise ValueError(f"missing const {name}= payload")
    cursor = start + len(prefix)
    try:
        value, _ = json.JSONDecoder().raw_decode(document[cursor:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid const {name}= JSON payload: {exc.msg}") from exc
    return value


def _bundle_length(document: str, tag: str) -> int:
    return sum(len(match.group(1)) for match in re.finditer(rf"<{tag}\b[^>]*>(.*?)</{tag}>", document, re.I | re.S))


def validate_final_html(path: Path, *, raise_on_error: bool = True) -> dict[str, Any]:
    """Validate one exact candidate HTML path and return an auditable report."""

    path = Path(path).resolve()
    errors: list[str] = []
    document = ""
    if not path.is_file():
        errors.append("file does not exist")
    else:
        try:
            document = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"cannot read UTF-8 HTML: {exc}")

    if "templates" in {part.lower() for part in path.parts} or path.name.lower().endswith(".template.html"):
        errors.append("template artifact cannot be a final handoff HTML")
    if path.is_file() and path.stat().st_size < 4096:
        errors.append("HTML is below the sensible standalone artifact size")

    markers = sorted(set(UNRESOLVED_MARKER_RE.findall(document)))
    if markers:
        errors.append(f"unresolved markers: {', '.join(markers)}")

    skeleton_checks = {
        "doctype": bool(re.search(r"<!doctype\s+html", document, re.I)),
        "html": bool(re.search(r"<html\b", document, re.I) and re.search(r"</html>", document, re.I)),
        "head": bool(re.search(r"<head\b", document, re.I) and re.search(r"</head>", document, re.I)),
        "body": bool(re.search(r"<body\b", document, re.I) and re.search(r"</body>", document, re.I)),
        "map_svg": '<svg id="map"' in document,
    }
    if not all(skeleton_checks.values()):
        errors.append("standalone HTML skeleton is incomplete")

    payloads: dict[str, Any] = {}
    for name in PAYLOAD_NAMES:
        try:
            payloads[name] = _extract_json_constant(document, name)
        except ValueError as exc:
            errors.append(str(exc))

    map_payload = payloads.get("MAP") if isinstance(payloads.get("MAP"), dict) else {}
    tutor_payload = payloads.get("TUTOR") if isinstance(payloads.get("TUTOR"), dict) else {}
    study_payload = payloads.get("STUDY") if isinstance(payloads.get("STUDY"), dict) else {}
    formulas_payload = payloads.get("FORMULAS") if isinstance(payloads.get("FORMULAS"), dict) else {}
    nodes = map_payload.get("nodes") if isinstance(map_payload.get("nodes"), list) else []
    formulas = formulas_payload.get("formulas") if isinstance(formulas_payload.get("formulas"), list) else []
    source = map_payload.get("source") if isinstance(map_payload.get("source"), dict) else {}

    if not isinstance(payloads.get("MAP"), dict) or not nodes:
        errors.append("MAP payload is missing or has no factual nodes")
    if not isinstance(payloads.get("TUTOR"), dict):
        errors.append("TUTOR payload is missing or invalid")
    if not isinstance(payloads.get("STUDY"), dict):
        errors.append("STUDY payload is missing or invalid")
    if not isinstance(payloads.get("FORMULAS"), dict) or not isinstance(formulas_payload.get("formulas"), list):
        errors.append("FORMULAS payload is missing or invalid")
    if not str((map_payload.get("paper_identity") or {}).get("title") or "").strip():
        errors.append("MAP paper_identity.title is empty")
    if source.get("mode") != "integrated":
        errors.append("MAP source.mode is not integrated")
    if source.get("verification_level") not in {"scholar_slides_validated", "tutor_only"}:
        errors.append("MAP source.verification_level is not a supported verification level")

    css_length = _bundle_length(document, "style")
    js_length = _bundle_length(document, "script")
    has_app_signatures = all(token in document for token in ("function measure", "function fit", "showRelations", "paper_fact:'fact'"))
    if css_length < 1000 or ":root" not in document:
        errors.append("inlined CSS bundle is missing or too small")
    if js_length < 1000 or not has_app_signatures:
        errors.append("inlined application JS bundle is missing or too small")

    katex_css_length = _bundle_length(document, "style") if 'id="katex-css"' in document else 0
    has_katex_js = "katex=" in document or "katex =" in document or "katex.render" in document
    if formulas and (katex_css_length < 1000 or not has_katex_js):
        errors.append("formula payload exists but offline KaTeX CSS/JS bundle is missing")

    body_text = re.sub(r"<[^>]+>", " ", document)
    if len(re.sub(r"\s+", "", body_text)) < 20:
        errors.append("blank page guard: body has no meaningful text")

    result = {
        "schema_version": "1.0",
        "path": str(path),
        "artifact_role": "final_handoff_html" if not errors else "candidate_html",
        "passed": not errors,
        "errors": errors,
        "unresolved_markers": markers,
        "size": path.stat().st_size if path.is_file() else 0,
        "payloads": {
            "map": isinstance(payloads.get("MAP"), dict),
            "tutor": isinstance(payloads.get("TUTOR"), dict),
            "study": isinstance(payloads.get("STUDY"), dict),
            "formulas": isinstance(payloads.get("FORMULAS"), dict),
        },
        "node_count": len(nodes),
        "formula_count": len(formulas),
        "paper_title": (map_payload.get("paper_identity") or {}).get("title"),
        "source_mode": source.get("mode"),
        "verification_level": source.get("verification_level"),
        "bundle_lengths": {"css": css_length, "js": js_length, "katex_css": katex_css_length, "katex_js": has_katex_js},
        "skeleton": skeleton_checks,
    }
    if raise_on_error and errors:
        raise ValueError("; ".join(errors))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed validation for final Paper Learning Map HTML")
    parser.add_argument("path")
    args = parser.parse_args()
    report = validate_final_html(Path(args.path), raise_on_error=False)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
