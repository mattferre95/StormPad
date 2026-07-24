"""Targeted tests for To-do Return handling at the block level.

The editor's data-loss bug was that text typed into a To-do inherited the
checkbox prefix decoration and was dropped on extraction; that fix is verified
against the running editor. These lock the pure block transforms Return relies
on: continuation, mid-text split, and preservation of checked state, inline
marks, and Unicode on both sides of a split.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSEvent,
    NSEventTypeKeyDown,
    NSTitledWindowMask,
    NSWindow,
)
from Foundation import NSDate, NSMakeRange, NSMakeRect, NSRunLoop

from stormpad.blocks import (
    Block,
    BlockType,
    InlineMark,
    InlineRun,
    MarkType,
    next_block_after_return,
    split_block_after_return,
)
from stormpad.models import IDEAS, Note
from stormpad.theme import get_theme
from stormpad.views.block_editor import (
    _TODO_TEXT_GAP,
    Editor,
    _python_offset_from_utf16,
    editable_prefix_end,
)
from stormpad.views.palette import Palette


def _todo(text: str, *, checked: bool = False, marks=()) -> Block:
    return Block(kind=BlockType.TODO, runs=[InlineRun(text, tuple(marks))], checked=checked)


# -- continuation --------------------------------------------------------------


def test_return_after_a_todo_creates_an_unchecked_todo():
    nxt = next_block_after_return(_todo("Buy milk", checked=True))
    assert nxt.kind == BlockType.TODO
    assert nxt.checked is False  # a fresh item is never pre-checked
    assert nxt.text == ""


def test_split_at_end_keeps_all_text_in_the_first_item():
    first, second = split_block_after_return(_todo("Buy milk"), len("Buy milk"))
    assert first.kind == BlockType.TODO
    assert first.text == "Buy milk"  # text is never lost
    assert second.kind == BlockType.TODO
    assert second.text == ""


# -- checked state -------------------------------------------------------------


def test_checked_state_is_preserved_on_the_original_only():
    first, second = split_block_after_return(_todo("Done", checked=True), len("Done"))
    assert first.checked is True
    assert second.checked is False


# -- mid-text split ------------------------------------------------------------


def test_split_in_the_middle_divides_the_text():
    first, second = split_block_after_return(_todo("HelloWorld"), 5)
    assert first.text == "Hello"
    assert second.text == "World"
    assert first.kind == second.kind == BlockType.TODO


def test_split_preserves_inline_formatting_on_both_sides():
    block = Block(
        kind=BlockType.TODO,
        runs=[
            InlineRun("bold", (InlineMark(MarkType.BOLD),)),
            InlineRun("plain"),
        ],
    )
    first, second = split_block_after_return(block, 4)  # split right at the boundary
    assert first.text == "bold"
    assert first.runs[0].marks == (InlineMark(MarkType.BOLD),)
    assert second.text == "plain"
    assert second.runs[0].marks == ()


def test_split_inside_a_formatted_run_keeps_marks_on_both_halves():
    block = _todo("bolded", marks=(InlineMark(MarkType.BOLD),))
    first, second = split_block_after_return(block, 3)
    assert first.text == "bol"
    assert second.text == "ded"
    assert first.runs[0].marks == (InlineMark(MarkType.BOLD),)
    assert second.runs[0].marks == (InlineMark(MarkType.BOLD),)


# -- unicode -------------------------------------------------------------------


def test_split_preserves_unicode_content():
    first, second = split_block_after_return(_todo("café日本"), 4)
    assert first.text == "café"
    assert second.text == "日本"


def test_todo_caret_starts_after_checkbox_decoration():
    assert editable_prefix_end("todo", 10, 11, 20) == 11
    assert editable_prefix_end(None, 10, 12, 20) == 10
    assert 8.0 <= _TODO_TEXT_GAP <= 10.0


class _Range:
    def __init__(self, location: int, length: int = 0):
        self.location = location
        self.length = length


class _Storage:
    def __init__(self, text: str):
        self.text = text
        self.fixed = False

    def length(self):
        return len(self.text.encode("utf-16-le")) // 2

    def ensureAttributesAreFixedInRange_(self, _range):
        self.fixed = True


class _Layout:
    def ensureLayoutForTextContainer_(self, _container):
        pass


class _Body:
    def __init__(self, text: str, live_location: int, stale_location: int):
        self.storage = _Storage(text)
        self.live_range = _Range(live_location)
        self.stale_range = _Range(stale_location)

    def hasMarkedText(self):
        return False

    def textStorage(self):
        return self.storage

    def layoutManager(self):
        return _Layout()

    def textContainer(self):
        return object()

    def rangeForUserTextChange(self):
        return self.live_range

    def selectedRange(self):
        return self.live_range


def _pending_editor(text: str, block: Block, live_location: int, stale_location: int):
    class PendingEditor:
        _body = _Body(text, live_location, stale_location)
        stale_model = text[:-1]
        flushed = False

        def _extract_blocks(self):
            # The focused regression: extraction reads the final live storage,
            # not stale_model/the debounced note snapshot.
            assert self._body.storage.text == text
            return [block]

    return PendingEditor()


def test_editor_level_pending_sync_uses_live_test_text_and_range():
    pending = _pending_editor("TEST", Block.text_block("TEST"), 4, 3)
    blocks, selection = Editor._authoritative_return_state(pending)
    assert pending.stale_model == "TES"
    assert pending._body.storage.fixed is True
    assert blocks[0].text == "TEST"
    assert selection == (4, 0)


def test_intentional_middle_split_uses_live_middle_range():
    pending = _pending_editor("TEST", Block.text_block("TEST"), 3, 3)
    blocks, selection = Editor._authoritative_return_state(pending)
    first, second = split_block_after_return(blocks[0], selection[0])
    assert (first.text, second.text) == ("TES", "T")


def test_formatted_final_character_remains_in_original_block():
    bold = InlineMark(MarkType.BOLD)
    block = Block(
        kind=BlockType.TODO,
        runs=[InlineRun("TES"), InlineRun("T", (bold,))],
    )
    pending = _pending_editor("TEST", block, 4, 3)
    blocks, selection = Editor._authoritative_return_state(pending)
    first, second = split_block_after_return(blocks[0], selection[0])
    assert first.text == "TEST"
    assert first.runs[-1] == InlineRun("T", (bold,))
    assert second.text == ""


def test_pending_todo_return_uses_live_text_and_creates_unchecked_todo():
    pending = _pending_editor("TEST", _todo("TEST", checked=True), 4, 3)
    blocks, selection = Editor._authoritative_return_state(pending)
    first, second = split_block_after_return(blocks[0], selection[0])
    assert first.text == "TEST"
    assert first.checked is True
    assert second.kind == BlockType.TODO
    assert second.checked is False
    assert second.text == ""


def test_plain_rapid_return_preserves_test_final_character_repeatedly():
    for _attempt in range(5):
        pending = _pending_editor("TEST", Block.text_block("TEST"), 4, 3)
        blocks, selection = Editor._authoritative_return_state(pending)
        first, second = split_block_after_return(blocks[0], selection[0])
        assert (first.text, second.text) == ("TEST", "")


def test_return_at_end_preserves_accents_and_composed_unicode():
    for text in ("héllo", "Cafe\u0301", "A🌩️"):
        utf16_length = len(text.encode("utf-16-le")) // 2
        pending = _pending_editor(
            text,
            Block.text_block(text),
            utf16_length,
            max(0, utf16_length - 1),
        )
        blocks, selection = Editor._authoritative_return_state(pending)
        first, second = split_block_after_return(
            blocks[0],
            _python_offset_from_utf16(text, selection[0]),
        )
        assert first.text == text
        assert second.text == ""


_KEY_CODES = {"T": 17, "E": 14, "S": 1}


def _key_event(character: str):
    factory = NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_  # noqa: E501
    return factory(
        NSEventTypeKeyDown,
        (0, 0),
        0,
        0,
        0,
        None,
        character,
        character,
        False,
        36 if character == "\r" else _KEY_CODES.get(character.upper(), 0),
    )


def _dispatch_keys(text_view, text: str) -> None:
    for character in text:
        text_view.interpretKeyEvents_([_key_event(character)])


def _pump_pending_return(editor: Editor) -> None:
    for _turn in range(8):
        if editor._pending_return_timer is None:
            return
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.01)
        )
    raise AssertionError("deferred structural Return did not run")


def _native_editor():
    NSApplication.sharedApplication()
    editor = Editor.alloc().initWithPalette_onTitle_onBody_onAttachment_(
        Palette(get_theme(None)),
        lambda _text: None,
        lambda _text: None,
        lambda _path, _managed: None,
    )
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 900, 700),
        NSTitledWindowMask,
        NSBackingStoreBuffered,
        False,
    )
    editor.view.setFrame_(window.contentView().bounds())
    window.contentView().addSubview_(editor.view)
    return editor, window


def _load_native_note(editor: Editor, body: str, attempt: int) -> None:
    now = datetime.now()
    editor.load_note(
        Note(
            id=f"event-return-{attempt}",
            path=Path(f"/tmp/event-return-{attempt}.md"),
            title="Return regression",
            body=body,
            category=IDEAS,
            created_at=now,
            updated_at=now,
        )
    )
    editor._body.setSelectedRange_(
        NSMakeRange(int(editor._body.textStorage().length()), 0)
    )
    assert editor.view.window().makeFirstResponder_(editor._body)


def test_native_immediate_return_key_sequence_preserves_final_character():
    """Real AppKit key dispatch reaches the deferred command path ten times."""
    editor, window = _native_editor()
    try:
        for attempt in range(10):
            _load_native_note(editor, "", attempt)
            _dispatch_keys(editor._body, "TEST")
            editor._body.interpretKeyEvents_([_key_event("\r")])

            # Return is consumed as intent; the split has not run synchronously.
            assert editor._pending_return_timer is not None
            _pump_pending_return(editor)

            blocks = editor._extract_blocks()
            assert [block.text for block in blocks[:2]] == ["TEST", ""]
            assert editor._current.id == f"event-return-{attempt}"

        _load_native_note(editor, "- [ ] ", 100)
        _dispatch_keys(editor._body, "TEST")
        editor._body.interpretKeyEvents_([_key_event("\r")])
        _pump_pending_return(editor)
        todo_blocks = editor._extract_blocks()
        assert [block.text for block in todo_blocks[:2]] == ["TEST", ""]
        assert all(block.kind == BlockType.TODO for block in todo_blocks[:2])
        assert todo_blocks[1].checked is False

        _load_native_note(editor, "", 101)
        _dispatch_keys(editor._body, "TÉST")
        editor._body.interpretKeyEvents_([_key_event("\r")])
        _pump_pending_return(editor)
        assert [block.text for block in editor._extract_blocks()[:2]] == ["TÉST", ""]

        _load_native_note(editor, "", 102)
        _dispatch_keys(editor._body, "TEST")
        final_character = int(editor._body.textStorage().length()) - 1
        editor._body.setSelectedRange_(NSMakeRange(final_character, 1))
        editor.toggleBold_(None)
        editor._body.setSelectedRange_(
            NSMakeRange(int(editor._body.textStorage().length()), 0)
        )
        editor._body.interpretKeyEvents_([_key_event("\r")])
        _pump_pending_return(editor)
        formatted = editor._extract_blocks()
        assert [block.text for block in formatted[:2]] == ["TEST", ""]
        assert formatted[0].runs[-1].marks == (InlineMark(MarkType.BOLD),)
    finally:
        window.close()
