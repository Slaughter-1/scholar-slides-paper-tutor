"""Load the project-local KaTeX bundle for fully offline HTML artifacts."""

from __future__ import annotations

import base64
import re
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = RUNTIME_ROOT / "assets" / "vendor" / "katex"


def _font_mime(path: Path) -> str:
    return {
        ".woff2": "font/woff2",
        ".woff": "font/woff",
        ".ttf": "font/ttf",
    }.get(path.suffix.lower(), "application/octet-stream")


def _inline_fonts(css: str) -> str:
    def replace(match: re.Match[str]) -> str:
        relative = match.group(1)
        path = (VENDOR_ROOT / relative).resolve()
        if VENDOR_ROOT.resolve() not in path.parents or not path.is_file():
            raise RuntimeError(f"KaTeX font is missing from offline bundle: {relative}")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"url(data:{_font_mime(path)};base64,{encoded})"

    return re.sub(r"url\((?:['\"]?)(fonts/[^'\")]+)(?:['\"]?)\)", replace, css)


def load_katex_assets() -> tuple[str, str, str]:
    """Return ``(version, javascript, css)`` with all font URLs embedded."""

    package_json = VENDOR_ROOT / "package.json"
    js_path = VENDOR_ROOT / "katex.min.js"
    css_path = VENDOR_ROOT / "katex.min.css"
    if not package_json.is_file() or not js_path.is_file() or not css_path.is_file():
        raise RuntimeError("project-local KaTeX bundle is incomplete")
    import json

    version = json.loads(package_json.read_text(encoding="utf-8")).get("version", "unknown")
    css = _inline_fonts(css_path.read_text(encoding="utf-8"))
    js = js_path.read_text(encoding="utf-8")
    return str(version), js, css
