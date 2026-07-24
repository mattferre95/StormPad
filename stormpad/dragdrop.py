"""Pure helpers for safe internal project/note drag operations."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass

from .models import UNFILED_PROJECT_ID

PROJECT_PASTEBOARD_TYPE = "com.stormpad.project-id"
NOTE_PASTEBOARD_TYPE = "com.stormpad.note-id"
DRAG_THRESHOLD = 5.0


@dataclass(frozen=True)
class InternalDragPayload:
    """UUID-only internal drag data; paths are intentionally never accepted."""

    kind: str
    stable_id: str
    source_project_id: str | None
    source_index: int


def _valid_uuid(value: object) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def encode_drag_payload(
    kind: str,
    stable_id: str,
    *,
    source_project_id: str | None,
    source_index: int,
) -> str:
    """Serialize validated UUID-only payload data for a private pasteboard type."""
    if kind not in {"project", "note"}:
        raise ValueError(f"unsupported drag kind: {kind}")
    normalized_id = _valid_uuid(stable_id)
    if normalized_id is None:
        raise ValueError("drag payload requires a stable UUID")
    if source_project_id not in (None, UNFILED_PROJECT_ID):
        source_project_id = _valid_uuid(source_project_id)
        if source_project_id is None:
            raise ValueError("source project requires a stable UUID or Unfiled")
    if not isinstance(source_index, int) or isinstance(source_index, bool) or source_index < 0:
        raise ValueError("source row index must be a non-negative integer")
    return json.dumps(
        {
            "kind": kind,
            "id": normalized_id,
            "source_project_id": source_project_id,
            "source_index": source_index,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def decode_drag_payload(
    raw: object,
    *,
    expected_kind: str | None = None,
) -> InternalDragPayload | None:
    """Return a validated payload, rejecting stale/malformed/path-based input."""
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if kind not in {"project", "note"} or (
        expected_kind is not None and kind != expected_kind
    ):
        return None
    stable_id = _valid_uuid(value.get("id"))
    source = value.get("source_project_id")
    if source not in (None, UNFILED_PROJECT_ID):
        source = _valid_uuid(source)
    source_index = value.get("source_index")
    if (
        stable_id is None
        or source is None
        and value.get("source_project_id") not in (None,)
        or not isinstance(source_index, int)
        or isinstance(source_index, bool)
        or source_index < 0
    ):
        return None
    return InternalDragPayload(kind, stable_id, source, source_index)


def drag_threshold_exceeded(
    start: tuple[float, float],
    current: tuple[float, float],
    *,
    threshold: float = DRAG_THRESHOLD,
) -> bool:
    """Whether pointer travel is large enough to start a deliberate drag."""
    return math.hypot(current[0] - start[0], current[1] - start[1]) >= threshold


def insertion_index_for_row(
    row_index: int,
    pointer_y: float,
    row_height: float,
) -> int:
    """Map a pointer within a project row to its before/after insertion boundary."""
    if row_index < 0 or row_height <= 0:
        raise ValueError("row index and height must be valid")
    return row_index if pointer_y < row_height / 2.0 else row_index + 1


def reorder_project_ids(
    order: list[str],
    project_id: str,
    insertion_index: int,
) -> list[str]:
    """Move one existing project to an insertion boundary without nesting."""
    if project_id not in order:
        return list(order)
    result = list(order)
    source = result.index(project_id)
    insertion = min(max(int(insertion_index), 0), len(result))
    result.pop(source)
    if source < insertion:
        insertion -= 1
    result.insert(min(max(insertion, 0), len(result)), project_id)
    return result


def move_project_id(order: list[str], project_id: str, offset: int) -> list[str]:
    """Keyboard-accessible adjacent project reordering."""
    if project_id not in order or offset == 0:
        return list(order)
    source = order.index(project_id)
    destination = min(max(source + offset, 0), len(order) - 1)
    result = list(order)
    moving = result.pop(source)
    result.insert(destination, moving)
    return result


def drop_feedback(payload_kind: str, target_kind: str) -> str | None:
    """Return the semantic visual state for a valid target kind."""
    if payload_kind == "project" and target_kind == "project":
        return "insertion"
    if payload_kind == "note" and target_kind == "project":
        return "project_target"
    if payload_kind == "note" and target_kind == "unfiled":
        return "unfiled_target"
    return None


def share_menu_options(
    *,
    note_selected: bool,
    project_selected: bool,
) -> tuple[str, ...]:
    """Pure enablement/state helper for share surfaces."""
    options: list[str] = []
    if note_selected:
        options.append("note")
    if project_selected:
        options.append("project")
    return tuple(options)
