"""Append-only observability receipts for the Paper-Tutor bridge.

Receipts are an audit trail, not a source of Learning Map state.  The factual
map, Tutor State, and Study State remain authoritative; this module only
records what a bridge invocation attempted and what it changed (or why it
could not change anything).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "paper-learning-map" / "schemas" / "sync-receipt.schema.json"


def sha256_file(path: Path | str) -> str | None:
    """Return a file hash, or ``None`` when the file is not present."""

    target = Path(path)
    if not target.is_file():
        return None
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_receipt(receipt: Mapping[str, Any]) -> None:
    """Validate one receipt before it is persisted."""

    errors = sorted(
        Draft202012Validator(_schema(), format_checker=FormatChecker()).iter_errors(dict(receipt)),
        key=lambda error: list(error.path),
    )
    if errors:
        location = ".".join(str(part) for part in errors[0].path) or "$"
        raise ValueError(f"invalid sync receipt at {location}: {errors[0].message}")


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(value), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(raw, path)
    finally:
        if os.path.exists(raw):
            os.unlink(raw)


def _filename(timestamp: str, event: str, directory: Path) -> Path:
    # The microsecond timestamp makes normal collisions unlikely; the suffix
    # loop keeps append-only semantics even when several turns finish in the
    # same clock tick or a copied project is replayed.
    stem = f"{re.sub(r'[^0-9A-Za-z]+', '', timestamp)}-{re.sub(r'[^0-9A-Za-z_.-]+', '_', event)}"
    candidate = directory / f"{stem}.json"
    index = 1
    while candidate.exists():
        candidate = directory / f"{stem}-{index:02d}.json"
        index += 1
    return candidate


def append_receipt(project: Path | str, receipt: Mapping[str, Any], *, directory: Path | str | None = None) -> Path:
    """Atomically append one receipt file and return its path."""

    payload = dict(receipt)
    validate_receipt(payload)
    root = Path(project).resolve()
    target_dir = Path(directory).resolve() if directory else root / "sync-receipts"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat())
    event = str(payload.get("event") or "sync_failed")
    target = _filename(timestamp, event, target_dir)
    _atomic_write(target, payload)
    return target


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def short_error(exc: BaseException, limit: int = 240) -> dict[str, str]:
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    return {"type": exc.__class__.__name__, "short_error": message[:limit]}


def state_hash(path: Path | str) -> str | None:
    """Hash one downstream state file when it exists."""

    return sha256_file(path)


def load_state(project: Path | str, name: str) -> dict[str, Any] | None:
    """Read a JSON state file for receipt diffing; missing/invalid is ``None``.

    Receipt generation must never replace the authoritative state validator.  This
    helper is intentionally tolerant so a malformed or partially written state can
    still produce a failed audit record rather than masking the original error.
    """

    path = Path(project) / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _items(state: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(state, Mapping):
        return result
    for node_id, node_state in (state.get("nodes") or {}).items():
        if not isinstance(node_state, Mapping):
            continue
        for item in node_state.get("map_items") or []:
            if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                result[item["id"]] = {"node_id": node_id, **dict(item)}
    return result


def diff_counts(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    records_received: int = 0,
) -> dict[str, Any]:
    """Return conservative item/unresolved/study diff facts for a receipt."""

    before_items, after_items = _items(before), _items(after)
    added_ids = set(after_items) - set(before_items)
    common_ids = set(before_items) & set(after_items)
    updated_ids = {item_id for item_id in common_ids if before_items[item_id] != after_items[item_id]}
    before_unresolved = (before or {}).get("unresolved_items") or [] if isinstance(before, Mapping) else []
    after_unresolved = (after or {}).get("unresolved_items") or [] if isinstance(after, Mapping) else []
    before_unresolved_ids = {item.get("id") for item in before_unresolved if isinstance(item, Mapping)}
    after_unresolved_ids = {item.get("id") for item in after_unresolved if isinstance(item, Mapping)}
    added_unresolved = len(after_unresolved_ids - before_unresolved_ids)
    return {
        "records_received": int(records_received),
        "items_added": len(added_ids),
        "items_updated": len(updated_ids),
        "unresolved_added": added_unresolved,
        "unresolved_total": len(after_unresolved_ids),
        "resolved_node_ids": sorted({str(after_items[item_id]["node_id"]) for item_id in added_ids | updated_ids}),
    }


def study_transition(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    preferred_node_id: str | None = None,
) -> dict[str, str | None] | None:
    """Report the first status transition, preferring a requested node."""

    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return None
    before_nodes, after_nodes = before.get("nodes") or {}, after.get("nodes") or {}
    ids = list(after_nodes)
    if preferred_node_id and preferred_node_id in after_nodes:
        ids = [preferred_node_id] + [item for item in ids if item != preferred_node_id]
    for node_id in ids:
        left = before_nodes.get(node_id) or {}
        right = after_nodes.get(node_id) or {}
        old, new = left.get("status"), right.get("status")
        if old != new:
            return {"node_id": str(node_id), "before": old, "after": new}
    return None


def build_receipt(
    *,
    event: str,
    project: Path | str,
    paper_sha256: str | None,
    status: str,
    records_received: int = 0,
    before_tutor: str | None = None,
    after_tutor: str | None = None,
    before_study: str | None = None,
    after_study: str | None = None,
    counts: Mapping[str, Any] | None = None,
    study: Mapping[str, Any] | None = None,
    error: Mapping[str, str] | None = None,
    reason: str | None = None,
    idempotency_key: str | None = None,
    retry_of: str | None = None,
    dedupe_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a schema-complete receipt payload without writing it."""

    values = dict(counts or {})
    return {
        "receipt_version": "1.0",
        "event": event,
        "timestamp": now(),
        "paper_sha256": paper_sha256,
        "project": str(Path(project).resolve()),
        "sync_attempted": status != "skipped",
        "status": status,
        "records_received": int(values.get("records_received", records_received)),
        "items_added": int(values.get("items_added", 0)),
        "items_updated": int(values.get("items_updated", 0)),
        "items_deduped": int(values.get("items_deduped", 0)),
        "unresolved_added": int(values.get("unresolved_added", 0)),
        "unresolved_total": int(values.get("unresolved_total", 0)),
        "resolved_node_ids": list(values.get("resolved_node_ids", [])),
        "tutor_state_sha256_before": before_tutor,
        "tutor_state_sha256_after": after_tutor,
        "study_state_sha256_before": before_study,
        "study_state_sha256_after": after_study,
        "study_state": dict(study) if study else None,
        "error": dict(error) if error else None,
        "reason": reason,
        "idempotency_key": idempotency_key,
        "retry_of": retry_of,
        "dedupe_report": dict(dedupe_report) if dedupe_report else None,
    }


def latest_receipt(project: Path | str) -> dict[str, Any] | None:
    """Return the newest valid receipt, if any, without claiming success."""

    directory = Path(project) / "sync-receipts"
    if not directory.is_dir():
        return None
    latest: dict[str, Any] | None = None
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            validate_receipt(value)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
        latest = value
    return latest


def visible_sync_status(project: Path | str, *, expected: bool = True) -> str:
    """Map real receipt state to the small user-facing status vocabulary."""

    receipt = latest_receipt(project)
    if receipt is None:
        return "not_synced" if expected else "not_applicable"
    if receipt.get("status") == "failed":
        return "sync_failed"
    if receipt.get("status") == "skipped":
        return "not_synced"
    if int(receipt.get("unresolved_total", 0)) > 0 or int(receipt.get("unresolved_added", 0)) > 0:
        return "unresolved"
    return "synced"
