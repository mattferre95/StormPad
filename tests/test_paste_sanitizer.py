"""Pasted text adopts StormPad's theme instead of importing the source's styling.

Pasting from a browser or TextEdit used to carry the source's own foreground
colour straight into the text storage, so black text landed on StormPad's dark
themes and became unreadable. These lock the sanitizer's contract: supported
inline marks survive, every other attribute is dropped, and the resulting note
never records a colour it was not given inside StormPad.

The pure sanitizer tests need no AppKit. The editor tests below drive the real
NSTextView paste path.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from AppKit import (
    NSApplication,
    NSBackgroundColorAttributeName,
    NSBackingStoreBuffered,
    NSBoldFontMask,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSFontManager,
    NSForegroundColorAttributeName,
    NSItalicFontMask,
    NSLinkAttributeName,
    NSPasteboard,
    NSPasteboardTypeRTF,
    NSPasteboardTypeString,
    NSTitledWindowMask,
    NSUnderlineStyleAttributeName,
    NSUnderlineStyleSingle,
    NSWindow,
)
from Foundation import (
    NSURL,
    NSAttributedString,
    NSMakeRange,
    NSMakeRect,
    NSMutableAttributedString,
)

from stormpad.block_serializer import serialize_blocks
from stormpad.blocks import BlockType, MarkType
from stormpad.models import IDEAS, Note
from stormpad.paste import PastedRun, pasted_blocks, safe_link, sanitize_pasted_runs
from stormpad.theme import get_theme
from stormpad.views.block_editor import Editor
from stormpad.views.palette import Palette

# --- pure sanitizer -----------------------------------------------------------


def _marks(run):
    return {(mark.kind, mark.value) for mark in run.marks}


def test_plain_black_text_keeps_no_colour_mark():
    """Nothing about a black paste should survive as a colour decision."""
    (run,) = sanitize_pasted_runs([PastedRun("Pasted from a website")])

    assert run.text == "Pasted from a website"
    assert run.marks == ()


def test_white_text_is_normalized_rather_than_pinned():
    """White must not be preserved either, or Light theme would break."""
    (run,) = sanitize_pasted_runs([PastedRun("White on dark")])

    assert not any(kind == MarkType.TEXT_COLOR for kind, _ in _marks(run))
    assert not any(kind == MarkType.HIGHLIGHT for kind, _ in _marks(run))


def test_supported_marks_survive():
    runs = sanitize_pasted_runs(
        [
            PastedRun("bold", bold=True),
            PastedRun("italic", italic=True),
            PastedRun("under", underline=True),
            PastedRun("link", link="https://example.com"),
        ]
    )

    assert [run.text for run in runs] == ["bold", "italic", "under", "link"]
    assert _marks(runs[0]) == {(MarkType.BOLD, None)}
    assert _marks(runs[1]) == {(MarkType.ITALIC, None)}
    assert _marks(runs[2]) == {(MarkType.UNDERLINE, None)}
    assert _marks(runs[3]) == {(MarkType.LINK, "https://example.com")}


def test_combined_marks_survive_together():
    (run,) = sanitize_pasted_runs([PastedRun("both", bold=True, italic=True)])

    assert _marks(run) == {(MarkType.BOLD, None), (MarkType.ITALIC, None)}


@pytest.mark.parametrize(
    "target",
    ["javascript:alert(1)", "data:text/html;base64,AAAA", "file:///etc/passwd"],
)
def test_unsafe_link_schemes_are_dropped(target):
    assert safe_link(target) is None
    (run,) = sanitize_pasted_runs([PastedRun("click me", link=target)])
    assert run.marks == ()
    assert run.text == "click me"


def test_ordinary_links_are_kept():
    assert safe_link("https://example.com") == "https://example.com"
    assert safe_link("mailto:someone@example.com") == "mailto:someone@example.com"
    assert safe_link("example.com/page") == "example.com/page"


def test_paragraph_breaks_become_separate_blocks():
    blocks = pasted_blocks([PastedRun("first\nsecond\nthird")])

    assert [block.kind for block in blocks] == [BlockType.TEXT] * 3
    assert [block.text for block in blocks] == ["first", "second", "third"]


def test_every_paragraph_separator_style_splits():
    blocks = pasted_blocks([PastedRun("a\r\nb\rc d e")])

    assert [block.text for block in blocks] == ["a", "b", "c", "d", "e"]


def test_marks_carry_across_a_paragraph_break():
    blocks = pasted_blocks([PastedRun("bold one\nbold two", bold=True)])

    assert [block.text for block in blocks] == ["bold one", "bold two"]
    for block in blocks:
        assert _marks(block.runs[0]) == {(MarkType.BOLD, None)}


def test_unicode_and_emoji_survive():
    blocks = pasted_blocks([PastedRun("café à Noël 🎉 naïve")])

    assert blocks[0].text == "café à Noël 🎉 naïve"


def test_sanitized_paste_never_serializes_a_colour_token():
    blocks = pasted_blocks(
        [
            PastedRun("black", bold=True),
            PastedRun("white"),
            PastedRun("highlighted"),
        ]
    )
    markdown = serialize_blocks(blocks)

    assert "data-stormpad-color" not in markdown
    assert "data-stormpad-highlight" not in markdown
    assert "**black**" in markdown


# --- native paste path --------------------------------------------------------


def _editor(theme_id="deep_dark", body="Existing line"):
    NSApplication.sharedApplication()
    editor = Editor.alloc().initWithPalette_onTitle_onBody_onAttachment_(
        Palette(get_theme(theme_id)),
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
    now = datetime.now()
    editor.load_note(
        Note(
            id="paste",
            path=Path("/tmp/paste.md"),
            title="Paste",
            body=body,
            category=IDEAS,
            created_at=now,
            updated_at=now,
        )
    )
    return editor, window


def _rich_pasteboard():
    """External rich text: black, custom face and size, background, marks."""
    manager = NSFontManager.sharedFontManager()
    source = NSFont.fontWithName_size_("Times New Roman", 24.0) or NSFont.systemFontOfSize_(24.0)
    text = NSMutableAttributedString.alloc().init()

    def add(value, extra=None):
        attributes = {
            NSForegroundColorAttributeName: NSColor.blackColor(),
            NSFontAttributeName: source,
        }
        attributes.update(extra or {})
        text.appendAttributedString_(
            NSAttributedString.alloc().initWithString_attributes_(value, attributes)
        )

    add("Plain. ")
    add("Bold", {NSFontAttributeName: manager.convertFont_toHaveTrait_(source, NSBoldFontMask)})
    add(" ")
    add("Italic", {NSFontAttributeName: manager.convertFont_toHaveTrait_(source, NSItalicFontMask)})
    add(" ")
    add("Under", {NSUnderlineStyleAttributeName: NSUnderlineStyleSingle})
    add(" ")
    add("Link", {NSLinkAttributeName: NSURL.URLWithString_("https://example.com")})
    add(" white", {NSForegroundColorAttributeName: NSColor.whiteColor()})
    add(" lit", {NSBackgroundColorAttributeName: NSColor.yellowColor()})
    add("\nSecond é 🎉")

    data = text.RTFFromRange_documentAttributes_(NSMakeRange(0, text.length()), None)
    pasteboard = NSPasteboard.pasteboardWithUniqueName()
    pasteboard.declareTypes_owner_([NSPasteboardTypeRTF], None)
    pasteboard.setData_forType_(data, NSPasteboardTypeRTF)
    return pasteboard


def _plain_pasteboard(value):
    pasteboard = NSPasteboard.pasteboardWithUniqueName()
    pasteboard.declareTypes_owner_([NSPasteboardTypeString], None)
    pasteboard.setString_forType_(value, NSPasteboardTypeString)
    return pasteboard


def _rgb(color):
    if color is None:
        return None
    converted = color.colorUsingColorSpaceName_("NSCalibratedRGBColorSpace")
    return (
        round(converted.redComponent(), 2),
        round(converted.greenComponent(), 2),
        round(converted.blueComponent(), 2),
    )


def _paste(editor, pasteboard):
    view = editor._body
    view.setSelectedRange_(NSMakeRange(view.textStorage().length(), 0))
    view.readSelectionFromPasteboard_(pasteboard)


def _foreign_styling(editor):
    """Any run whose colour, background, or face came from the source."""
    storage = editor._body.textStorage()
    expected = _rgb(editor._palette.editor_text)
    offenders = []
    cursor = 0
    while cursor < storage.length():
        attrs, effective = storage.attributesAtIndex_effectiveRange_(cursor, None)
        colour = attrs.get(NSForegroundColorAttributeName)
        font = attrs.get(NSFontAttributeName)
        is_link = attrs.get(NSLinkAttributeName) is not None
        if colour is not None and _rgb(colour) != expected and not is_link:
            offenders.append(("foreground", _rgb(colour)))
        if attrs.get(NSBackgroundColorAttributeName) is not None:
            offenders.append(("background", None))
        if font is not None and "Times" in font.fontName():
            offenders.append(("font", font.fontName()))
        cursor = max(cursor + 1, int(effective.location + effective.length))
    return offenders


@pytest.mark.parametrize("theme_id", ["storm_blue", "deep_dark", "light"])
def test_pasted_text_is_readable_in_every_theme(theme_id):
    editor, window = _editor(theme_id)
    try:
        _paste(editor, _rich_pasteboard())
        assert _foreign_styling(editor) == []
    finally:
        window.close()


@pytest.mark.parametrize("theme_id", ["storm_blue", "deep_dark", "light"])
def test_typing_after_a_paste_uses_theme_attributes(theme_id):
    editor, window = _editor(theme_id)
    try:
        _paste(editor, _rich_pasteboard())
        typing = editor._body.typingAttributes()
        assert _rgb(typing.get(NSForegroundColorAttributeName)) == _rgb(
            editor._palette.editor_text
        )
        assert typing.get(NSBackgroundColorAttributeName) is None
    finally:
        window.close()


def test_paste_preserves_supported_formatting_in_the_markdown():
    editor, window = _editor()
    try:
        _paste(editor, _rich_pasteboard())
        markdown = editor.body_text()
        assert "**Bold**" in markdown
        assert "*Italic*" in markdown
        assert "<u>Under</u>" in markdown
        assert "[Link](https://example.com)" in markdown
        assert "Second é 🎉" in markdown
    finally:
        window.close()


def test_paste_never_writes_an_external_colour_into_the_note():
    editor, window = _editor()
    try:
        _paste(editor, _rich_pasteboard())
        markdown = editor.body_text()
        assert "data-stormpad-color" not in markdown
        assert "data-stormpad-highlight" not in markdown
    finally:
        window.close()


def test_paragraph_breaks_become_real_blocks():
    editor, window = _editor()
    try:
        _paste(editor, _rich_pasteboard())
        blocks = editor._extract_blocks()
        assert len(blocks) == 2
        assert blocks[-1].text == "Second é 🎉"
    finally:
        window.close()


def test_plain_text_paste_still_works():
    editor, window = _editor()
    try:
        _paste(editor, _plain_pasteboard("café à Noël 🎉\nsecond line"))
        assert _foreign_styling(editor) == []
        markdown = editor.body_text()
        assert "café à Noël 🎉" in markdown
        assert "second line" in markdown
    finally:
        window.close()


def test_paste_is_a_single_undo_step():
    editor, window = _editor()
    try:
        before = editor.body_text()
        _paste(editor, _rich_pasteboard())
        assert editor.body_text() != before
        editor._body.undoManager().undo()
        assert editor.body_text() == before
        editor._body.undoManager().redo()
        assert "**Bold**" in editor.body_text()
    finally:
        window.close()


def test_reloading_a_pasted_note_keeps_it_theme_neutral():
    """Save and reopen must not resurrect a fixed colour."""
    editor, window = _editor()
    try:
        _paste(editor, _rich_pasteboard())
        saved = editor.body_text()
    finally:
        window.close()

    reopened, window = _editor(body=saved)
    try:
        assert _foreign_styling(reopened) == []
        assert reopened.body_text() == saved
    finally:
        window.close()


def test_pasted_note_stays_readable_after_switching_theme():
    editor, window = _editor("deep_dark")
    try:
        _paste(editor, _rich_pasteboard())
        saved = editor.body_text()
    finally:
        window.close()

    for theme_id in ("light", "storm_blue"):
        switched, window = _editor(theme_id, body=saved)
        try:
            assert _foreign_styling(switched) == []
        finally:
            window.close()


def test_curated_stormpad_colour_and_highlight_still_work():
    """The fix must not disturb colours applied inside StormPad."""
    body = (
        '<span data-stormpad-color="blue">blue text</span> and '
        '<span data-stormpad-highlight="yellow">lit text</span>'
    )
    editor, window = _editor(body=body)
    try:
        markdown = editor.body_text()
        assert 'data-stormpad-color="blue"' in markdown
        assert 'data-stormpad-highlight="yellow"' in markdown
    finally:
        window.close()
