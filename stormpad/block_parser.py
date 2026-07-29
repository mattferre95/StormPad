"""Parse StormPad's supported Markdown subset into semantic blocks."""

from __future__ import annotations

import html
import re
from urllib.parse import unquote

from .blocks import (
    COLOR_TOKENS,
    Block,
    BlockType,
    InlineMark,
    InlineRun,
    MarkType,
    coalesce_runs,
)

_TODO = re.compile(r"^(\s*)-\s+\[([ xX])\]\s*(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
_IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")
_IMAGE_METADATA = re.compile(
    r'^<!--\s*stormpad:image\s+width="([0-9]+(?:\.[0-9]+)?)"\s*-->$',
    re.IGNORECASE,
)
_LINK = re.compile(r"^\[([^\]]*)\]\(([^)]+)\)$")
_TRANSCRIPT = re.compile(
    r'^<!--\s*stormpad:transcript(?:\s+collapsed="(true|false)")?\s*-->$',
    re.IGNORECASE,
)
_COLOR_OPEN = re.compile(r'^<span data-stormpad-(color|highlight)="([^"]+)">')
_TOGGLE = re.compile(
    r'^<!--\s*stormpad:toggle(?:\s+collapsed="(true|false)")?\s*-->$',
    re.IGNORECASE,
)
_TOGGLE_HEADING_PREFIXES = (
    ("### ", BlockType.TOGGLE_HEADING_3),
    ("## ", BlockType.TOGGLE_HEADING_2),
    ("# ", BlockType.TOGGLE_HEADING_1),
)
_TOGGLE_EMPTY_HEADINGS = {
    "###": BlockType.TOGGLE_HEADING_3,
    "##": BlockType.TOGGLE_HEADING_2,
    "#": BlockType.TOGGLE_HEADING_1,
}


def _toggle_summary(line: str, collapsed: bool) -> Block | None:
    """Turn the line under a toggle marker into a summary block.

    Returns ``None`` when the following line is not something a toggle can
    summarize, which leaves the marker to be preserved as raw text and the line
    to parse normally. Malformed metadata therefore degrades to visible content
    instead of hiding or dropping anything.
    """
    stripped = line.strip()
    empty_heading = _TOGGLE_EMPTY_HEADINGS.get(stripped)
    if empty_heading is not None:
        return Block(kind=empty_heading, collapsed=collapsed)
    for prefix, kind in _TOGGLE_HEADING_PREFIXES:
        if stripped.startswith(prefix):
            return Block(
                kind=kind,
                runs=parse_inline(stripped[len(prefix) :]),
                collapsed=collapsed,
            )
    bullet = _BULLET.match(line)
    if bullet and not _TODO.match(line):
        spaces, content = bullet.groups()
        return Block(
            kind=BlockType.TOGGLE,
            runs=parse_inline(content),
            indent=_indent(spaces),
            collapsed=collapsed,
        )
    if stripped == "-":
        return Block(kind=BlockType.TOGGLE, collapsed=collapsed)
    return None


def _add_mark(runs: list[InlineRun], mark: InlineMark) -> list[InlineRun]:
    return [InlineRun(run.text, (*run.marks, mark)) for run in runs]


def _find_unescaped(text: str, needle: str, start: int) -> int:
    cursor = start
    while True:
        found = text.find(needle, cursor)
        if found < 0:
            return -1
        backslashes = 0
        probe = found - 1
        while probe >= 0 and text[probe] == "\\":
            backslashes += 1
            probe -= 1
        if backslashes % 2 == 0:
            return found
        cursor = found + len(needle)


def _find_matching_span(text: str, start: int) -> int:
    """Find the close tag for a span body, accounting for nested spans."""
    depth = 1
    cursor = start
    while cursor < len(text):
        opening = text.find("<span ", cursor)
        closing = text.find("</span>", cursor)
        if closing < 0:
            return -1
        if opening >= 0 and opening < closing:
            depth += 1
            cursor = opening + len("<span ")
            continue
        depth -= 1
        if depth == 0:
            return closing
        cursor = closing + len("</span>")
    return -1


def parse_inline(text: str) -> list[InlineRun]:
    """Parse supported inline Markdown/StormPad HTML without executing HTML."""
    runs: list[InlineRun] = []
    plain: list[str] = []

    def flush() -> None:
        if plain:
            runs.append(InlineRun(html.unescape("".join(plain))))
            plain.clear()

    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            plain.append(text[i + 1])
            i += 2
            continue

        if text.startswith("***", i):
            end = _find_unescaped(text, "***", i + 3)
            if end >= 0:
                flush()
                nested = parse_inline(text[i + 3 : end])
                nested = _add_mark(nested, InlineMark(MarkType.BOLD))
                runs.extend(_add_mark(nested, InlineMark(MarkType.ITALIC)))
                i = end + 3
                continue

        if text.startswith("**", i):
            end = _find_unescaped(text, "**", i + 2)
            if end >= 0:
                flush()
                runs.extend(
                    _add_mark(
                        parse_inline(text[i + 2 : end]),
                        InlineMark(MarkType.BOLD),
                    )
                )
                i = end + 2
                continue

        if text[i] == "*":
            end = _find_unescaped(text, "*", i + 1)
            if end >= 0:
                flush()
                runs.extend(
                    _add_mark(
                        parse_inline(text[i + 1 : end]),
                        InlineMark(MarkType.ITALIC),
                    )
                )
                i = end + 1
                continue

        if text.startswith("<u>", i):
            end = text.find("</u>", i + 3)
            if end >= 0:
                flush()
                runs.extend(
                    _add_mark(
                        parse_inline(text[i + 3 : end]),
                        InlineMark(MarkType.UNDERLINE),
                    )
                )
                i = end + 4
                continue

        color = _COLOR_OPEN.match(text[i:])
        if color:
            attribute, token = color.groups()
            end_tag = "</span>"
            start = i + color.end()
            end = _find_matching_span(text, start)
            if end >= 0 and token in COLOR_TOKENS:
                flush()
                mark_type = (
                    MarkType.TEXT_COLOR if attribute == "color" else MarkType.HIGHLIGHT
                )
                runs.extend(
                    _add_mark(
                        parse_inline(text[start:end]),
                        InlineMark(mark_type, token),
                    )
                )
                i = end + len(end_tag)
                continue

        if text[i] == "[":
            close_label = _find_unescaped(text, "](", i + 1)
            if close_label >= 0:
                close_target = _find_unescaped(text, ")", close_label + 2)
                if close_target >= 0:
                    target = text[close_label + 2 : close_target].strip()
                    if target:
                        flush()
                        nested = parse_inline(text[i + 1 : close_label])
                        runs.extend(
                            _add_mark(nested, InlineMark(MarkType.LINK, target))
                        )
                        i = close_target + 1
                        continue

        plain.append(text[i])
        i += 1

    flush()
    return coalesce_runs(runs)


def _indent(value: str) -> int:
    return len(value.replace("\t", "    ")) // 2


def _is_managed_attachment(target: str) -> bool:
    normalized = target.replace("\\", "/")
    return "/Attachments/" in normalized or normalized.startswith("Attachments/")


def parse_blocks(markdown: str) -> list[Block]:
    """Parse body Markdown. Empty body yields one editable empty text block."""
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return [Block()]

    lines = normalized.split("\n")
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if line.lstrip().startswith("```"):
            raw_lines = [line]
            i += 1
            while i < len(lines):
                raw_lines.append(lines[i])
                if lines[i].lstrip().startswith("```"):
                    i += 1
                    break
                i += 1
            blocks.append(Block(kind=BlockType.RAW, raw="\n".join(raw_lines)))
            continue

        toggle = _TOGGLE.match(line.strip())
        if toggle and i + 1 < len(lines):
            summary = _toggle_summary(
                lines[i + 1], (toggle.group(1) or "false").lower() == "true"
            )
            if summary is not None:
                blocks.append(summary)
                i += 2
                continue

        transcript = _TRANSCRIPT.match(line.strip())
        if transcript:
            blocks.append(
                Block(
                    kind=BlockType.TRANSCRIPT,
                    collapsed=(transcript.group(1) or "false").lower() == "true",
                )
            )
            i += 1
            continue

        image_metadata = _IMAGE_METADATA.match(line.strip())
        if image_metadata and i + 1 < len(lines):
            image = _IMAGE.match(lines[i + 1].strip())
            if image:
                alt, target = image.groups()
                blocks.append(
                    Block(
                        kind=BlockType.IMAGE,
                        runs=parse_inline(alt),
                        alt=alt,
                        target=unquote(target),
                        display_width=float(image_metadata.group(1)),
                    )
                )
                i += 2
                continue

        if line.strip() == "---":
            blocks.append(Block(kind=BlockType.DIVIDER))
            i += 1
            continue

        empty_structural = {
            "#": BlockType.HEADING_1,
            "##": BlockType.HEADING_2,
            "###": BlockType.HEADING_3,
            "-": BlockType.BULLET,
            "1.": BlockType.NUMBERED,
            ">": BlockType.QUOTE,
        }.get(line.strip())
        if empty_structural is not None:
            blocks.append(Block(kind=empty_structural))
            i += 1
            continue

        image = _IMAGE.match(line.strip())
        if image:
            alt, target = image.groups()
            target = unquote(target)
            blocks.append(
                Block(
                    kind=BlockType.IMAGE,
                    runs=parse_inline(alt),
                    alt=alt,
                    target=target,
                )
            )
            i += 1
            continue

        link = _LINK.match(line.strip())
        if link:
            title, target = link.groups()
            target = unquote(target)
            kind = BlockType.FILE if _is_managed_attachment(target) else BlockType.LINK
            blocks.append(
                Block(kind=kind, runs=parse_inline(title), target=target)
            )
            i += 1
            continue

        todo = _TODO.match(line)
        if todo:
            spaces, checked, content = todo.groups()
            blocks.append(
                Block(
                    kind=BlockType.TODO,
                    runs=parse_inline(content),
                    checked=checked.lower() == "x",
                    indent=_indent(spaces),
                )
            )
            i += 1
            continue

        numbered = _NUMBERED.match(line)
        if numbered:
            spaces, content = numbered.groups()
            blocks.append(
                Block(
                    kind=BlockType.NUMBERED,
                    runs=parse_inline(content),
                    indent=_indent(spaces),
                )
            )
            i += 1
            continue

        bullet = _BULLET.match(line)
        if bullet:
            spaces, content = bullet.groups()
            blocks.append(
                Block(
                    kind=BlockType.BULLET,
                    runs=parse_inline(content),
                    indent=_indent(spaces),
                )
            )
            i += 1
            continue

        prefixes = (
            ("### ", BlockType.HEADING_3),
            ("## ", BlockType.HEADING_2),
            ("# ", BlockType.HEADING_1),
            ("> ", BlockType.QUOTE),
        )
        matched = False
        for prefix, kind in prefixes:
            if line.startswith(prefix):
                blocks.append(Block(kind=kind, runs=parse_inline(line[len(prefix) :])))
                matched = True
                break
        if matched:
            i += 1
            continue

        # Unsupported structural Markdown is retained verbatim. StormPad's own
        # safe inline tags may legitimately begin an otherwise normal paragraph.
        supported_inline_prefixes = (
            "<u>",
            '<span data-stormpad-color="',
            '<span data-stormpad-highlight="',
        )
        unsupported_html = line.startswith("<") and not line.startswith(
            supported_inline_prefixes
        )
        if line.startswith(("    ", "|")) or unsupported_html:
            blocks.append(Block(kind=BlockType.RAW, raw=line))
        else:
            blocks.append(Block(kind=BlockType.TEXT, runs=parse_inline(line)))
        i += 1

    return blocks or [Block()]
