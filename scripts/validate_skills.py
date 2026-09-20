#!/usr/bin/env python3
"""Validate the bundled Codex skill packages without a local Codex install."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

def validate(path: Path) -> list[str]:
    errors=[]
    skill=path / "SKILL.md"
    if not skill.is_file(): return [f"{path}: missing SKILL.md"]
    text=skill.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]: errors.append(f"{path}: invalid frontmatter")
    else:
        front=text[4:text.index("\n---\n",4)]
        for key in ("name:","description:"):
            if not re.search(rf"(?m)^{re.escape(key)}\s*.+$", front): errors.append(f"{path}: missing {key}")
    if not re.fullmatch(r"[a-z0-9-]+", path.name): errors.append(f"{path}: invalid skill directory name")
    return errors

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("paths", nargs="*", default=["scholar-slides", "paper-tutor"]); args=parser.parse_args()
    errors=[]
    for raw in args.paths: errors.extend(validate(Path(raw)))
    payload={"ok": not errors, "errors": errors}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1
if __name__ == "__main__": raise SystemExit(main())
