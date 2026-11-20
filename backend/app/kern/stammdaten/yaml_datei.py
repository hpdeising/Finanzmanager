# SPDX-License-Identifier: AGPL-3.0-or-later
"""YAML-Dateien der Stammdaten lesen und ihre Felder prüfen.

Gelesen wird mit ``yaml.safe_load``: nur Grunddatentypen, keine Objekte aus Tags.
"""

from datetime import date, datetime
from pathlib import Path
from typing import cast

import yaml

from app.kern.stammdaten.fehler import StammdatenUngueltigError

# Verzeichnis ``stammdaten/`` im Wurzelverzeichnis des Repositorys.
STAMMDATEN_VERZEICHNIS = Path(__file__).resolve().parents[4] / "stammdaten"


def lies_yaml(pfad: Path) -> object:
    """Datei lesen und als YAML auswerten.

    Raises:
        StammdatenUngueltigError: wenn die Datei fehlt, nicht UTF-8 ist oder kein YAML.
    """
    try:
        text = pfad.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        msg = f"Stammdatendatei {pfad.name} fehlt oder ist nicht als UTF-8 lesbar."
        raise StammdatenUngueltigError(msg) from None
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        msg = f"Stammdatendatei {pfad.name} ist kein gültiges YAML."
        raise StammdatenUngueltigError(msg) from None


def zuordnung(wert: object, ort: str, pflicht: set[str], erlaubt: set[str]) -> dict[str, object]:
    """``wert`` muss eine Zuordnung mit allen Pflichtfeldern und nur erlaubten Feldern sein."""
    if not isinstance(wert, dict):
        msg = f"{ort}: Zuordnung erwartet."
        raise StammdatenUngueltigError(msg)
    felder: dict[str, object] = {}
    for schluessel, inhalt in cast("dict[object, object]", wert).items():
        if not isinstance(schluessel, str):
            msg = f"{ort}: Feldnamen müssen Text sein."
            raise StammdatenUngueltigError(msg)
        felder[schluessel] = inhalt
    fehlend = pflicht - felder.keys()
    if fehlend:
        msg = f"{ort}: Pflichtfeld fehlt: {', '.join(sorted(fehlend))}."
        raise StammdatenUngueltigError(msg)
    unbekannt = felder.keys() - pflicht - erlaubt
    if unbekannt:
        msg = f"{ort}: unbekanntes Feld: {', '.join(sorted(unbekannt))}."
        raise StammdatenUngueltigError(msg)
    return felder


def text(wert: object, ort: str) -> str:
    """Nicht leerer Text."""
    if not isinstance(wert, str) or not wert.strip():
        msg = f"{ort}: nicht leerer Text erwartet."
        raise StammdatenUngueltigError(msg)
    return wert


def datum(wert: object, ort: str) -> date:
    """Datum ohne Uhrzeit, in YAML als ``JJJJ-MM-TT`` ohne Anführungszeichen."""
    if isinstance(wert, datetime) or not isinstance(wert, date):
        msg = f"{ort}: Datum JJJJ-MM-TT ohne Uhrzeit erwartet."
        raise StammdatenUngueltigError(msg)
    return wert


def liste(wert: object, ort: str) -> list[object]:
    """Nicht leere Liste."""
    if not isinstance(wert, list) or not wert:
        msg = f"{ort}: nicht leere Liste erwartet."
        raise StammdatenUngueltigError(msg)
    return list(cast("list[object]", wert))
