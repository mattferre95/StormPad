"""Optional Project icons — a curated SF Symbol or a single emoji.

Pure and AppKit-free. An icon is stored as ``"symbol:<name>"`` or
``"emoji:<char>"``; ``None`` means "use the default folder". Values are
normalised defensively so an unknown symbol, an old value, or a corrupted
metadata file falls back to the folder instead of breaking a Project row.

Image uploads and custom icon files are intentionally out of scope.
"""

from __future__ import annotations

DEFAULT_PROJECT_SYMBOL = "folder"
SYMBOL_PREFIX = "symbol:"
EMOJI_PREFIX = "emoji:"

# Curated SF Symbols offered in the picker. Availability is still checked at
# render time — a symbol missing on this macOS falls back to the folder.
PROJECT_SYMBOLS: tuple[str, ...] = (
    "folder",
    "folder.fill",
    "bolt",
    "lightbulb",
    "briefcase",
    "hammer",
    "paintbrush",
    "music.note",
    "camera",
    "film",
    "gamecontroller",
    "terminal",
    "chevron.left.forwardslash.chevron.right",  # "code"
    "globe",
    "heart",
    "star",
    "bookmark",
    "flag",
    "person.2",
    "waveform",
)

# A handful of emoji offered for one-click selection. Any other single emoji can
# still be typed in, so this is a shortcut rather than the allowed set.
SUGGESTED_EMOJI: tuple[str, ...] = (
    "📁",
    "⚡",
    "💡",
    "🎯",
    "🚀",
    "📝",
    "🎨",
    "🎵",
    "📸",
    "🎬",
    "🎮",
    "🛠️",
    "🌍",
    "❤️",
    "⭐",
)

# A ZWJ family emoji is 7 code points; nothing legitimate needs more.
MAX_EMOJI_CODEPOINTS = 8


def is_supported_emoji(value: str) -> bool:
    """True for a single non-ASCII pictographic cluster.

    Deliberately permissive about *which* emoji (any Unicode cluster the system
    font can draw is fine) and strict about *how many* — one icon, never a word
    or a sentence.
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate or len(candidate) > MAX_EMOJI_CODEPOINTS:
        return False
    # Reject plain text: any ASCII character means this is not an emoji.
    return all(ord(char) > 127 for char in candidate)


def normalize_project_icon(value: str | None) -> str | None:
    """Return a canonical icon value, or ``None`` to mean the default folder.

    Accepts the canonical prefixed forms, a bare curated symbol name, or a bare
    emoji. Everything else — an unknown symbol, free text, a path — normalises
    to ``None`` so the row safely shows a folder.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.startswith(SYMBOL_PREFIX):
        name = candidate[len(SYMBOL_PREFIX) :].strip()
        return f"{SYMBOL_PREFIX}{name}" if name in PROJECT_SYMBOLS else None
    if candidate.startswith(EMOJI_PREFIX):
        glyph = candidate[len(EMOJI_PREFIX) :].strip()
        return f"{EMOJI_PREFIX}{glyph}" if is_supported_emoji(glyph) else None
    if candidate in PROJECT_SYMBOLS:
        return f"{SYMBOL_PREFIX}{candidate}"
    if is_supported_emoji(candidate):
        return f"{EMOJI_PREFIX}{candidate}"
    return None


def project_icon_kind(value: str | None) -> str:
    """``"symbol"``, ``"emoji"``, or ``"default"`` for a stored icon value."""
    normalized = normalize_project_icon(value)
    if normalized is None:
        return "default"
    return "symbol" if normalized.startswith(SYMBOL_PREFIX) else "emoji"


def project_icon_payload(value: str | None) -> str:
    """The symbol name or emoji glyph to draw; the folder symbol by default."""
    normalized = normalize_project_icon(value)
    if normalized is None:
        return DEFAULT_PROJECT_SYMBOL
    prefix = SYMBOL_PREFIX if normalized.startswith(SYMBOL_PREFIX) else EMOJI_PREFIX
    return normalized[len(prefix) :]


def symbol_icon(name: str) -> str | None:
    """Canonical value for a curated symbol name (``None`` if not curated)."""
    return normalize_project_icon(f"{SYMBOL_PREFIX}{name}")


def emoji_icon(glyph: str) -> str | None:
    """Canonical value for an emoji (``None`` if it is not a single emoji)."""
    return normalize_project_icon(f"{EMOJI_PREFIX}{glyph}")
