# SPDX-License-Identifier: AGPL-3.0-or-later
"""Abgleich einer Forderungsaufstellung mit der Berechnung (Fachkonzept Kap. 5.3).

Verglichen wird Position für Position: die Summen zum Stichtag, die Zeilen von Rechenweg und
Anrechnung in ihrer Reihenfolge (Zeile n der Aufstellung mit Zeile n des Programms) und die
Kosten je Position mit dem Betrag des erfassten Bestandteils. Was die Aufstellung nicht nennt,
wird nicht verglichen.

Mögliche Ursachen einer Abweichung:

- Zinssatz: Basiszinssatz oder Satz der Zeile weichen ab.
- Teilung der Abschnitte: Beginn, Ende oder Grund einer Zeile weichen ab, oder die Zahl der
  Zeilen; außerdem, wenn die andere Wahl für ``teilung`` den Wert der Aufstellung ergibt.
- Tageszählung, Zinsbeginn, Zahltag, Anrechnungsreihenfolge: wenn eine andere Wahl für
  ``tageszaehlung``, ``zinsbeginn``, ``zahltag`` oder die Reihenfolge der Gruppen den Wert der
  Aufstellung an dieser Position ergibt.
- Unbekannte Kosten: eine Kostenposition ohne erfassten Bestandteil; dann auch für Kosten und
  Gesamtbetrag.
- Fehlende Zahlungen: Die Zahlungen der Aufstellung (Wertstellung und Betrag) sind andere als die
  erfassten; dann für alle Positionen außer den Kosten.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from itertools import permutations

from app.kern.geld import als_text, schneide_ab
from app.kern.stammdaten import Basiszinsreihe, StammdatenError
from app.module.verbindlichkeiten.abgleich.aufstellung import (
    Abgleich,
    Abweichung,
    Aufstellung,
    Bereich,
    Position,
    Ursache,
)
from app.module.verbindlichkeiten.berechnung import Abschnitt, Anrechnungszeile, Ergebnis, berechne
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Anrechnungsregel,
    Bestandteil,
    EingabeUngueltigError,
    Gruppe,
    Tageszaehlung,
    Teilung,
    Zahltag,
    Zahlung,
    Zinsbeginn,
)

_TEXT = {"bestandteil", "von", "bis", "grund", "zahlung", "gruppe"}
_SATZ = {"basiszins", "satz"}
_GANZ = {"tage", "tagesbasis"}
_UNGERUNDET = "zins_ungerundet"
_STELLEN_ANZEIGE = 6

Zeile = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _Werte:
    """Die Werte des Programms in der Form der Aufstellung."""

    summen: Mapping[str, object]
    rechenweg: Sequence[Zeile]
    anrechnung: Sequence[Zeile]
    kosten: Mapping[str, Decimal]

    def wert(self, position: Position) -> object | None:
        if position.bereich is Bereich.SUMME:
            return self.summen.get(position.spalte)
        zeilen = self.rechenweg if position.bereich is Bereich.RECHENWEG else self.anrechnung
        if position.nummer is None or position.nummer > len(zeilen):
            return None
        return zeilen[position.nummer - 1].get(position.spalte)

    def zeilen(self, bereich: Bereich) -> int:
        return len(self.rechenweg if bereich is Bereich.RECHENWEG else self.anrechnung)


def gleiche_ab(
    parameter: Aktenparameter,
    bestandteile: Sequence[Bestandteil],
    zahlungen: Sequence[Zahlung],
    aufstellung: Aufstellung,
    reihe: Basiszinsreihe,
) -> Abgleich:
    """Aufstellung des Gläubigers mit der Berechnung zu ihrem Stichtag vergleichen (Kap. 5.3).

    Raises:
        EingabeUngueltigError: wenn ein Wert der Aufstellung nicht die Form aus Kap. 12 hat.
        StammdatenFehlenError: wie ``berechne``.
    """
    werte = _werte(parameter, bestandteile, zahlungen, aufstellung.stichtag, reihe)
    gefunden = list(_vergleiche(aufstellung, werte))
    varianten = list(_varianten(parameter, bestandteile, zahlungen, aufstellung.stichtag, reihe))
    andere_zahlungen = _andere_zahlungen(aufstellung, zahlungen)
    unbekannte_kosten = any(
        a.position.bereich is Bereich.KOSTEN and programm is None for a, programm in gefunden
    )
    abweichungen: list[Abweichung] = []
    for roh, _ in gefunden:
        ursachen = set(_direkte_ursachen(roh.position, roh.laut_aufstellung, roh.programm))
        if unbekannte_kosten and roh.position in {
            Position(Bereich.SUMME, "kosten"),
            Position(Bereich.SUMME, "gesamt"),
        }:
            ursachen.add(Ursache.UNBEKANNTE_KOSTEN)
        if andere_zahlungen and roh.position.bereich is not Bereich.KOSTEN:
            ursachen.add(Ursache.FEHLENDE_ZAHLUNGEN)
        if roh.position.bereich is not Bereich.KOSTEN:
            for ursache, variante in varianten:
                if _stimmt(roh.position, roh.laut_aufstellung, variante):
                    ursachen.add(ursache)
        abweichungen.append(replace(roh, ursachen=frozenset(ursachen)))
    return Abgleich(tuple(abweichungen))


# --- Werte des Programms -----------------------------------------------------------------------


def _werte(
    parameter: Aktenparameter,
    bestandteile: Sequence[Bestandteil],
    zahlungen: Sequence[Zahlung],
    stichtag: date,
    reihe: Basiszinsreihe,
) -> _Werte:
    ergebnis = berechne(parameter, bestandteile, zahlungen, stichtag, reihe)
    return _darstellung(ergebnis, bestandteile, stichtag)


def _darstellung(ergebnis: Ergebnis, bestandteile: Sequence[Bestandteil], stichtag: date) -> _Werte:
    return _Werte(
        summen={
            "hauptforderung": ergebnis.hauptforderung,
            "zinsen": ergebnis.zinsen,
            "kosten": ergebnis.kosten,
            "gesamt": ergebnis.gesamt,
        },
        rechenweg=[_zeile_rechenweg(a) for a in ergebnis.abschnitte],
        anrechnung=[_zeile_anrechnung(z) for z in ergebnis.anrechnungen],
        kosten={
            b.kennung: b.betrag
            for b in bestandteile
            if b.art.gruppe is Gruppe.KOSTEN
            and (b.entstanden_am is None or b.entstanden_am <= stichtag)
        },
    )


def _zeile_rechenweg(a: Abschnitt) -> Zeile:
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


def _zeile_anrechnung(z: Anrechnungszeile) -> Zeile:
    return {
        "zahlung": z.zahlung.datum.isoformat(),
        "betrag": z.zahlung.betrag,
        "bestandteil": z.bestandteil or "",
        "gruppe": z.gruppe.value if z.gruppe is not None else "ueberzahlung",
        "angerechnet": z.angerechnet,
        "offen_danach": z.offen_danach,
    }


# --- Vergleich ---------------------------------------------------------------------------------


def _vergleiche(aufstellung: Aufstellung, werte: _Werte) -> Iterator[tuple[Abweichung, object]]:
    """Abweichungen ohne Ursachen, mit dem Wert des Programms."""
    leer: frozenset[Ursache] = frozenset()
    for spalte, laut in aufstellung.summen.items():
        position = Position(Bereich.SUMME, spalte)
        yield from _abweichung(position, laut, werte.wert(position), leer)
    for bereich, zeilen in (
        (Bereich.RECHENWEG, aufstellung.rechenweg),
        (Bereich.ANRECHNUNG, aufstellung.anrechnung),
    ):
        for nummer, zeile in enumerate(zeilen, 1):
            for spalte, laut in zeile.items():
                position = Position(bereich, spalte, nummer)
                yield from _abweichung(position, laut, werte.wert(position), leer)
        if zeilen:
            erste_spalte = "von" if bereich is Bereich.RECHENWEG else "zahlung"
            for nummer in range(len(zeilen) + 1, werte.zeilen(bereich) + 1):
                position = Position(bereich, erste_spalte, nummer)
                programm = werte.wert(position)
                yield (
                    Abweichung(position, None, _anzeige(position.spalte, programm), leer),
                    programm,
                )
    for nummer, kosten in enumerate(aufstellung.kosten, 1):
        position = Position(Bereich.KOSTEN, "betrag", nummer)
        programm = werte.kosten.get(kosten.kennung) if kosten.kennung else None
        yield from _abweichung(position, kosten.betrag, programm, leer)


def _abweichung(
    position: Position, laut: str, programm: object | None, ursachen: frozenset[Ursache]
) -> Iterator[tuple[Abweichung, object]]:
    if laut == "" or _gleich(position.spalte, laut, programm):
        return
    yield Abweichung(position, laut, _anzeige(position.spalte, programm), ursachen), programm


def _gleich(spalte: str, laut: str, programm: object | None) -> bool:
    """Wie der Golden-Test (Kap. 12): Text gleich, Zahlen gleich, ungerundeter Zins mit gleichem
    Anfang."""
    if programm is None:
        return False
    if spalte in _TEXT:
        return laut == programm
    zahl = _zahl(spalte, laut)
    if spalte == _UNGERUNDET:
        stellen = len(laut.split(".")[1]) if "." in laut else 0
        return isinstance(programm, Decimal) and schneide_ab(programm, stellen) == zahl
    return isinstance(programm, Decimal | int) and zahl == programm


def _zahl(spalte: str, laut: str) -> Decimal:
    try:
        zahl = Decimal(laut)
    except InvalidOperation:
        msg = f"Wert der Aufstellung in Spalte {spalte} ist keine Zahl."
        raise EingabeUngueltigError(msg) from None
    if not zahl.is_finite():
        msg = f"Wert der Aufstellung in Spalte {spalte} ist keine endliche Zahl."
        raise EingabeUngueltigError(msg)
    return zahl


def _anzeige(spalte: str, wert: object | None) -> str | None:
    if wert is None:
        return None
    if isinstance(wert, Decimal):
        if spalte == _UNGERUNDET:
            return format(schneide_ab(wert, _STELLEN_ANZEIGE), "f")
        if spalte in _SATZ:
            return format(wert, "f")
        return als_text(wert)
    return str(wert)


# --- Ursachen ----------------------------------------------------------------------------------


def _direkte_ursachen(position: Position, laut: str | None, programm: str | None) -> set[Ursache]:
    if position.bereich is Bereich.KOSTEN:
        return {Ursache.UNBEKANNTE_KOSTEN} if programm is None else set()
    if position.bereich is not Bereich.RECHENWEG:
        return set()
    if position.spalte in _SATZ:
        return {Ursache.ZINSSATZ}
    if position.spalte in {"von", "bis", "grund"} or laut is None or programm is None:
        return {Ursache.TEILUNG}
    return set()


def _varianten(
    parameter: Aktenparameter,
    bestandteile: Sequence[Bestandteil],
    zahlungen: Sequence[Zahlung],
    stichtag: date,
    reihe: Basiszinsreihe,
) -> Iterator[tuple[Ursache, _Werte]]:
    """Berechnungen mit genau einem anderen Aktenparameter."""
    andere: list[tuple[Ursache, Aktenparameter]] = []
    for zaehlung in Tageszaehlung:
        if zaehlung is not parameter.tageszaehlung:
            andere.append((Ursache.TAGESZAEHLUNG, replace(parameter, tageszaehlung=zaehlung)))
    for zinsbeginn in Zinsbeginn:
        if zinsbeginn is not parameter.zinsbeginn:
            andere.append((Ursache.ZINSBEGINN, replace(parameter, zinsbeginn=zinsbeginn)))
    for zahltag in Zahltag:
        if zahltag is not parameter.zahltag:
            andere.append((Ursache.ZAHLTAG, replace(parameter, zahltag=zahltag)))
    for teilung in Teilung:
        if teilung is not parameter.teilung:
            andere.append((Ursache.TEILUNG, replace(parameter, teilung=teilung)))
    for folge in permutations(Gruppe):
        if folge != parameter.gruppenfolge:
            andere.append(
                (
                    Ursache.ANRECHNUNGSREIHENFOLGE,
                    replace(parameter, anrechnung=Anrechnungsregel.INDIVIDUELL, reihenfolge=folge),
                )
            )
    for ursache, variante in andere:
        try:
            yield ursache, _werte(variante, bestandteile, zahlungen, stichtag, reihe)
        except (StammdatenError, EingabeUngueltigError):
            continue


def _stimmt(position: Position, laut: str | None, variante: _Werte) -> bool:
    """Ergibt die Variante an dieser Position den Wert der Aufstellung?"""
    if laut is None:
        return variante.zeilen(position.bereich) < (position.nummer or 0)
    return _gleich(position.spalte, laut, variante.wert(position))


def _andere_zahlungen(aufstellung: Aufstellung, zahlungen: Sequence[Zahlung]) -> bool:
    """Nennt die Aufstellung andere Zahlungen als die erfassten bis zum Stichtag?"""
    genannt: set[tuple[str, Decimal]] = set()
    for zeile in aufstellung.anrechnung:
        tag, betrag = zeile.get("zahlung", ""), zeile.get("betrag", "")
        if tag and betrag:
            genannt.add((tag, _zahl("betrag", betrag)))
    if not genannt:
        return False
    erfasst = {
        (z.datum.isoformat(), z.betrag) for z in zahlungen if z.datum <= aufstellung.stichtag
    }
    return genannt != erfasst
