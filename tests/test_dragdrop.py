"""Pure private-payload, threshold, ordering, and drop-state coverage."""

from __future__ import annotations

import json
import uuid

import pytest

from stormpad.dragdrop import (
    decode_drag_payload,
    drag_threshold_exceeded,
    drop_feedback,
    encode_drag_payload,
    insertion_index_for_row,
    move_project_id,
    reorder_project_ids,
    share_menu_options,
)
from stormpad.models import UNFILED_PROJECT_ID
from stormpad.preferences import InMemoryBackend, Preferences


def ids(count: int) -> list[str]:
    return [str(uuid.uuid4()) for _ in range(count)]


def test_private_payload_round_trip_contains_ids_not_paths():
    note_id, project_id = ids(2)
    raw = encode_drag_payload(
        "note",
        note_id,
        source_project_id=project_id,
        source_index=3,
    )
    assert "/Users/" not in raw
    payload = decode_drag_payload(raw, expected_kind="note")
    assert payload is not None
    assert payload.stable_id == note_id
    assert payload.source_project_id == project_id
    assert payload.source_index == 3


def test_unfiled_payload_and_invalid_or_stale_shapes_are_rejected():
    note_id = str(uuid.uuid4())
    raw = encode_drag_payload(
        "note",
        note_id,
        source_project_id=UNFILED_PROJECT_ID,
        source_index=0,
    )
    assert decode_drag_payload(raw).source_project_id == UNFILED_PROJECT_ID
    assert decode_drag_payload("not-json") is None
    assert decode_drag_payload(json.dumps({"kind": "note", "id": "/tmp/note.md"})) is None
    assert decode_drag_payload(raw, expected_kind="project") is None
    with pytest.raises(ValueError):
        encode_drag_payload(
            "project",
            "/tmp/project",
            source_project_id=None,
            source_index=0,
        )


def test_drag_threshold_requires_deliberate_pointer_movement():
    assert drag_threshold_exceeded((10, 10), (12, 13)) is False
    assert drag_threshold_exceeded((10, 10), (14, 13)) is True


def test_project_reorder_first_last_middle_and_unknown_noop():
    first, middle, last = ids(3)
    order = [first, middle, last]
    assert reorder_project_ids(order, first, 3) == [middle, last, first]
    assert reorder_project_ids(order, last, 0) == [last, first, middle]
    assert reorder_project_ids(order, middle, 3) == [first, last, middle]
    assert reorder_project_ids(order, str(uuid.uuid4()), 1) == order


def test_keyboard_project_ordering_clamps_without_nesting():
    first, middle, last = ids(3)
    order = [first, middle, last]
    assert move_project_id(order, middle, -1) == [middle, first, last]
    assert move_project_id(order, middle, 1) == [first, last, middle]
    assert move_project_id(order, first, -1) == order
    assert move_project_id(order, last, 1) == order
    assert all(isinstance(value, str) for value in order)


def test_reordered_projects_persist_without_touching_ids():
    order = ids(3)
    reordered = reorder_project_ids(order, order[0], 3)
    backend = InMemoryBackend()
    Preferences(backend).project_order = reordered
    assert Preferences(backend).project_order == reordered
    assert set(reordered) == set(order)


def test_insertion_and_drop_feedback_states():
    assert insertion_index_for_row(2, 4, 34) == 2
    assert insertion_index_for_row(2, 30, 34) == 3
    assert drop_feedback("project", "project") == "insertion"
    assert drop_feedback("note", "project") == "project_target"
    assert drop_feedback("note", "unfiled") == "unfiled_target"
    assert drop_feedback("note", "all_notes") is None
    assert drop_feedback("project", "unfiled") is None


def test_context_aware_share_menu_state():
    assert share_menu_options(note_selected=False, project_selected=False) == ()
    assert share_menu_options(note_selected=True, project_selected=False) == ("note",)
    assert share_menu_options(note_selected=True, project_selected=True) == (
        "note",
        "project",
    )
