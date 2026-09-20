from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from formula_projection import validate_formula_index_binding
from katex_bundle import load_katex_assets
from validate_final_html import validate_final_html


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = RUNTIME_ROOT / "templates" / "paper-learning-map.template.html"
CSS_PATH = RUNTIME_ROOT / "assets" / "paper-learning-map.css"
JS_PATH = RUNTIME_ROOT / "assets" / "paper-learning-map.js"

RENDERER_CONTRACT = (
    "presentation_only",
    "function measure",
    "function fit",
    "drawer",
    "showRelations",
    "paper_fact:'fact'",
)

_MARKERS = (
    "__INLINE_CSS__",
    "__INLINE_KATEX_CSS__",
    "__INLINE_KATEX_JS__",
    "__INLINE_JS__",
    "__MAP_DATA__",
    "__TUTOR_DATA__",
    "__STUDY_DATA__",
    "__FORMULA_DATA__",
    "__SYNC_RECEIPTS__",
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - exercised by CLI users
        raise RuntimeError(f"Renderer asset is unavailable: {path}") from exc


def _safe_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return encoded.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _value_digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _inject_markers(template: str, replacements: Mapping[str, str]) -> str:
    rendered = template
    for marker in _MARKERS:
        if marker not in replacements:
            raise ValueError(f"Missing replacement for marker {marker}")
        count = rendered.count(marker)
        if count != 1:
            raise ValueError(f"Template marker {marker} must occur exactly once (found {count})")
        start = rendered.index(marker)
        rendered = rendered[:start] + replacements[marker] + rendered[start + len(marker) :]
    leftovers = [marker for marker in _MARKERS if marker in rendered]
    if leftovers:
        raise ValueError(f"Unresolved renderer markers: {', '.join(leftovers)}")
    return rendered


def _load_project_data(project: Path, formula_index: Path | None = None) -> dict[str, object]:
    names = ("paper-map.json", "tutor-state.json", "study-state.json")
    data: dict[str, object] = {}
    for name in names:
        path = project / name
        try:
            data[name] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError(f"Missing renderer input: {path}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in renderer input: {path}: {exc}") from exc
    candidate = formula_index or (project / "formula-index.json")
    if candidate.is_file():
        try:
            data["formula-index.json"] = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in renderer input: {candidate}: {exc}") from exc
    else:
        data["formula-index.json"] = {"schema_version": "1.0", "formulas": []}
    receipts: list[dict[str, object]] = []
    receipt_dir = project / "sync-receipts"
    if receipt_dir.is_dir():
        for path in sorted(receipt_dir.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                receipts.append(value)
    data["sync-receipts.json"] = receipts[-50:]
    return data


def render_project(project: Path, output: Path | None = None, formula_index: Path | None = None) -> Path:
    project = project.resolve()
    data = _load_project_data(project, formula_index=formula_index)
    validate_formula_index_binding(data["formula-index.json"], data["paper-map.json"])
    template = _read_text(TEMPLATE_PATH)
    css = _read_text(CSS_PATH) + "\n.deep-nav{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--muted);margin:12px 0}.deep-nav a{color:var(--accent)}.sync-status{font-weight:700;color:var(--accent);border-left:3px solid var(--accent);padding-left:8px}.sync-status[data-sync-status=\\\"sync failed\\\"]{color:#b42318;border-color:#b42318}.sync-status[data-sync-status=\\\"not synced\\\"],.sync-status[data-sync-status=\\\"unresolved\\\"]{color:#9a6700;border-color:#9a6700}"
    javascript = _read_text(JS_PATH)
    katex_version, katex_js, katex_css = load_katex_assets()
    replacements = {
        "__INLINE_CSS__": css,
        "__INLINE_KATEX_CSS__": f"/* KaTeX {katex_version}; offline vendor */\n{katex_css}",
        "__INLINE_KATEX_JS__": f"/* KaTeX {katex_version}; offline vendor */\n{katex_js}",
        "__INLINE_JS__": javascript,
        "__MAP_DATA__": _safe_json(data["paper-map.json"]),
        "__TUTOR_DATA__": _safe_json(data["tutor-state.json"]),
        "__STUDY_DATA__": _safe_json(data["study-state.json"]),
        "__FORMULA_DATA__": _safe_json(data["formula-index.json"]),
        "__SYNC_RECEIPTS__": _safe_json(data["sync-receipts.json"]),
    }
    html = _inject_markers(template, replacements)
    target = (output or (project / "paper-learning-map.html")).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    validation = validate_final_html(target, raise_on_error=False)
    formula_candidate = formula_index or (project / "formula-index.json")
    receipt = {
        "schema_version": "1.0",
        "artifact_role": "rendered_html",
        "template_path": str(TEMPLATE_PATH.resolve()),
        "template_sha256": _sha256(TEMPLATE_PATH),
        "paper_map_sha256": _sha256(project / "paper-map.json") if (project / "paper-map.json").is_file() else None,
        "tutor_state_sha256": _sha256(project / "tutor-state.json") if (project / "tutor-state.json").is_file() else None,
        "study_state_sha256": _sha256(project / "study-state.json") if (project / "study-state.json").is_file() else None,
        "formula_index_sha256": _sha256(formula_candidate) if formula_candidate.is_file() else _value_digest(data["formula-index.json"]),
        "sync_receipts_digest": _value_digest(data["sync-receipts.json"]),
        "output_path": str(target),
        "output_sha256": _sha256(target),
        "output_size": target.stat().st_size,
        "markers_remaining": validation.get("unresolved_markers", []),
        "validation_passed": bool(validation.get("passed")),
        "validation": validation,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = target.parent / "render-receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not validation.get("passed"):
        raise RuntimeError(f"final HTML validation failed for {target}: {', '.join(validation.get('errors', []))}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a standalone Paper Learning Map HTML")
    parser.add_argument("--project", required=True)
    parser.add_argument("--output")
    parser.add_argument("--formula-index")
    args = parser.parse_args()
    target = render_project(
        Path(args.project),
        Path(args.output) if args.output else None,
        Path(args.formula_index) if args.formula_index else None,
    )
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
