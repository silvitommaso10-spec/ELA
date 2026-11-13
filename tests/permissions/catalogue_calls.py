"""One valid call for every capability of the production catalogue (M13.14, ADR 0068; answer 21).

What a property «on every capability of the catalogue» needs: the catalogue the composition builds,
with declared sites, folders and programs, and arguments that satisfy each schema and sit inside
each scope. **A closed world**: :func:`tests.permissions.test_guardian_policies` asserts the keys
are the catalogue's ids, so a capability added tomorrow cannot be left out of the property.
"""

from __future__ import annotations

from typing import Any, Final

from ela.permissions import DEFAULT_NOTES_SCOPE, CapabilityRegistry, production_catalogue
from tests.permissions.policy_support import MODEL

SITE: Final = "httpbin.org"
FOLDER: Final = "ELA"
PROGRAM: Final = "git"

CATALOGUE: Final[CapabilityRegistry] = production_catalogue(
    sites=(SITE,), fs_scope=FOLDER, programs=(PROGRAM,), guided_model=MODEL
)

_READ: Final = {"site": SITE, "path": "/", "purpose": "la prova"}
_ACT: Final = {
    "site": SITE,
    "path": "/forms/post",
    "fill": [["#custname", "ELA"]],
    "click": "#submit",
    "expect_text": "ELA",
    "purpose": "la prova",
}
_SESSION: Final = {
    "goal": "Apri il modulo e leggilo.",
    "sites": [SITE],
    "max_cost_usd": "1.10",
    "looks": 5,
    "seconds": 300,
}
_DOWNLOAD: Final = {
    "site": SITE,
    "path": "/image/png",
    "file": f"{FOLDER}/prova.png",
    "overwrite": False,
    "purpose": "la prova",
}
_UPLOAD: Final = {
    "site": SITE,
    "path": "/forms/post",
    "file": f"{FOLDER}/prova.txt",
    "file_field": "#file",
    "expect_text": "ok",
    "purpose": "la prova",
}

CALLS: Final[dict[str, dict[str, Any]]] = {
    "core.echo": {"message": "ciao"},
    "workspace.write_note": {"path": f"{DEFAULT_NOTES_SCOPE}/a.md", "body": "x"},
    "model.complete": {"input": "riassumi"},
    "perception.capture_screen": {"purpose": "la prova"},
    "perception.read_screen_text": {"capture_id": "una-cattura", "purpose": "la prova"},
    "voice.speak": {"text": "ciao", "purpose": "la prova"},
    "voice.speak_online": {"text": "ciao", "purpose": "la prova"},
    "perception.listen": {"purpose": "la prova", "seconds": 5},
    "fs.read": {"path": f"{FOLDER}/a.md", "purpose": "la prova"},
    "fs.write": {
        "path": f"{FOLDER}/a.md",
        "body": "una riga",
        "overwrite": False,
        "purpose": "la prova",
    },
    "terminal.run": {"program": PROGRAM, "args": ["status"], "purpose": "la prova"},
    "browser.read": _READ,
    "browser.act": _ACT,
    "browser.guided": _SESSION,
    "browser.read_as_you": _READ,
    "browser.act_as_you": _ACT,
    "browser.login": {
        "site": SITE,
        "path": "/login",
        "username_field": "#user",
        "password_field": "#word",
        "click": "#go",
        "purpose": "la prova",
    },
    "browser.guided_as_you": _SESSION,
    "browser.download": _DOWNLOAD,
    "browser.download_as_you": _DOWNLOAD,
    "browser.upload": _UPLOAD,
    "browser.upload_as_you": _UPLOAD,
}
