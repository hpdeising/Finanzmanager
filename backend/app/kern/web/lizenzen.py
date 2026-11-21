# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lizenzhinweise der Python-Pakete, die der Server zur Laufzeit nutzt (Fachkonzept 11.3).

Ausgangspunkt sind die Abhängigkeiten des Pakets ``finanzmanager`` samt angeforderter Extras,
rekursiv; Entwicklungswerkzeuge gehören nicht dazu. Ob die Lizenzen erlaubt sind, prüft
``tests/test_lizenzen.py``; hier werden sie nur angezeigt. Native Bibliotheken in Wheels
(etwa libpq in ``psycopg-binary``) nennt erst ``THIRD-PARTY-LICENSES`` (M9).
"""

import re
from dataclasses import dataclass
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from typing import Final

WURZEL: Final = "finanzmanager"
_ANFORDERUNG = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?")
_EXTRA = re.compile(r"""extra\s*==\s*["']([^"']+)["']""")
_LIZENZDATEI = re.compile(r"(licen[cs]e|copying|notice)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Lizenzhinweis:
    name: str
    version: str
    lizenz: str
    text: str


def _normiert(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _lizenz(dist: Distribution) -> str:
    metadaten = dist.metadata
    if ausdruck := metadaten.get("License-Expression"):
        return str(ausdruck)
    klassen = [
        str(k).split(" :: ")[-1]
        for k in metadaten.get_all("Classifier", [])
        if str(k).startswith("License ::")
    ]
    if klassen:
        return "; ".join(klassen)
    freitext = str(metadaten.get("License") or "").strip()
    return freitext.splitlines()[0] if freitext else "keine Angabe"


def _text(dist: Distribution) -> str:
    texte: list[str] = []
    for datei in dist.files or []:
        if _LIZENZDATEI.search(datei.name) and ".dist-info" in str(datei):
            try:
                texte.append(datei.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return "\n\n".join(texte)


def _abhaengigkeiten(dist: Distribution, extras: set[str]) -> list[tuple[str, set[str]]]:
    gefunden: list[tuple[str, set[str]]] = []
    for anforderung in dist.requires or []:
        teil, _, marker = anforderung.partition(";")
        extra = _EXTRA.search(marker)
        if extra is not None and extra.group(1) not in extras:
            continue
        treffer = _ANFORDERUNG.match(teil)
        if treffer is None:
            continue
        unter = {e.strip() for e in (treffer.group(2) or "").split(",") if e.strip()}
        gefunden.append((treffer.group(1), unter))
    return gefunden


def lizenzhinweise() -> list[Lizenzhinweis]:
    """Laufzeit-Abhängigkeiten des Servers mit Lizenz und Lizenztext, nach Namen sortiert.

    Pakete, deren Bedingung auf dieser Plattform nicht zutrifft, sind nicht installiert und
    fehlen deshalb.
    """
    try:
        wurzel = distribution(WURZEL)
    except PackageNotFoundError:
        return []
    besucht: dict[str, Lizenzhinweis] = {}
    offen = _abhaengigkeiten(wurzel, set())
    while offen:
        name, extras = offen.pop()
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue
        schluessel = _normiert(dist.metadata["Name"])
        neu = schluessel not in besucht
        if neu:
            besucht[schluessel] = Lizenzhinweis(
                name=str(dist.metadata["Name"]),
                version=dist.version,
                lizenz=_lizenz(dist),
                text=_text(dist),
            )
        if neu or extras:
            offen.extend(_abhaengigkeiten(dist, extras))
    return sorted(besucht.values(), key=lambda h: h.name.lower())
