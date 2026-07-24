"""Pure block and inline-formatting model for StormPad.

The native editor maps these values to attributed strings, while the parser and
serializer map them to human-readable Markdown.  No AppKit types live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class BlockType(StrEnum):
    TEXT = "text"
    HEADING_1 = "heading_1"
    HEADING_2 = "heading_2"
    HEADING_3 = "heading_3"
    TODO = "todo"
    BULLET = "bullet"
    NUMBERED = "numbered"
    QUOTE = "quote"
    DIVIDER = "divider"
    LINK = "link"
    IMAGE = "image"
    FILE = "file"
    TRANSCRIPT = "transcript"
    RAW = "raw"  # unsupported Markdown preserved verbatim


class MarkType(StrEnum):
    BOLD = "bold"
    ITALIC = "italic"
    UNDERLINE = "underline"
    TEXT_COLOR = "text_color"
    HIGHLIGHT = "highlight"
    LINK = "link"


COLOR_TOKENS: tuple[str, ...] = (
    "default",
    "gray",
    "blue",
    "cyan",
    "green",
    "yellow",
    "orange",
    "red",
    "purple",
    "brown",
    "pink",
)

PARAGRAPH_BLOCK_TYPES: frozenset[BlockType] = frozenset(
    {
        BlockType.TEXT,
        BlockType.HEADING_1,
        BlockType.HEADING_2,
        BlockType.HEADING_3,
        BlockType.TODO,
        BlockType.BULLET,
        BlockType.NUMBERED,
        BlockType.QUOTE,
    }
)


@dataclass(frozen=True, order=True)
class InlineMark:
    kind: MarkType
    value: str | None = None

    def __post_init__(self) -> None:
        if self.kind in (MarkType.TEXT_COLOR, MarkType.HIGHLIGHT):
            if self.value not in COLOR_TOKENS:
                raise ValueError(f"unsupported StormPad color token: {self.value!r}")
        elif self.kind == MarkType.LINK:
            if not self.value:
                raise ValueError("link marks require a target")
        elif self.value is not None:
            raise ValueError(f"{self.kind.value} marks do not accept a value")


@dataclass(frozen=True)
class InlineRun:
    text: str
    marks: tuple[InlineMark, ...] = ()

    def __post_init__(self) -> None:
        normalized = tuple(sorted(set(self.marks)))
        object.__setattr__(self, "marks", normalized)


def coalesce_runs(runs: list[InlineRun]) -> list[InlineRun]:
    """Drop empty runs and merge adjacent runs carrying the same marks."""
    result: list[InlineRun] = []
    for run in runs:
        if not run.text:
            continue
        if result and result[-1].marks == run.marks:
            previous = result[-1]
            result[-1] = InlineRun(previous.text + run.text, previous.marks)
        else:
            result.append(run)
    return result


def split_runs(runs: list[InlineRun], offset: int) -> tuple[list[InlineRun], list[InlineRun]]:
    """Split inline runs at a plain-text offset while retaining all marks."""
    offset = max(0, offset)
    before: list[InlineRun] = []
    after: list[InlineRun] = []
    consumed = 0
    for run in runs:
        run_end = consumed + len(run.text)
        if run_end <= offset:
            before.append(run)
        elif consumed >= offset:
            after.append(run)
        else:
            cut = offset - consumed
            before.append(InlineRun(run.text[:cut], run.marks))
            after.append(InlineRun(run.text[cut:], run.marks))
        consumed = run_end
    return coalesce_runs(before), coalesce_runs(after)


def remove_inline_mark(runs: list[InlineRun], kind: MarkType) -> list[InlineRun]:
    """Remove one semantic mark from every run without changing visible text."""
    return coalesce_runs(
        [
            InlineRun(
                run.text,
                tuple(mark for mark in run.marks if mark.kind != kind),
            )
            for run in runs
        ]
    )


@dataclass
class Block:
    kind: BlockType = BlockType.TEXT
    runs: list[InlineRun] = field(default_factory=list)
    checked: bool = False
    indent: int = 0
    target: str | None = None
    alt: str | None = None
    raw: str | None = None
    collapsed: bool = False

    def __post_init__(self) -> None:
        self.runs = coalesce_runs(self.runs)
        self.indent = max(0, int(self.indent))
        if self.kind == BlockType.RAW and self.raw is None:
            self.raw = self.text

    @classmethod
    def text_block(cls, text: str = "", kind: BlockType = BlockType.TEXT) -> Block:
        return cls(kind=kind, runs=[InlineRun(text)] if text else [])

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)

    def with_text(self, text: str) -> Block:
        self.runs = [InlineRun(text)] if text else []
        return self

    @property
    def is_empty(self) -> bool:
        return not self.text and self.kind not in (
            BlockType.DIVIDER,
            BlockType.IMAGE,
            BlockType.FILE,
            BlockType.TRANSCRIPT,
            BlockType.RAW,
        )


def insert_block(
    blocks: list[Block], index: int, block: Block | None = None, *, above: bool = False
) -> tuple[list[Block], int]:
    """Return a copy with a block inserted beside ``index`` and its new index."""
    result = list(blocks)
    if not result:
        result.append(block or Block())
        return result, 0
    index = min(max(index, 0), len(result) - 1)
    destination = index if above else index + 1
    result.insert(destination, block or Block())
    return result, destination


def convert_block(block: Block, kind: BlockType) -> Block:
    """Convert an editable block while retaining its text and inline marks."""
    if kind == BlockType.RAW:
        raise ValueError("raw is an internal preservation block")
    return Block(
        kind=kind,
        runs=list(block.runs),
        checked=block.checked if kind == BlockType.TODO else False,
        indent=(
            block.indent if kind in (BlockType.TODO, BlockType.BULLET, BlockType.NUMBERED) else 0
        ),
        target=block.target if kind in (BlockType.LINK, BlockType.IMAGE, BlockType.FILE) else None,
        alt=block.alt if kind == BlockType.IMAGE else None,
        collapsed=block.collapsed if kind == BlockType.TRANSCRIPT else False,
    )


def convert_selected_blocks(
    blocks: list[Block], indices: list[int], kind: BlockType
) -> list[Block]:
    """Convert compatible selected paragraphs while retaining order/content."""
    if kind not in PARAGRAPH_BLOCK_TYPES:
        raise ValueError(f"{kind.value} is not a paragraph block type")
    selected = set(indices)
    return [
        convert_block(block, kind)
        if index in selected and block.kind in PARAGRAPH_BLOCK_TYPES
        else block
        for index, block in enumerate(blocks)
    ]


def move_block(blocks: list[Block], index: int, offset: int) -> tuple[list[Block], int]:
    """Move one block by ``offset`` (-1/+1), clamped to the list."""
    if not blocks:
        return [], 0
    index = min(max(index, 0), len(blocks) - 1)
    destination = min(max(index + offset, 0), len(blocks) - 1)
    result = list(blocks)
    if destination != index:
        block = result.pop(index)
        result.insert(destination, block)
    return result, destination


def apply_block_command(
    blocks: list[Block],
    index: int,
    block: Block,
    *,
    option_pressed: bool = False,
) -> tuple[list[Block], int]:
    """Apply an Add Block command at an explicit block index.

    An empty text block is converted in place. Otherwise the requested block is
    inserted below, or above while Option is held. Keeping this in the pure
    block layer makes menu commands deterministic and independently testable.
    """
    result = list(blocks) or [Block()]
    index = min(max(index, 0), len(result) - 1)
    current = result[index]
    if current.kind == BlockType.TEXT and current.is_empty:
        converted = convert_block(current, block.kind)
        converted.target = block.target
        converted.alt = block.alt
        converted.runs = list(block.runs)
        converted.checked = block.checked
        converted.indent = block.indent
        converted.collapsed = block.collapsed
        result[index] = converted
        return result, index
    return insert_block(result, index, block, above=option_pressed)


def reorder_blocks(
    blocks: list[Block], source_index: int, insertion_index: int
) -> tuple[list[Block], int]:
    """Move a block to an insertion boundary while preserving its payload.

    ``insertion_index`` is a boundary in the original list (0 through
    ``len(blocks)``), matching native drag-and-drop destination semantics.
    """
    if not blocks:
        return [], 0
    source = min(max(source_index, 0), len(blocks) - 1)
    boundary = min(max(insertion_index, 0), len(blocks))
    result = list(blocks)
    moving = result.pop(source)
    if boundary > source:
        boundary -= 1
    destination = min(max(boundary, 0), len(result))
    result.insert(destination, moving)
    return result, destination


def next_block_after_return(block: Block) -> Block:
    """Natural block produced by Return after a non-empty block."""
    if block.kind in (BlockType.BULLET, BlockType.NUMBERED, BlockType.TODO):
        return Block(kind=block.kind, indent=block.indent)
    return Block()


def empty_return_result(block: Block) -> Block:
    """An empty list/to-do/quote/heading exits to a normal text block."""
    if block.kind != BlockType.TEXT:
        return Block()
    return block


def backspace_empty_result(block: Block) -> Block:
    """Backspace on an empty non-text block converts it to normal text."""
    return Block() if block.is_empty and block.kind != BlockType.TEXT else block


def toggle_todo(block: Block) -> Block:
    if block.kind != BlockType.TODO:
        raise ValueError("only to-do blocks can be toggled")
    return Block(
        kind=block.kind,
        runs=list(block.runs),
        checked=not block.checked,
        indent=block.indent,
    )
