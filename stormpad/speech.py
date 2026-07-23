"""Native text-to-speech for the "Speak Selection" feature.

Isolated, testable controller around a single ``AVSpeechSynthesizer``. The
AppKit/AVFoundation dependency is confined to :class:`AVSpeechBackend`; the
:class:`SpeechController` logic (validation, "new speech stops previous",
speaking state, cleanup) is exercised in tests with an injected fake backend.

No deprecated ``NSSpeechSynthesizer``, no network, no cloud. Uses the current
system default voice/configuration.

Verified imports (PyObjC 12.x): ``AVSpeechSynthesizer``, ``AVSpeechUtterance``,
and ``AVSpeechBoundaryImmediate`` all come from the top-level ``AVFoundation``
module (also available via ``AVFAudio``); ``AVSpeechBoundaryImmediate == 0``.
"""

from __future__ import annotations

from typing import Protocol


class SpeechUnavailableError(RuntimeError):
    """The AVFoundation speech binding could not be loaded."""


class SpeechBackend(Protocol):
    """Minimal speech backend contract (AVFoundation or a test fake)."""

    def speak(self, text: str) -> None: ...

    def stop(self) -> None: ...

    @property
    def is_speaking(self) -> bool: ...


def make_av_backend() -> SpeechBackend:
    """Create the AVFoundation-backed speech backend.

    Raises :class:`SpeechUnavailableError` (a clear, catchable error) if the
    binding is missing, rather than failing mysteriously deep in the UI.
    """
    try:
        from AVFoundation import (  # noqa: PLC0415
            AVSpeechBoundaryImmediate,
            AVSpeechSynthesizer,
            AVSpeechUtterance,
        )
    except Exception as exc:  # pragma: no cover - only hit if binding absent
        raise SpeechUnavailableError(
            "AVFoundation speech binding is unavailable; "
            "install pyobjc-framework-AVFoundation."
        ) from exc

    class _AVBackend:
        def __init__(self) -> None:
            # Strongly retained for the backend's lifetime.
            self._synth = AVSpeechSynthesizer.alloc().init()

        def speak(self, text: str) -> None:
            if self._synth.isSpeaking():
                self._synth.stopSpeakingAtBoundary_(AVSpeechBoundaryImmediate)
            utterance = AVSpeechUtterance.speechUtteranceWithString_(text)
            self._synth.speakUtterance_(utterance)

        def stop(self) -> None:
            if self._synth.isSpeaking():
                self._synth.stopSpeakingAtBoundary_(AVSpeechBoundaryImmediate)

        @property
        def is_speaking(self) -> bool:
            return bool(self._synth.isSpeaking())

    return _AVBackend()


class SpeechController:
    """Owns one speech backend and mediates all speak/stop requests."""

    def __init__(self, backend: SpeechBackend | None = None, *, backend_factory=make_av_backend):
        self._backend = backend
        self._factory = backend_factory

    def _ensure_backend(self) -> SpeechBackend:
        if self._backend is None:
            self._backend = self._factory()
        return self._backend

    def speak(self, text: str) -> bool:
        """Speak ``text`` exactly. Returns False if there's nothing to speak.

        The selection is trimmed only to *validate* it; the original text
        (including its internal punctuation/wording) is spoken. Any current
        utterance is stopped first.
        """
        if not text or not text.strip():
            return False
        backend = self._ensure_backend()
        backend.stop()
        backend.speak(text)
        return True

    def stop(self) -> None:
        """Stop any current utterance immediately (no-op if idle)."""
        if self._backend is not None:
            self._backend.stop()

    @property
    def is_speaking(self) -> bool:
        return bool(self._backend is not None and self._backend.is_speaking)

    def cleanup(self) -> None:
        """Stop speech on window close / app termination."""
        self.stop()
