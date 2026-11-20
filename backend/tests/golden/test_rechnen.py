# SPDX-License-Identifier: AGPL-3.0-or-later
"""Golden Files durchrechnen und mit den Erwartungswerten vergleichen (Fachkonzept Kap. 12).

Verglichen werden die Erwartung zum Stichtag (mit der Toleranz der Datei), dann der Rechenweg
und die Anrechnung Zeile für Zeile. Ein Fehlschlag nennt die erste abweichende Zeile, gezählt wie
im Editor (Kopfzeile = Zeile 1). Schlägt ein Fall fehl, wird der Code korrigiert, nie die
Erwartung (CLAUDE.md).
"""

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from app.kern.geld import als_text, schneide_ab
from app.kern.stammdaten import lade_basiszinsreihe
from app.module.verbindlichkeiten.berechnung import Abschnitt, Anrechnungszeile, berechne
from tests.golden.faelle import Csv, Fall, alle_faelle, eingaben, lies_fall


@pytest.mark.parametrize("pfad", alle_faelle(), ids=lambda p: p.stem)
def test_erwartung_zum_stichtag(pfad: Path) -> None:
    fall = lies_fall(pfad)
    e = eingaben(fall)
    ergebnis = berechne(e.parameter, e.bestandteile, e.zahlungen, e.stichtag, lade_basiszinsreihe())
    erwartung = cast("dict[str, str]", fall.daten["erwartung"])
    toleranz = Decimal(cast("str", fall.daten["toleranz"]))
    ist = {
        "hauptforderung": ergebnis.hauptforderung,
        "zinsen": ergebnis.zinsen,
        "kosten": ergebnis.kosten,
        "gesamt": ergebnis.gesamt,
    }
    for feld, wert in ist.items():
        soll = Decimal(erwartung[feld])
        assert abs(wert - soll) <= toleranz, (
            f"{fall.id}, erwartung.{feld}: erwartet {erwartung[feld]}, Programm {als_text(wert)}"
        )


@pytest.mark.parametrize("pfad", alle_faelle(), ids=lambda p: p.stem)
def test_rechenweg(pfad: Path) -> None:
    fall = lies_fall(pfad)
    if fall.rechenweg is None:
        assert fall.sorte == "real", "Rechenweg ist bei konstruierten Fällen Pflicht"
        return
    e = eingaben(fall)
    ergebnis = berechne(e.parameter, e.bestandteile, e.zahlungen, e.stichtag, lade_basiszinsreihe())
    _vergleiche(fall, fall.rechenweg, [_zeile_rechenweg(a) for a in ergebnis.abschnitte])


@pytest.mark.parametrize("pfad", alle_faelle(), ids=lambda p: p.stem)
def test_anrechnung(pfad: Path) -> None:
    fall = lies_fall(pfad)
    if fall.anrechnung is None:
        assert fall.sorte == "real" or not fall.daten.get("zahlungen")
        return
    e = eingaben(fall)
    ergebnis = berechne(e.parameter, e.bestandteile, e.zahlungen, e.stichtag, lade_basiszinsreihe())
    _vergleiche(fall, fall.anrechnung, [_zeile_anrechnung(z) for z in ergebnis.anrechnungen])


# --- Vergleich ---------------------------------------------------------------------------------

Vergleich = Callable[[str, object], bool]


def _gleich_text(soll: str, ist: object) -> bool:
    return soll == ist


def _gleich_zahl(soll: str, ist: object) -> bool:
    if ist is None:
        return soll == ""
    return soll != "" and Decimal(soll) == ist


def _gleich_ungerundet(soll: str, ist: object) -> bool:
    """Der exakte Wert des Programms beginnt mit den angegebenen Stellen (Kap. 12)."""
    stellen = len(soll.split(".")[1])
    return isinstance(ist, Decimal) and schneide_ab(ist, stellen) == Decimal(soll)


SPALTEN: dict[str, Vergleich] = {
    "bestandteil": _gleich_text,
    "von": _gleich_text,
    "bis": _gleich_text,
    "grund": _gleich_text,
    "tage": _gleich_zahl,
    "tagesbasis": _gleich_zahl,
    "basis": _gleich_zahl,
    "basiszins": _gleich_zahl,
    "satz": _gleich_zahl,
    "zins_ungerundet": _gleich_ungerundet,
    "zins_gerundet": _gleich_zahl,
    "zahlung": _gleich_text,
    "betrag": _gleich_zahl,
    "gruppe": _gleich_text,
    "angerechnet": _gleich_zahl,
    "offen_danach": _gleich_zahl,
}


def _zeile_rechenweg(a: Abschnitt) -> dict[str, object]:
    return {
        "bestandteil": a.bestandteil,
        "von": a.von.isoformat(),
        "bis": a.bis.isoformat(),
        "grund": "+".join(g.value for g in a.gruende),
        "tage": a.tage,
        "tagesbasis": a.tagesbasis,
        "basis": a.basis,
        "basiszins": a.basiszins,
        "satz": a.satz,
        "zins_ungerundet": a.zins_exakt,
        "zins_gerundet": a.zins,
    }


def _zeile_anrechnung(z: Anrechnungszeile) -> dict[str, object]:
    return {
        "zahlung": z.zahlung.datum.isoformat(),
        "betrag": z.zahlung.betrag,
        "bestandteil": z.bestandteil or "",
        "gruppe": z.gruppe.value if z.gruppe is not None else "ueberzahlung",
        "angerechnet": z.angerechnet,
        "offen_danach": z.offen_danach,
    }


def _vergleiche(fall: Fall, datei: Csv, ist: list[dict[str, object]]) -> None:
    """Zeile für Zeile; bei realen Fällen bleiben leere Werte ungeprüft (Kap. 12)."""
    for index, (soll_zeile, ist_zeile) in enumerate(zip(datei.zeilen, ist, strict=False)):
        nummer = index + 2
        for spalte, soll in soll_zeile.items():
            if fall.sorte == "real" and soll == "":
                continue
            wert = ist_zeile[spalte]
            assert SPALTEN[spalte](soll, wert), (
                f"{datei.name}, Zeile {nummer}, Spalte {spalte}: erwartet {soll!r}, "
                f"Programm {_anzeige(wert)!r}"
            )
    assert len(ist) == len(datei.zeilen), (
        f"{datei.name}, Zeile {min(len(ist), len(datei.zeilen)) + 2}: erwartet "
        f"{len(datei.zeilen)} Datenzeilen, Programm {len(ist)}"
    )


def _anzeige(wert: object) -> str:
    if isinstance(wert, Decimal):
        return format(wert, "f")
    return "" if wert is None else str(wert)
