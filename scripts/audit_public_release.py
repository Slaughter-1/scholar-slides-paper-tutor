#!/usr/bin/env python3
"""Audit tracked public-release files for credentials and oversized artifacts."""
from __future__ import annotations
import argparse, json, re, subprocess
from pathlib import Path

SECRET_PATTERNS = {
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "openai_like_key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
}
DEFAULT_MAX_BYTES = 10 * 1024 * 1024

def tracked(repo: Path) -> list[Path]:
    out = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-z"])
    return [repo / item for item in out.decode("utf-8").split("\0") if item]

def audit(repo: Path, max_bytes: int) -> dict:
    findings = []
    files = tracked(repo)
    for path in files:
        try:
            size = path.stat().st_size
        except OSError as exc:
            findings.append({"kind": "missing", "path": str(path.relative_to(repo)), "detail": str(exc)})
            continue
        if size > max_bytes:
            findings.append({"kind": "oversized", "path": str(path.relative_to(repo)), "bytes": size, "limit": max_bytes})
        if size > 25 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append({"kind": name, "path": str(path.relative_to(repo))})
    return {"ok": not findings, "tracked_files": len(files), "findings": findings}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = audit(Path(args.repo).resolve(), args.max_bytes)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else ("PUBLIC RELEASE AUDIT: PASS" if result["ok"] else json.dumps(result, ensure_ascii=False, indent=2)))
    return 0 if result["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
