"""Tests for the speech controller using an injected fake backend.

No real audio is played; the AVFoundation backend is never constructed here.
"""

from __future__ import annotations

from stormpad.speech import SpeechController


class FakeBackend:
    """Records speak/stop calls and tracks a speaking flag."""

    def __init__(self) -> None:
        self.events: list = []
        self._speaking = False

    def speak(self, text: str) -> None:
        self.events.append(("speak", text))
        self._speaking = True

    def stop(self) -> None:
        self.events.append(("stop",))
        self._speaking = False

    @property
    def is_speaking(self) -> bool:
        return self._speaking


def make_controller():
    backend = FakeBackend()
    return SpeechController(backend=backend), backend


def test_empty_selection_rejected():
    ctrl, backend = make_controller()
    assert ctrl.speak("") is False
    assert ctrl.speak("   \n\t") is False
    assert backend.events == []  # backend never touched
    assert ctrl.is_speaking is False


def test_speak_exact_text_retained():
    ctrl, backend = make_controller()
    assert ctrl.speak("  Hello, world.  ") is True
    # Speaks the ORIGINAL text (only trimmed for validation), and stops first.
    assert backend.events == [("stop",), ("speak", "  Hello, world.  ")]
    assert ctrl.is_speaking is True


def test_new_speech_stops_previous():
    ctrl, backend = make_controller()
    ctrl.speak("first")
    ctrl.speak("second")
    assert backend.events == [
        ("stop",),
        ("speak", "first"),
        ("stop",),
        ("speak", "second"),
    ]


def test_stop_and_state():
    ctrl, backend = make_controller()
    ctrl.speak("hi")
    assert ctrl.is_speaking is True
    ctrl.stop()
    assert ctrl.is_speaking is False
    assert backend.events[-1] == ("stop",)


def test_cleanup_requests_stop():
    ctrl, backend = make_controller()
    ctrl.speak("hi")
    backend.events.clear()
    ctrl.cleanup()
    assert backend.events == [("stop",)]
    assert ctrl.is_speaking is False


def test_stop_when_idle_is_safe():
    ctrl, backend = make_controller()
    ctrl.stop()  # never spoke
    assert backend.events == [("stop",)]  # backend.stop is itself a no-op-safe call
    assert ctrl.is_speaking is False


def test_lazy_backend_not_created_for_empty_text():
    created = []

    def factory():
        created.append(1)
        return FakeBackend()

    ctrl = SpeechController(backend_factory=factory)
    assert ctrl.speak("") is False
    assert created == []  # empty text must not construct the AV backend
    ctrl.speak("hi")
    assert created == [1]
