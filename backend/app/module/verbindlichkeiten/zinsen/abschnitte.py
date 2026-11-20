# SPDX-License-Identifier: AGPL-3.0-or-later
"""Zinsläufe und Abschnitte eines Bestandteils (Fachkonzept Kap. 5.2 Schritte 1 und 2).

Die Abschnitte hängen nur von Daten ab, nicht von Beträgen: Zinsregeln, Aktenparameter,
Teilungstage, die Grenzen der Zahlungen und der Stichtag. Die Beträge rechnet ``berechnung``.
"""

from collections.abc import Set
from dataclasses import dataclass
from datetime import date, timedelta

from app.kern.stammdaten import Basiszinsreihe
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Bestandteil,
    Grund,
    Tageszaehlung,
    Teilung,
    Zinsbeginn,
    Zinsregel,
)

EIN_TAG = timedelta(days=1)
HALBJAHRESBEGINN = ((1, 1), (7, 1))
_REIHENFOLGE = list(Grund)


@dataclass(frozen=True, slots=True)
class Abschnittsrahmen:
    """Ein Abschnitt ohne Beträge: Tage, Gründe, Zinsregel.

    ``vortag_verzinst`` ist falsch für den ersten Abschnitt jedes Zinslaufs; davon hängt die
    Zählung bei ``30_360`` ab (E-34).
    """

    von: date
    bis: date
    gruende: tuple[Grund, ...]
    regel: Zinsregel
    vortag_verzinst: bool


@dataclass(frozen=True, slots=True)
class _Lauf:
    """Zusammenhängend verzinste Tage unter einer Zinsregel."""

    von: date
    bis: date
    regel: Zinsregel
    neuer_zinslauf: bool


def abschnittsrahmen(
    bestandteil: Bestandteil,
    parameter: Aktenparameter,
    zahlungsgrenzen: Set[date],
    stichtag: date,
    reihe: Basiszinsreihe,
) -> list[Abschnittsrahmen]:
    """Abschnitte eines Bestandteils bis zum Stichtag, nach ``von`` geordnet.

    ``zahlungsgrenzen`` sind die ersten Tage, an denen eine Zahlung die Zinsbasis mindert
    (E-30): bei ``alter_betrag`` der Tag nach der Wertstellung, sonst die Wertstellung.

    Ein neuer Abschnitt beginnt (Kap. 5.2 Schritt 2):

    - bei basiszinsabhängigen Regeln an jedem 01.01. und 01.07. (§ 247 Abs. 1 BGB), bei
      ``teilung = satzwechsel`` nur, wenn sich der Basiszinssatz dort ändert (E-32);
    - bei ``act_act`` an jedem 01.01. (E-31);
    - an jedem Teilungstag (E-32), an jeder Zahlungsgrenze (E-30) und bei jedem Regelwechsel.

    Der erste Abschnitt jedes Zinslaufs hat allein den Grund ``zinsbeginn``.
    """
    rahmen: list[Abschnittsrahmen] = []
    vorige: Zinsregel | None = None
    for lauf in _laeufe(bestandteil, parameter.zinsbeginn, stichtag):
        if lauf.neuer_zinslauf:
            start: tuple[Grund, ...] = (Grund.ZINSBEGINN,)
        else:
            vorher = vorige or lauf.regel
            start = (
                *_gruende(lauf.von, lauf.regel, vorher, parameter, zahlungsgrenzen, reihe),
                Grund.REGELWECHSEL,
            )
        beginne: list[tuple[date, tuple[Grund, ...]]] = [(lauf.von, start)]
        for tag in sorted(_kandidaten(lauf, parameter, zahlungsgrenzen)):
            gruende = _gruende(tag, lauf.regel, lauf.regel, parameter, zahlungsgrenzen, reihe)
            if gruende:
                beginne.append((tag, gruende))
        for nummer, (von, gruende) in enumerate(beginne):
            bis = beginne[nummer + 1][0] - EIN_TAG if nummer + 1 < len(beginne) else lauf.bis
            vortag_verzinst = nummer > 0 or not lauf.neuer_zinslauf
            rahmen.append(Abschnittsrahmen(von, bis, gruende, lauf.regel, vortag_verzinst))
        vorige = lauf.regel
    return rahmen


def _laeufe(bestandteil: Bestandteil, zinsbeginn: Zinsbeginn, stichtag: date) -> list[_Lauf]:
    """Verzinste Tage je Zinsregel bis zum Stichtag (Kap. 5.2 Schritt 1, E-24).

    Eine Regel gilt ab ``ab`` bis ``bis``, ohne ``bis`` bis zum Tag vor der nächsten Regel.
    Folgt sie ohne unverzinsten Tag auf eine verzinsliche, setzt sie deren Zinslauf fort, und
    ``zinsbeginn`` wirkt nicht. Sonst beginnt ein neuer Zinslauf, bei ``folgetag`` am Tag nach
    ``ab``.
    """
    laeufe: list[_Lauf] = []
    letzter_verzinster: date | None = None
    regeln = bestandteil.zinsregeln
    for index, regel in enumerate(regeln):
        if not regel.typ.verzinslich or regel.ab is None:
            continue
        ende = regel.bis
        if index + 1 < len(regeln):
            naechste = regeln[index + 1].ab
            if naechste is not None:
                ende = naechste - EIN_TAG if ende is None else min(ende, naechste - EIN_TAG)
        ende = stichtag if ende is None else min(ende, stichtag)
        fortsetzung = letzter_verzinster == regel.ab - EIN_TAG
        beginn = regel.ab
        if not fortsetzung and zinsbeginn is Zinsbeginn.FOLGETAG:
            beginn += EIN_TAG
        if beginn > ende:
            continue
        laeufe.append(_Lauf(beginn, ende, regel, neuer_zinslauf=not fortsetzung))
        letzter_verzinster = ende
    return laeufe


def _kandidaten(lauf: _Lauf, parameter: Aktenparameter, zahlungsgrenzen: Set[date]) -> set[date]:
    """Tage nach dem ersten Tag des Laufs, an denen ein Abschnitt beginnen kann."""
    tage = {t for t in parameter.teilungstage | zahlungsgrenzen if lauf.von < t <= lauf.bis}
    for jahr in range(lauf.von.year, lauf.bis.year + 1):
        for monat, tag in HALBJAHRESBEGINN:
            kandidat = date(jahr, monat, tag)
            if lauf.von < kandidat <= lauf.bis:
                tage.add(kandidat)
    return tage


def _gruende(
    tag: date,
    regel: Zinsregel,
    vorige: Zinsregel,
    parameter: Aktenparameter,
    zahlungsgrenzen: Set[date],
    reihe: Basiszinsreihe,
) -> tuple[Grund, ...]:
    """Gründe für einen Abschnittsbeginn am ``tag`` außer zinsbeginn und regelwechsel."""
    gruende: set[Grund] = set()
    if _halbjahr(tag, regel, vorige, parameter.teilung, reihe):
        gruende.add(Grund.HALBJAHR)
    if parameter.tageszaehlung is Tageszaehlung.ACT_ACT and (tag.month, tag.day) == (1, 1):
        gruende.add(Grund.JAHRESWECHSEL)
    if tag in parameter.teilungstage:
        gruende.add(Grund.TEILUNGSTAG)
    if tag in zahlungsgrenzen:
        gruende.add(Grund.ZAHLUNG)
    return tuple(sorted(gruende, key=_REIHENFOLGE.index))


def _halbjahr(
    tag: date, regel: Zinsregel, vorige: Zinsregel, teilung: Teilung, reihe: Basiszinsreihe
) -> bool:
    """Teilung am 01.01. oder 01.07. bei basiszinsabhängiger Regel (§ 247 Abs. 1 BGB, E-32).

    Bei ``satzwechsel`` nur, wenn sich der Basiszinssatz an diesem Tag ändert und auch die
    Regel davor basiszinsabhängig war.
    """
    if (tag.month, tag.day) not in HALBJAHRESBEGINN or not regel.typ.basiszinsabhaengig:
        return False
    if teilung is Teilung.KALENDER:
        return True
    return vorige.typ.basiszinsabhaengig and reihe.satz_am(tag) != reihe.satz_am(tag - EIN_TAG)
