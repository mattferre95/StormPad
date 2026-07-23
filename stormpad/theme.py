"""Semantic theme tokens for StormPad.

Three themes — Storm Blue (default), Light, Deep Dark — are defined as complete
semantic token sets (app background, sidebar, selection, accent, transcript,
success/destructive, text tiers, etc.), mirroring the supplied design handoff
token tables. Colors live here only; view code references semantic names, never
literals. Implemented in Phase 5 (tokens defined pure here; NSColor resolution
in the app layer).
"""

from __future__ import annotations

# TODO(phase-5): Theme dataclass + STORM_BLUE / LIGHT / DEEP_DARK token dicts
# transcribed from the design handoff, plus a hex -> NSColor resolver used by
# the views. Storm Blue is the default.
