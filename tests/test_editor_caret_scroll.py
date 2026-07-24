"""Focused AppKit coverage for deferred caret-follow scrolling."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSEvent,
    NSEventTypeKeyDown,
    NSTitledWindowMask,
    NSWindow,
)
from Foundation import NSDate, NSMakeRange, NSMakeRect, NSRunLoop

from stormpad.blocks import BlockType
from stormpad.models import IDEAS, Note
from stormpad.theme import get_theme
from stormpad.views.block_editor import (
    _CARET_BOTTOM_MARGIN,
    _EDITOR_BOTTOM_INSET,
    Editor,
)
from stormpad.views.palette import Palette


def _native_editor():
    NSApplication.sharedApplication()
    editor = Editor.alloc().initWithPalette_onTitle_onBody_onAttachment_(
        Palette(get_theme(None)),
        lambda _text: None,
        lambda _text: None,
        lambda _path, _managed: None,
    )
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(80, 80, 760, 430),
        NSTitledWindowMask,
        NSBackingStoreBuffered,
        False,
    )
    editor.view.setFrame_(window.contentView().bounds())
    window.contentView().addSubview_(editor.view)
    window.makeKeyAndOrderFront_(None)
    return editor, window


def _note(note_id: str, body: str) -> Note:
    now = datetime.now()
    return Note(
        id=note_id,
        path=Path(f"/tmp/{note_id}.md"),
        title="Caret follow",
        body=body,
        category=IDEAS,
        created_at=now,
        updated_at=now,
    )


def _load(editor: Editor, note_id: str, body: str) -> None:
    editor.load_note(_note(note_id, body))
    editor._body.setSelectedRange_(
        NSMakeRange(int(editor._body.textStorage().length()), 0)
    )
    assert editor.view.window().makeFirstResponder_(editor._body)


def _return_event():
    factory = NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_  # noqa: E501
    return factory(
        NSEventTypeKeyDown,
        (0, 0),
        0,
        0,
        0,
        None,
        "\r",
        "\r",
        False,
        36,
    )


def _pump_editor(editor: Editor) -> None:
    for _turn in range(16):
        if (
            editor._pending_return_timer is None
            and editor._pending_caret_visibility_timer is None
        ):
            return
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.01)
        )
    raise AssertionError("deferred editor operation did not run")


def _caret_document_rect(editor: Editor):
    body = editor._body
    selected = body.selectedRange()
    return editor._caret_rect_in_document(
        body,
        int(selected.location),
    )


def _assert_caret_comfortable(editor: Editor) -> None:
    caret = _caret_document_rect(editor)
    visible = editor._scroll.contentView().bounds()
    visible_top = float(visible.origin.y)
    visible_bottom = (
        visible_top
        + float(visible.size.height)
        + float(editor._scroll.contentInsets().bottom)
    )
    caret_top = float(caret.origin.y)
    caret_bottom = caret_top + max(1.0, float(caret.size.height))
    assert caret_top >= visible_top
    assert caret_bottom <= visible_bottom
    assert visible_bottom - caret_bottom >= 72.0
    assert visible_bottom - caret_bottom <= _CARET_BOTTOM_MARGIN + 2.0


def test_repeated_return_keeps_caret_visible_with_bottom_margin():
    editor, window = _native_editor()
    try:
        _load(editor, "repeated-return", "")
        event = _return_event()
        for _index in range(24):
            editor._body.interpretKeyEvents_([event])
            _pump_editor(editor)
        assert len(editor._extract_blocks()) == 25
        assert float(editor._scroll.contentView().bounds().origin.y) > 0.0
        _assert_caret_comfortable(editor)
    finally:
        window.close()


def test_caret_already_comfortable_does_not_scroll():
    editor, window = _native_editor()
    try:
        _load(editor, "already-visible", "First\nSecond")
        before = editor._scroll.contentView().bounds()
        assert editor._scroll_caret_into_comfortable_view(editor._body) is False
        after = editor._scroll.contentView().bounds()
        assert float(after.origin.x) == pytest.approx(float(before.origin.x))
        assert float(after.origin.y) == pytest.approx(float(before.origin.y))
    finally:
        window.close()


def test_todo_return_follows_new_todo_caret():
    editor, window = _native_editor()
    try:
        body = "\n".join(["- [ ] item"] * 18)
        _load(editor, "todo-return", body)
        editor._body.interpretKeyEvents_([_return_event()])
        _pump_editor(editor)
        blocks = editor._extract_blocks()
        assert len(blocks) == 19
        assert blocks[-1].kind == BlockType.TODO
        assert blocks[-1].checked is False
        _assert_caret_comfortable(editor)
    finally:
        window.close()


def test_note_switch_cancels_stale_deferred_scroll():
    editor, window = _native_editor()
    try:
        _load(editor, "old-note", "\n".join(["old"] * 20))
        editor._schedule_caret_visibility(editor._body)
        assert editor._pending_caret_visibility_timer is not None
        editor.load_note(_note("new-note", "new"))
        before = editor._scroll.contentView().bounds()
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.02)
        )
        after = editor._scroll.contentView().bounds()
        assert editor._current.id == "new-note"
        assert editor._pending_caret_visibility_timer is None
        assert float(after.origin.x) == pytest.approx(float(before.origin.x))
        assert float(after.origin.y) == pytest.approx(float(before.origin.y))
    finally:
        window.close()


def test_bottom_inset_is_layout_only_and_not_markdown():
    editor, window = _native_editor()
    try:
        body = "Only real content"
        _load(editor, "layout-only-inset", body)
        assert float(editor._scroll.contentInsets().bottom) == _EDITOR_BOTTOM_INSET
        assert editor.body_text() == body
        assert len(editor._extract_blocks()) == 1
    finally:
        window.close()
