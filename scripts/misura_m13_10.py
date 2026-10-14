"""La misura di M13.10 che vuole Tommaso: i selettori di WhatsApp Web, trovati per attributi.

    uv run python scripts/misura_m13_10.py

**La lancia Tommaso, dal suo Terminale, dal repository**, con il telefono vicino (decisione 47 della
review della SPEC di M13.10). Apre il browser con i tuoi account **come lo apre ELA** — Chrome for
Testing sulla cartella di ``ELA_BROWSER_PROFILE_DIR``, con gli argomenti del suo adapter, i service
worker tolti prima del lancio e bloccati, e la finestra — su ``https://web.whatsapp.com/``, con quel
solo sito come confine. Poi aspetta te: colleghi il telefono a mano, nella finestra, e apri la chat
con te stesso.

**Che cosa trova, e come.** Per **attributi dichiarati** dagli elementi — ``contenteditable``,
``role``, ``data-tab``, ``data-testid``, ``data-icon``, ``type``, e le classi fatte solo di parole e
trattini —, **mai** per il testo di un elemento, per il suo ``aria-label`` o il suo ``title`` (che
possono portare un nome), né per la sua posizione: la casella del messaggio; l'elemento che invia,
che compare dopo un carattere che **tu** scrivi a mano nella casella e poi cancelli; la bolla di un
messaggio uscito; e se l'indirizzo ``/send?phone=`` con il tuo numero apre quella chat. Ogni
selettore è contato sulla pagina: quanti elementi trova.

**Che cosa non fa.** Non scrive niente nella pagina, non clicca, non preme un tasto, non invia
niente: ogni gesto nella finestra è tuo. Il tuo numero lo chiede qui, senza mostrarlo, lo usa per
comporre un indirizzo, e **non lo scrive da nessuna parte**.

**Il file**, ``~/Downloads/misura-m13.10-<data e ora>.txt``, va in chat: porta **solo selettori,
conti, sì e no** — se la pagina ha retto senza service worker, se ogni selettore trova un elemento
solo. Nessun testo della pagina, nessun nome, nessun numero: ogni riga passa da un filtro
(:func:`withheld`), e alla fine lo script rilegge il file e lo dice.

Le parole dell'esito: **PASSATO** — misurato —; **SALTATO** — il mondo non l'ha dato: un selettore
che non si trova, una risposta «no» —; **FERMATO** — una precondizione non c'è, e la misura non
parte —; **FALLITO** — un dovere dello script non verificato: la chiusura, il file, il filtro.
"""

from __future__ import annotations

import asyncio
import getpass
import re
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

SITE: Final = "web.whatsapp.com"
ORIGIN: Final = f"https://{SITE}"
ADDRESS: Final = f"{ORIGIN}/"
SEND: Final = f"{ORIGIN}/send?phone="

SAFE_ATTRIBUTES: Final = ("data-testid", "data-tab", "data-icon", "role", "contenteditable", "type")
"""Gli attributi da cui un selettore si scrive, nell'ordine in cui si provano: dichiarazioni di chi
ha fatto la pagina, e mai un testo per chi la legge. **Non** ``aria-label``, ``title``, ``alt``,
``placeholder`` né ``data-id``: portano parole, e a volte un nome o un numero."""
SAFE_VALUE: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
"""Il valore di un attributo che entra in un selettore: comincia con una lettera, niente spazi."""
SAFE_CLASS: Final = re.compile(r"^[a-z]+(?:-[a-z]+)+$")
"""Una classe che entra in un selettore: parole minuscole e trattini — ``message-out`` —, mai un
nome generato, che cambia a ogni versione della pagina."""
PHONE: Final = re.compile(r"^\+?[0-9]{6,15}$")
DIGITS: Final = re.compile(r"[0-9]{6,}")
"""Sei cifre di fila in una riga del file: un numero, e la riga non si scrive."""

SCOPES: Final = {"the box": "footer", "the element that sends": "footer", "the bubble": "#main"}
KINDS: Final = {
    "the box": '[contenteditable="true"], textarea, input[type="text"]',
    "the element that sends": 'button, [role="button"], span[data-icon]',
    "the bubble": "div, span",
}

CANDIDATES: Final = """
([scope, kinds, safe]) => {
  const root = document.querySelector(scope);
  if (!root) return null;
  const visible = (el) => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  return [...root.querySelectorAll(kinds)].filter(visible).map((el) => ({
    tag: el.tagName.toLowerCase(),
    attributes: Object.fromEntries(safe.filter((name) => el.hasAttribute(name))
      .map((name) => [name, el.getAttribute(name)])),
    classes: [...el.classList],
  }));
}
"""
"""Ciò che la pagina dice di ogni elemento candidato: il nome del tag, gli attributi della lista e
le classi. **Mai il testo**: questa funzione non legge ``textContent``, ``innerText`` né
``value``."""
EMPTY: Final = """
(selector) => { const el = document.querySelector(selector);
  return el ? (el.textContent.length === 0
    && (el.value === undefined || el.value.length === 0)) : null; }
"""
"""Se la casella è vuota: una lunghezza, mai il contenuto."""


@dataclass(frozen=True)
class Candidate:
    """Un elemento, com'è dichiarato: il tag, gli attributi della lista, le classi."""

    tag: str
    attributes: Mapping[str, str]
    classes: tuple[str, ...]

    def key(self) -> tuple[str, tuple[tuple[str, str], ...], tuple[str, ...]]:
        return (self.tag, tuple(sorted(self.attributes.items())), self.classes)


def candidates_of(found: object) -> list[Candidate]:
    """I candidati come la pagina li ha descritti, tenuti solo nei nomi e nei valori sicuri."""
    if not isinstance(found, list):
        return []
    made: list[Candidate] = []
    for one in found:
        if not isinstance(one, dict):
            continue
        attributes = {
            str(name): str(value)
            for name, value in (one.get("attributes") or {}).items()
            if name in SAFE_ATTRIBUTES and isinstance(value, str) and SAFE_VALUE.match(value)
        }
        classes = tuple(str(c) for c in one.get("classes") or () if SAFE_CLASS.match(str(c)))
        made.append(Candidate(str(one.get("tag", "")), attributes, classes))
    return made


def selectors_of(candidate: Candidate, scope: str) -> list[str]:
    """I selettori che si possono scrivere per ``candidate``: dentro ``scope``, per un attributo o
    una classe alla volta, nell'ordine di :data:`SAFE_ATTRIBUTES`. Nessun testo e nessuna
    posizione."""
    tag = candidate.tag if re.fullmatch(r"[a-z][a-z0-9-]*", candidate.tag) else ""
    written = [
        f'{scope} {tag}[{name}="{candidate.attributes[name]}"]'
        for name in SAFE_ATTRIBUTES
        if name in candidate.attributes
    ]
    written += [f"{scope} {tag}.{one}" for one in candidate.classes]
    return written


def withheld(line: str, secrets: Iterable[str] = ()) -> bool:
    """Se ``line`` non si scrive nel file: porta sei cifre di fila, una chiocciola, o uno dei
    ``secrets`` — il numero, che il file non deve mai avere."""
    if DIGITS.search(line) or "@" in line:
        return True
    return any(secret and secret in line for secret in secrets)


@dataclass
class Report:
    """Il file della misura, scritto riga per riga attraverso il filtro."""

    secrets: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    refused: int = 0

    def say(self, line: str) -> None:
        if withheld(line, self.secrets):
            self.refused += 1
            line = "(una riga non scritta: il filtro l'ha fermata)"
        self.lines.append(line)
        print(line, flush=True)

    def word(self, word: str, what: str) -> None:
        self.say(f"{word} — {what}")


def wait_for_you(ask: Callable[[str], str], what: str) -> None:
    ask(f"\n>>> {what}\n    Quando hai fatto, premi Invio qui. ")


def yes(ask: Callable[[str], str], question: str) -> bool:
    while True:
        said = ask(f"\n>>> {question} [s/n] ").strip().lower()
        if said in {"s", "si", "sì"}:
            return True
        if said == "n":
            return False


async def counted(page: Any, selectors: Sequence[str]) -> list[tuple[str, int]]:
    """Quanti elementi trova ciascun selettore: un conto, e niente altro della pagina."""
    return [(selector, await page.locator(selector).count()) for selector in selectors]


async def described(page: Any, what: str) -> list[Candidate]:
    return candidates_of(
        await page.evaluate(CANDIDATES, [SCOPES[what], KINDS[what], list(SAFE_ATTRIBUTES)])
    )


def unique_selectors(candidates: Iterable[Candidate], scope: str) -> list[str]:
    seen: list[str] = []
    for candidate in candidates:
        for selector in selectors_of(candidate, scope):
            if selector not in seen:
                seen.append(selector)
    return seen


async def measure(report: Report, ask: Callable[[str], str], page: Any) -> None:
    """La misura, sulla pagina aperta: tre selettori e un indirizzo."""
    wait_for_you(
        ask,
        "Nella finestra di Chrome for Testing: collega il telefono a mano\n"
        "    (sul telefono, WhatsApp →\n"
        "    Dispositivi collegati → Collega un dispositivo, e inquadra il codice).\n"
        "    Quando vedi le chat,\n"
        "    apri la chat con te stesso. Non scrivere niente.",
    )
    box_candidates = await described(page, "the box")
    held = bool(box_candidates)
    report.word(
        "PASSATO" if held else "SALTATO",
        "la pagina ha retto senza service worker fino alla casella del messaggio: "
        f"{'sì' if held else 'no'}",
    )
    boxes = [
        (s, n)
        for s, n in await counted(page, unique_selectors(box_candidates, SCOPES["the box"]))
        if n >= 1
    ]
    for selector, number in boxes:
        report.say(
            f"    la casella: {selector} — trova {number} element{'o' if number == 1 else 'i'}"
        )
    box = next((s for s, n in boxes if n == 1), None)
    report.word(
        "PASSATO" if box else "SALTATO",
        f"un selettore della casella che trova un elemento solo: {box or 'nessuno'}",
    )

    before = {c.key() for c in await described(page, "the element that sends")}
    wait_for_you(
        ask,
        "Scrivi A MANO un carattere qualsiasi nella casella del messaggio.\n"
        "    NON premere Invio nella finestra.",
    )
    after = [c for c in await described(page, "the element that sends") if c.key() not in before]
    sends = await counted(page, unique_selectors(after, SCOPES["the element that sends"]))
    for selector, number in sends:
        report.say(
            f"    l'elemento che compare dopo la scrittura: {selector} — trova {number} "
            f"element{'o' if number == 1 else 'i'}"
        )
    send = next((s for s, n in sends if n == 1), None)
    report.word(
        "PASSATO" if send else "SALTATO",
        f"un selettore dell'elemento che invia che trova un elemento solo: {send or 'nessuno'}",
    )
    wait_for_you(
        ask, "Ora CANCELLA quel carattere dalla casella, finché è vuota. Niente è stato inviato."
    )
    if box is not None:
        empty = await page.evaluate(EMPTY, box)
        report.word(
            "PASSATO" if empty else "FALLITO",
            f"la casella è di nuovo vuota: {'sì' if empty else 'no'}",
        )

    if yes(ask, "Nella chat con te stesso c'è almeno un messaggio che hai mandato tu?"):
        bubbles = await described(page, "the bubble")
        outgoing = [
            c for c in bubbles if any("out" in one for one in (*c.classes, *c.attributes.values()))
        ]
        found = [
            (s, n)
            for s, n in await counted(page, unique_selectors(outgoing, SCOPES["the bubble"]))
            if n >= 1
        ]
        for selector, number in found:
            report.say(
                f"    una bolla di un messaggio uscito: {selector} — trova {number} "
                f"element{'o' if number == 1 else 'i'}"
            )
        report.word(
            "PASSATO" if found else "SALTATO",
            "un selettore della bolla di un messaggio uscito (più di un elemento è atteso: "
            "il piano aggiunge il testo del messaggio)"
            if found
            else "nessun selettore della bolla trovato per attributi",
        )
    else:
        report.word("SALTATO", "la bolla di un messaggio uscito: nella chat non ce n'era uno")

    number = getpass.getpass(
        "\n>>> Il tuo numero, con il prefisso del paese, senza spazi "
        "(non si vede mentre lo scrivi): "
    ).strip()
    if not PHONE.match(number):
        report.word("SALTATO", "l'indirizzo /send?phone=: il numero scritto non è un numero")
        return
    digits = number.lstrip("+")
    report.secrets.extend([number, digits])
    await page.goto(SEND + digits, wait_until="load")
    opened = False
    if box is not None:
        until = time.monotonic() + 30
        while time.monotonic() < until and not opened:
            opened = await page.locator(box).count() == 1
            if not opened:
                await asyncio.sleep(0.5)
    del number, digits
    report.word(
        "PASSATO" if opened else "SALTATO",
        "l'indirizzo /send?phone= con il tuo numero apre una chat con la casella: "
        f"{'sì' if opened else 'no'}",
    )
    wait_for_you(ask, "Guarda la finestra: è la chat con te stesso? (Rispondi alla domanda dopo.)")
    report.word(
        "PASSATO" if yes(ask, "Era la chat con te stesso?") else "SALTATO",
        "la chat che l'indirizzo apre è quella con te stesso, a occhio",
    )


async def run(ask: Callable[[str], str] = input) -> int:
    from ela.composition.settings import AccountSettings
    from ela.infrastructure.machine.account import AccountChrome
    from ela.testing.fakes import FakeStop
    from ela.tools.browser import boundary

    report = Report()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path.home() / "Downloads" / f"misura-m13.10-{stamp}.txt"
    report.say(
        "MISURA DI M13.10 — i selettori di WhatsApp Web, per attributi — "
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    folder = AccountSettings().browser_profile_dir
    if folder is None:
        report.word("FERMATO", "ELA_BROWSER_PROFILE_DIR non è dichiarata nel .env")
        return finish(report, out, 2)

    async def never() -> None:
        await asyncio.Event().wait()

    made = AccountChrome(
        asyncio.Event(),
        environment={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(Path.home()),
            "TMPDIR": tempfile.gettempdir(),
            "LANG": "C.UTF-8",
        },
        kept=never,
        system="Darwin",
        profile=folder,
        shown=lambda: True,
    )
    holder = await made.occupied()
    if holder is not None:
        report.word(
            "FERMATO",
            f"il browser con i tuoi account è in uso ({holder}): "
            "ferma ELA o chiudi la finestra, e rilancia",
        )
        return finish(report, out, 2)
    report.word("PASSATO", "il browser con i tuoi account è libero")
    opened = await made.open(ADDRESS, boundary(frozenset({ORIGIN})), FakeStop())
    try:
        await measure(report, ask, made._pages[opened.page].page)
    finally:
        await made.close(opened.page)
        if made._watching is not None:
            made._watching.cancel()
    free = await made.occupied() is None
    report.word(
        "PASSATO" if free else "FALLITO",
        f"il browser è chiuso e la cartella libera: {'sì' if free else 'no'}",
    )
    return finish(report, out, 0 if free else 1)


def finish(report: Report, out: Path, code: int) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report.lines) + "\n", encoding="utf-8")
    again = out.read_text(encoding="utf-8")
    clean = not any(withheld(line, report.secrets) for line in again.splitlines())
    print(
        f"\n{'PASSATO' if clean else 'FALLITO'} — il file, riletto, non porta numeri "
        f"né chiocciole: {out}"
    )
    return code if clean else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
