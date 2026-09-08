"""The helper process: reads macOS, prints JSON, and is allowed to die (M10.1, ADR 0028 §2).

Run as ``python -m ela.infrastructure.perception.probe SENSORS,SESSION`` and it writes one JSON
object on stdout — the fields of :class:`~ela.domain.RawObservation` belonging to the families it
was asked for, and nothing else.

**Why this is a separate process at all.** The status of the camera and microphone permissions —
the whole point of "a missing permission is a first-class citizen" — has no public C API. It
exists only as an Objective-C message, and a mistaken ``objc_msgSend`` through ``ctypes`` raises
an Objective-C exception, which Python cannot catch: ``libc++abi: terminating``, interpreter
gone. Not a traceback — the end of ELA. Reading a permission is also an XPC call to ``tccd``, a
daemon that can decline to answer, and a hang is not something an exception handler fixes.
A child process with a timeout covers the exception, the crash and the hang with one mechanism,
and its failure lands on a value the domain already has: not observable.

**This module imports nothing from ELA** (architecture rule 33). What has to be able to die on
its own must not carry the Core's import graph with it, and the Core must not be able to reach
in here. The two sides agree on a JSON object and on nothing else.

**What it does not read** (§57). ``CGSessionCopyCurrentDictionary`` also carries the user's full
name in ``kCGSessionLongUserNameKey``. This reads **by named key** and never copies the
dictionary: a snapshot that drags personal data along because nobody looked inside is exactly how
that mistake gets made.

Every reading that fails yields ``null`` for its own key rather than a non-zero exit: the child
exits non-zero only when it cannot start at all, so a Mac with no camera is an answer and not a
failure.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import struct
import sys
from typing import Any

SENSORS = "SENSORS"
SESSION = "SESSION"
PERMISSIONS = "PERMISSIONS"

AV_VIDEO = b"vide"
AV_AUDIO = b"soun"

_HID_STATE = 1
"""``kCGEventSourceStateHIDSystemState``."""
_ANY_INPUT = 0xFFFFFFFF
"""``kCGAnyInputEventType``."""


def _library(name: str) -> ctypes.CDLL:
    path = ctypes.util.find_library(name)
    if path is None:  # pragma: no cover - this module only ever runs on macOS
        raise OSError(f"{name} not found")
    return ctypes.CDLL(path)


class _Objc:
    """The few Objective-C messages this probe sends, each with an explicit prototype.

    ``objc_msgSend`` must be cast to the exact signature of the call: on arm64 there is no
    variadic dispatch, and a wrong prototype is the mistake that kills the process. Casting once
    per shape, here, is what keeps the risky part of this file to four functions.
    """

    def __init__(self) -> None:
        self._objc = _library("objc")
        _library("AVFoundation")
        self._objc.objc_getClass.restype = ctypes.c_void_p
        self._objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self._objc.sel_registerName.restype = ctypes.c_void_p
        self._objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = self._objc.objc_msgSend
        self._string = ctypes.cast(
            send,
            ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p),
        )
        self._object = ctypes.cast(
            send,
            ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
        )
        self._long = ctypes.cast(
            send, ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
        )
        self._count = ctypes.cast(
            send, ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
        )
        self._ns_string = self._objc.objc_getClass(b"NSString")
        self._capture_device = self._objc.objc_getClass(b"AVCaptureDevice")
        self._media = {
            media: self._string(
                self._ns_string, self._objc.sel_registerName(b"stringWithUTF8String:"), media
            )
            for media in (AV_VIDEO, AV_AUDIO)
        }

    def device_count(self, media: bytes) -> int:
        """How many capture devices of this media type exist. Needs no permission."""
        devices = self._object(
            self._capture_device,
            self._objc.sel_registerName(b"devicesWithMediaType:"),
            self._media[media],
        )
        return int(self._count(devices, self._objc.sel_registerName(b"count")))

    def authorization_status(self, media: bytes) -> int:
        """``AVAuthorizationStatus`` for this media type: asks, and never prompts."""
        return int(
            self._long(
                self._capture_device,
                self._objc.sel_registerName(b"authorizationStatusForMediaType:"),
                self._media[media],
            )
        )


def _four_char(code: str) -> int:
    return int(struct.unpack(">I", code.encode())[0])


class _AudioObjectPropertyAddress(ctypes.Structure):
    _fields_ = (
        ("mSelector", ctypes.c_uint32),
        ("mScope", ctypes.c_uint32),
        ("mElement", ctypes.c_uint32),
    )


def _microphone_in_use(core_audio: ctypes.CDLL) -> bool:
    """Whether the default input device is running **for anybody** — not only for ELA.

    ``kAudioDevicePropertyDeviceIsRunningSomewhere``: the one public, exact and nearly free answer
    to the question §11 exists to answer. There is no equivalent for the camera, which is why the
    webcam's state is declared not observable instead of being guessed.
    """
    device = _audio_property(core_audio, 1, "dIn ")
    return _audio_property(core_audio, device, "gone") != 0


def _audio_property(core_audio: ctypes.CDLL, obj: int, selector: str) -> int:
    address = _AudioObjectPropertyAddress(_four_char(selector), _four_char("glob"), 0)
    size = ctypes.c_uint32(4)
    out = ctypes.c_uint32(0)
    status = core_audio.AudioObjectGetPropertyData(
        ctypes.c_uint32(obj), ctypes.byref(address), 0, None, ctypes.byref(size), ctypes.byref(out)
    )
    if status != 0:
        raise OSError(f"CoreAudio property {selector!r} failed with {status}")
    return int(out.value)


def _session_flag(core_graphics: ctypes.CDLL, core_foundation: ctypes.CDLL, key: bytes) -> bool:
    """One named key of the current session dictionary, as a boolean; absent means ``False``.

    Reads *this* key and nothing else. The dictionary is never copied out (§57).
    """
    core_graphics.CGSessionCopyCurrentDictionary.restype = ctypes.c_void_p
    session = core_graphics.CGSessionCopyCurrentDictionary()
    if not session:
        raise OSError("no window server session")
    try:
        core_foundation.CFStringCreateWithCString.restype = ctypes.c_void_p
        core_foundation.CFStringCreateWithCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        name = core_foundation.CFStringCreateWithCString(None, key, 0x08000100)
        core_foundation.CFDictionaryGetValue.restype = ctypes.c_void_p
        core_foundation.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        value = core_foundation.CFDictionaryGetValue(ctypes.c_void_p(session), name)
        core_foundation.CFRelease(ctypes.c_void_p(name))
        if not value:
            return False
        number = ctypes.c_int64(0)
        core_foundation.CFNumberGetValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_void_p,
        ]
        if core_foundation.CFNumberGetValue(ctypes.c_void_p(value), 4, ctypes.byref(number)):
            return number.value != 0
        core_foundation.CFBooleanGetValue.restype = ctypes.c_bool
        core_foundation.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
        return bool(core_foundation.CFBooleanGetValue(ctypes.c_void_p(value)))
    finally:
        core_foundation.CFRelease(ctypes.c_void_p(session))


def _displays(core_graphics: ctypes.CDLL) -> int:
    count = ctypes.c_uint32(0)
    identifiers = (ctypes.c_uint32 * 32)()
    status = core_graphics.CGGetActiveDisplayList(32, identifiers, ctypes.byref(count))
    if status != 0:
        raise OSError(f"CGGetActiveDisplayList failed with {status}")
    return int(count.value)


def _read(name: str, reading: Any) -> Any:
    """Run one reading; anything that goes wrong is ``null`` for that key alone.

    The child's own fail-safe, and the reason a Mac with no camera is an answer instead of a
    non-zero exit: one unreadable fact must not cost the caller the other nine.
    """
    del name
    try:
        return reading()
    except Exception:  # noqa: BLE001 — one unreadable fact, not a failed observation
        return None


def observe(families: frozenset[str]) -> dict[str, Any]:
    """Every field of the requested families, as primitives. No domain vocabulary (rule 34)."""
    readings: dict[str, Any] = {}
    if SENSORS in families:
        objc = _Objc()
        core_audio = _library("CoreAudio")
        readings["camera_count"] = _read("camera_count", lambda: objc.device_count(AV_VIDEO))
        readings["microphone_count"] = _read(
            "microphone_count", lambda: objc.device_count(AV_AUDIO)
        )
        readings["microphone_in_use"] = _read(
            "microphone_in_use", lambda: _microphone_in_use(core_audio)
        )
    if SESSION in families:
        core_graphics = _library("CoreGraphics")
        core_foundation = _library("CoreFoundation")
        core_graphics.CGDisplayIsAsleep.restype = ctypes.c_bool
        core_graphics.CGMainDisplayID.restype = ctypes.c_uint32
        core_graphics.CGEventSourceSecondsSinceLastEventType.restype = ctypes.c_double
        core_graphics.CGEventSourceSecondsSinceLastEventType.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
        ]
        readings["display_count"] = _read("display_count", lambda: _displays(core_graphics))
        readings["display_asleep"] = _read(
            "display_asleep",
            lambda: bool(core_graphics.CGDisplayIsAsleep(core_graphics.CGMainDisplayID())),
        )
        readings["screen_locked"] = _read(
            "screen_locked",
            lambda: _session_flag(core_graphics, core_foundation, b"CGSSessionScreenIsLocked"),
        )
        readings["on_console"] = _read(
            "on_console",
            lambda: _session_flag(core_graphics, core_foundation, b"kCGSSessionOnConsoleKey"),
        )
        readings["idle_seconds"] = _read(
            "idle_seconds",
            lambda: round(
                float(core_graphics.CGEventSourceSecondsSinceLastEventType(_HID_STATE, _ANY_INPUT)),
                3,
            ),
        )
    if PERMISSIONS in families:
        objc = _Objc()
        core_graphics = _library("CoreGraphics")
        core_graphics.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        readings["camera_permission"] = _read(
            "camera_permission", lambda: objc.authorization_status(AV_VIDEO)
        )
        readings["microphone_permission"] = _read(
            "microphone_permission", lambda: objc.authorization_status(AV_AUDIO)
        )
        readings["screen_recording_permission"] = _read(
            "screen_recording_permission",
            lambda: bool(core_graphics.CGPreflightScreenCaptureAccess()),
        )
    return readings


def main(argv: list[str]) -> int:
    """``argv[1]`` is a comma-separated list of families; the answer goes to stdout as JSON."""
    requested = frozenset(part for part in (argv[1] if len(argv) > 1 else "").split(",") if part)
    json.dump(observe(requested), sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point of the child process
    sys.exit(main(sys.argv))
