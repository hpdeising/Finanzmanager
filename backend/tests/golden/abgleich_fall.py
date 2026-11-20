# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aufstellung eines realen Golden Files für den Abgleich (Fachkonzept Kap. 5.3 und 12).

Die Aufstellung des Gläubigers steckt im Golden File: Erwartung, Rechenweg und Anrechnung
stammen aus ihr, bis auf die Werte im Block ``abweichungen``, an deren Ort der nachgerechnete
Wert steht. Setzt man dort ``laut_aufstellung`` ein, erhält man die Aufstellung zurück. Der
Abgleich muss dann genau die Orte des Blocks melden.

Positionen des Abgleichs und ``ort``:

- Summe ``s``: ``feld: erwartung.s``
- Rechenweg, Datenzeile ``n``, Spalte ``s``: ``datei: <id>.rechenweg.csv``, ``zeile: n + 1``,
  ``spalte: s`` (Anrechnung entsprechend mit ``<id>.anrechnung.csv``)
- Kostenposition des Bestandteils an Stelle ``k`` der YAML-Datei: ``feld: bestandteile.k.betrag``
"""

from datetime import date
from typing import cast

from app.module.verbindlichkeiten.abgleich import (
    SUMMEN,
    Abgleich,
    Aufstellung,
    Bereich,
    Kostenposition,
    Position,
)
from tests.golden.faelle import Csv, Fall, Ort, abweichungen


def aufstellung(fall: Fall) -> Aufstellung:
    """Die Aufstellung des Gläubigers, wie sie der Fall beschreibt."""
    laut = abweichungen(fall)
    erwartung = cast("dict[str, object]", fall.daten["erwartung"])
    summen = {s: laut.get(("feld", f"erwartung.{s}"), str(erwartung[s])) for s in SUMMEN}

    def zeilen(datei: Csv | None) -> tuple[dict[str, str], ...]:
        if datei is None:
            return ()
        return tuple(
            {s: laut.get(("datei", datei.name, nummer, s), w) for s, w in zeile.items()}
            for nummer, zeile in enumerate(datei.zeilen, 2)
        )

    bestandteile = cast("list[dict[str, object]]", fall.daten["bestandteile"])
    kosten = tuple(
        Kostenposition(
            kennung,
            laut.get(("feld", f"bestandteile.{stelle}.betrag"), str(roh["betrag"])),
        )
        for stelle, (kennung, roh) in enumerate(zip(fall.kennungen, bestandteile, strict=True), 1)
        if str(roh["art"]).startswith("kosten_")
    )
    return Aufstellung(
        stichtag=cast("date", erwartung["stichtag"]),
        summen=summen,
        rechenweg=zeilen(fall.rechenweg),
        anrechnung=zeilen(fall.anrechnung),
        kosten=kosten,
    )


def ort(fall: Fall, aufstellung: Aufstellung, position: Position) -> Ort:
    """Der ``ort`` im Block ``abweichungen`` zu einer Position des Abgleichs."""
    if position.bereich is Bereich.SUMME:
        return ("feld", f"erwartung.{position.spalte}")
    nummer = position.nummer or 0
    if position.bereich is Bereich.KOSTEN:
        kennung = aufstellung.kosten[nummer - 1].kennung
        return ("feld", f"bestandteile.{fall.kennungen.index(str(kennung)) + 1}.betrag")
    datei = "rechenweg" if position.bereich is Bereich.RECHENWEG else "anrechnung"
    return ("datei", f"{fall.id}.{datei}.csv", nummer + 1, position.spalte)


def gemeldet(fall: Fall, aufstellung: Aufstellung, ergebnis: Abgleich) -> dict[Ort, str | None]:
    """Orte und Werte laut Aufstellung, die der Abgleich meldet."""
    return {ort(fall, aufstellung, a.position): a.laut_aufstellung for a in ergebnis.abweichungen}
