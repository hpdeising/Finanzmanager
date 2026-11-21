# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fristen aus Ereignissen (Fachkonzept Kap. 5.4, Tabelle).

Fristen werden aus Ereignissen abgeleitet und nie gespeichert. Jede Frist führt Norm,
auslösendes Ereignis, Fristende, Art und Warnstufen. Hier stehen die Fristen der Tabelle, deren
Auslöser ein erfasstes Ereignis ist; Verjährung (Kap. 5.5), Auskunfteien und die Aufgabe
„vorzeitige Löschung“ folgen gesondert.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.kern.stammdaten import Feiertagskalender
from app.module.verbindlichkeiten.domain import Ereignis, Ereignistyp
from app.module.verbindlichkeiten.fristen.berechnung import (
    Dauer,
    Einheit,
    Fristart,
    fristende,
    warnstufen,
)

ZWEI_WOCHEN = Dauer(2, Einheit.WOCHEN)


@dataclass(frozen=True, slots=True)
class Frist:
    """Eine Frist mit Norm, Auslöser, Ende, Art und Warnstufen (Kap. 5.4)."""

    name: str
    norm: str
    ausloeser: Ereignis
    ende: date
    art: Fristart
    warnstufen: tuple[date, ...]
    hinweis: str | None = None


@dataclass(frozen=True, slots=True)
class Warnung:
    """Etwas fehlt, ohne das keine Frist berechnet werden kann."""

    ereignis: Ereignis
    text: str


def fristen_aus_ereignissen(
    ereignisse: Iterable[Ereignis], kalender: Feiertagskalender, haushalt_land: str
) -> tuple[list[Frist], list[Warnung]]:
    """Fristen und Warnungen aus den Ereignissen einer Akte, in deren Reihenfolge.

    Feiertage richten sich nach dem Land des Gerichts, bei dem die Handlung vorzunehmen ist; ist
    kein Gericht erfasst, nach dem Land des Haushalts (Kap. 5.4). Fällt ein Fristende auf einen
    Feiertag, der nur in Teilen des Landes gilt, bekommt die Frist einen Hinweis.

    Raises:
        StammdatenFehlenError: wenn der Feiertagskalender für ein Fristende nichts weiß.
    """
    fristen: list[Frist] = []
    warnungen: list[Warnung] = []
    for ereignis in ereignisse:
        if ereignis.datum is None:
            if ereignis.typ.ist_zustellung:
                warnungen.append(
                    Warnung(ereignis, "Zustellungsdatum fehlt: ohne Zustellungsdatum keine Frist.")
                )
            continue
        land = ereignis.gericht_land or haushalt_land
        neu, warnung = _fristen(ereignis, ereignis.datum, kalender, land)
        fristen.extend(neu)
        warnungen.extend(warnung)
    return fristen, warnungen


def _fristen(
    ereignis: Ereignis, tag: date, kalender: Feiertagskalender, land: str
) -> tuple[list[Frist], list[Warnung]]:
    def frist(
        name: str, norm: str, dauer: Dauer, art: Fristart, start: date, hinweis: str | None = None
    ) -> Frist:
        ende = fristende(start, dauer, art, kalender, land)
        if art.verschiebung_222_zpo and (regional := kalender.regionaler_feiertag(ende, land)):
            zusatz = (
                f"Am Gerichtsort kann die Frist einen Tag später enden: {regional} ist in Teilen "
                "des Landes Feiertag."
            )
            hinweis = f"{hinweis} {zusatz}" if hinweis else zusatz
        return Frist(name, norm, ereignis, ende, art, warnstufen(ende, art), hinweis)

    typ = ereignis.typ
    if typ is Ereignistyp.ZUSTELLUNG_MAHNBESCHEID:
        return [
            frist(
                "Widerspruch gegen Mahnbescheid",
                "§ 692 Abs. 1 Nr. 3, § 694 Abs. 1 ZPO",
                ZWEI_WOCHEN,
                Fristart.PROZESSUAL,
                tag,
                "Danach ist der Widerspruch möglich, solange kein Vollstreckungsbescheid "
                "verfügt ist.",
            )
        ], []
    if typ is Ereignistyp.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID:
        return [
            frist(
                "Einspruch gegen Vollstreckungsbescheid",
                "§ 700 Abs. 1, § 339 Abs. 1 ZPO",
                ZWEI_WOCHEN,
                Fristart.NOTFRIST,
                tag,
            )
        ], []
    if typ is Ereignistyp.ZUSTELLUNG_URTEIL and ereignis.versaeumnisurteil:
        return [
            frist(
                "Einspruch gegen Versäumnisurteil",
                "§ 339 Abs. 1 ZPO",
                ZWEI_WOCHEN,
                Fristart.NOTFRIST,
                tag,
            )
        ], []
    if typ is Ereignistyp.ZUSTELLUNG_URTEIL:
        return [
            frist(
                "Berufung",
                "§§ 511, 517 ZPO",
                Dauer(1, Einheit.MONATE),
                Fristart.NOTFRIST,
                tag,
                "Nur bei Beschwer über 600 € oder Zulassung der Berufung.",
            )
        ], []
    if typ is Ereignistyp.EINTRAGUNGSANORDNUNG:
        loeschung = frist(
            "Löschung im Schuldnerverzeichnis",
            "§ 882e Abs. 1 ZPO",
            Dauer(3, Einheit.JAHRE),
            Fristart.INFORMATION,
            tag,
            "Von Amts wegen.",
        )
        if ereignis.bekanntgabe_am is None:
            warnung = Warnung(
                ereignis, "Tag der Bekanntgabe fehlt: ohne ihn keine Frist für den Widerspruch."
            )
            return [loeschung], [warnung]
        widerspruch = frist(
            "Widerspruch gegen Eintragungsanordnung",
            "§ 882d Abs. 1 ZPO",
            ZWEI_WOCHEN,
            Fristart.PROZESSUAL,
            ereignis.bekanntgabe_am,
        )
        return [widerspruch, loeschung], []
    return [], []
