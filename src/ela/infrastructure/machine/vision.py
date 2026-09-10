"""The second helper process: reads text out of an image, prints JSON, and may die (M10.3).

Run as ``python -m ela.infrastructure.machine.vision <path> <lang,lang>`` — plus, optionally,
four normalised numbers for a region — and it writes one JSON object on stdout: the lines macOS's
Vision framework read, each with its confidence, and the requested languages it could not use.

**Why a child of ours, when M10.2's was Apple's.** ADR 0029 §3 handed the capture to
``screencapture(1)`` and got architecture rule 33 for free: a child that is not our code cannot
import ours. There is no equivalent here — no binary shipped with macOS does OCR; ``shortcuts``,
``textutil``, ``sips``, ``qlmanage`` and ``mdimport`` were all checked, and nothing under
``/usr/bin``, ``/usr/sbin`` or ``/usr/libexec`` does it. So the child is ours again, rule 33 goes
back to being a thing that is *verified* rather than true by construction, and it verifies it on a
derived subject: a module here with a ``__main__`` guard is a child, and this file has one.

**Why a child at all.** The first attempt at this through ``ctypes`` died of ``SIGSEGV`` before
printing a line. That is ADR 0028 §2's hazard, met again on a different framework, and it is the
whole argument: what can take the interpreter with it runs somewhere the interpreter is expendable.

**This module imports nothing from ELA** (architecture rule 33), and it never names a window-title
key (rule 36). It does not read a permission and does not have one: Vision needs no TCC grant —
measured from a process that was its own responsible process — and it answers identically with the
network denied, which is what "the text does not leave the machine" rests on.

The one call that is not obvious is ``performRequests:error:``, and it is why this is reachable
from ``ctypes`` at all: it is **synchronous**. ScreenCaptureKit was rejected in ADR 0029 §3 because
its API is asynchronous with Objective-C blocks, and hand-building a block literal would have been
the most fragile code in the repository. There is no block here.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import sys
from typing import Any

ACCURATE = 0
"""``VNRequestTextRecognitionLevelAccurate``.

The only level this ships, and the alternative was measured rather than reasoned about. ``fast``
took 20 ms against 108 and read ``Nota pl¢¢ols'.18 s¢*denz¥ slitta 812026-04-03`` where
``accurate`` read the line exactly, confidence 0,50 against 1,00. A level that mangles the digits
of a date and an amount is not a speed/quality trade, it is a generator of false facts that ELA
would write into an artefact somebody later reads. A knob with no second good value is not a knob.
"""


def _library(name: str) -> ctypes.CDLL:
    path = ctypes.util.find_library(name)
    if path is None:  # pragma: no cover - this module only ever runs on macOS
        raise OSError(f"{name} not found")
    return ctypes.CDLL(path)


class _Vision:
    """The Objective-C messages this helper sends, each cast to its exact signature.

    ``objc_msgSend`` must be cast to the shape of the call: on arm64 there is no variadic
    dispatch, and a wrong prototype is what kills the process. Casting once per shape, here, keeps
    the risky part of this file to a handful of functions — the same discipline as ``probe.py``.
    """

    def __init__(self) -> None:
        self._objc = _library("objc")
        _library("Foundation")
        _library("Vision")
        self._objc.objc_getClass.restype = ctypes.c_void_p
        self._objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self._objc.sel_registerName.restype = ctypes.c_void_p
        self._objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = self._objc.objc_msgSend
        pointer = ctypes.c_void_p
        self._send0 = ctypes.cast(send, ctypes.CFUNCTYPE(pointer, pointer, pointer))
        self._send1 = ctypes.cast(send, ctypes.CFUNCTYPE(pointer, pointer, pointer, pointer))
        self._send2 = ctypes.cast(
            send, ctypes.CFUNCTYPE(pointer, pointer, pointer, pointer, pointer)
        )
        self._index = ctypes.cast(send, ctypes.CFUNCTYPE(pointer, pointer, pointer, ctypes.c_long))
        self._count = ctypes.cast(send, ctypes.CFUNCTYPE(ctypes.c_long, pointer, pointer))
        self._float = ctypes.cast(send, ctypes.CFUNCTYPE(ctypes.c_float, pointer, pointer))
        self._utf8 = ctypes.cast(send, ctypes.CFUNCTYPE(ctypes.c_char_p, pointer, pointer))
        self._string = ctypes.cast(
            send, ctypes.CFUNCTYPE(pointer, pointer, pointer, ctypes.c_char_p)
        )
        self._set_long = ctypes.cast(send, ctypes.CFUNCTYPE(None, pointer, pointer, ctypes.c_long))
        self._set_bool = ctypes.cast(send, ctypes.CFUNCTYPE(None, pointer, pointer, ctypes.c_bool))
        self._set_object = ctypes.cast(send, ctypes.CFUNCTYPE(None, pointer, pointer, pointer))
        self._set_rect = ctypes.cast(send, ctypes.CFUNCTYPE(None, pointer, pointer, _CGRect))
        self._perform = ctypes.cast(
            send, ctypes.CFUNCTYPE(ctypes.c_bool, pointer, pointer, pointer, pointer)
        )

    def _selector(self, name: bytes) -> Any:
        return self._objc.sel_registerName(name)

    def _class(self, name: bytes) -> Any:
        return self._objc.objc_getClass(name)

    def _nsstring(self, value: str) -> Any:
        return self._string(
            self._class(b"NSString"),
            self._selector(b"stringWithUTF8String:"),
            value.encode("utf-8"),
        )

    def _text(self, string: Any) -> str | None:
        if not string:
            return None
        raw = self._utf8(string, self._selector(b"UTF8String"))
        return raw.decode("utf-8", "replace") if raw else None

    def _request(self) -> Any:
        request = self._send0(
            self._send0(self._class(b"VNRecognizeTextRequest"), self._selector(b"alloc")),
            self._selector(b"init"),
        )
        self._set_long(request, self._selector(b"setRecognitionLevel:"), ACCURATE)
        return request

    def supported_languages(self) -> list[str]:
        """Which languages this macOS can actually recognise, at the accurate level.

        Thirty of them when this was measured, in 10,6 ms. It is read **before** anything is
        recognised, and that ordering is the whole of ADR 0030 §8: an unsupported language makes
        Vision answer ``ok=True`` with zero observations, so without this check a typo in the
        configuration would report "this screen has no text" forever, silently and wrongly.
        """
        error = ctypes.c_void_p(0)
        languages = self._send1(
            self._request(),
            self._selector(b"supportedRecognitionLanguagesAndReturnError:"),
            ctypes.cast(ctypes.byref(error), ctypes.c_void_p),
        )
        if not languages:
            raise OSError("Vision did not answer which languages it supports")
        count = self._count(languages, self._selector(b"count"))
        found = []
        for index in range(count):
            name = self._text(self._index(languages, self._selector(b"objectAtIndex:"), index))
            if name:
                found.append(name)
        return found

    def recognise(
        self, source: str, languages: list[str], region: list[float] | None
    ) -> list[dict[str, Any]]:
        """Every line of text in the image, with its confidence, top candidate only."""
        url = self._send1(
            self._class(b"NSURL"), self._selector(b"fileURLWithPath:"), self._nsstring(source)
        )
        handler = self._send2(
            self._send0(self._class(b"VNImageRequestHandler"), self._selector(b"alloc")),
            self._selector(b"initWithURL:options:"),
            url,
            self._send0(self._class(b"NSDictionary"), self._selector(b"dictionary")),
        )
        request = self._request()
        self._set_bool(request, self._selector(b"setUsesLanguageCorrection:"), True)
        if languages:
            wanted = self._send0(self._class(b"NSMutableArray"), self._selector(b"array"))
            for language in languages:
                self._set_object(wanted, self._selector(b"addObject:"), self._nsstring(language))
            self._set_object(request, self._selector(b"setRecognitionLanguages:"), wanted)
        if region is not None:
            x, y, width, height = region
            self._set_rect(
                request,
                self._selector(b"setRegionOfInterest:"),
                _CGRect(_CGPoint(x, y), _CGSize(width, height)),
            )
        requests = self._send0(self._class(b"NSMutableArray"), self._selector(b"array"))
        self._set_object(requests, self._selector(b"addObject:"), request)
        error = ctypes.c_void_p(0)
        performed = self._perform(
            handler,
            self._selector(b"performRequests:error:"),
            requests,
            ctypes.cast(ctypes.byref(error), ctypes.c_void_p),
        )
        if not performed:
            described = self._text(self._send0(error, self._selector(b"localizedDescription")))
            raise OSError(described or "Vision could not read this image")
        return self._lines(self._send0(request, self._selector(b"results")))

    def _lines(self, results: Any) -> list[dict[str, Any]]:
        found = []
        for index in range(self._count(results, self._selector(b"count"))):
            observation = self._index(results, self._selector(b"objectAtIndex:"), index)
            candidates = self._index(observation, self._selector(b"topCandidates:"), 1)
            if self._count(candidates, self._selector(b"count")) == 0:
                continue
            best = self._index(candidates, self._selector(b"objectAtIndex:"), 0)
            text = self._text(self._send0(best, self._selector(b"string")))
            if text is None:
                continue
            confidence = float(self._float(best, self._selector(b"confidence")))
            found.append({"text": text, "confidence": min(max(confidence, 0.0), 1.0)})
        return found


class _CGPoint(ctypes.Structure):
    _fields_ = (("x", ctypes.c_double), ("y", ctypes.c_double))


class _CGSize(ctypes.Structure):
    _fields_ = (("width", ctypes.c_double), ("height", ctypes.c_double))


class _CGRect(ctypes.Structure):
    """``regionOfInterest``: normalised to the image, origin at the **bottom left**.

    The convention is the framework's and it stays here. Whoever calls ELA thinks in screen
    coordinates, top-left, and the conversion happens in :mod:`ela.tools.screen_text` where a
    runner can cover it — a flipped rectangle does not raise, it returns the text of the wrong
    half (ADR 0030 §12).
    """

    _fields_ = (("origin", _CGPoint), ("size", _CGSize))


def read(source: str, languages: list[str], region: list[float] | None) -> dict[str, Any]:
    """The whole answer: the lines, and the languages that were asked for and do not exist."""
    vision = _Vision()
    unsupported = sorted(set(languages) - set(vision.supported_languages()))
    if unsupported:
        # Not an optimisation: recognising anyway would answer "no text on this screen", which is
        # a different fact from "ELA was configured with a language macOS does not have", and the
        # two must not arrive as the same value (ADR 0030 §8).
        return {"lines": [], "unsupported_languages": unsupported}
    return {"lines": vision.recognise(source, languages, region), "unsupported_languages": []}


def main(argv: list[str]) -> int:
    """``argv``: the image, a comma-separated language list, and optionally four region numbers."""
    source = argv[1] if len(argv) > 1 else ""
    languages = [part for part in (argv[2] if len(argv) > 2 else "").split(",") if part]
    region = [float(value) for value in argv[3:7]] if len(argv) > 6 else None
    json.dump(read(source, languages, region), sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point of the child process
    sys.exit(main(sys.argv))
