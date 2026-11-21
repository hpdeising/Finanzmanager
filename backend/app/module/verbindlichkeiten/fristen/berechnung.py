# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fristende und Warnstufen (Fachkonzept Kap. 5.4).

Berechnet wird nach §§ 187, 188 BGB für Fristen, die mit einem Ereignis beginnen (etwa einer
Zustellung). Bei prozessualen Fristen gilt zusätzlich § 222 Abs. 2 ZPO.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from app.kern.stammdaten import Feiertagskalender

EIN_TAG = timedelta(days=1)
SAMSTAG = 5


class Einheit(StrEnum):
    TAGE = "tage"
    WOCHEN = "wochen"
    MONATE = "monate"
    JAHRE = "jahre"


@dataclass(frozen=True, slots=True)
class Dauer:
    """Dauer einer Frist, etwa 2 Wochen."""

    anzahl: int
    einheit: Einheit

    def __post_init__(self) -> None:
        if self.anzahl < 1:
            msg = "Eine Frist dauert mindestens eine Einheit."
            raise ValueError(msg)


class Fristart(StrEnum):
    """Art einer Frist (Kap. 5.4)."""

    NOTFRIST = "notfrist"
    PROZESSUAL = "prozessual"
    MATERIELL = "materiell"
    INFORMATION = "information"
    AUFGABE = "aufgabe"

    @property
    def verschiebung_222_zpo(self) -> bool:
        """§ 222 Abs. 2 ZPO gilt für prozessuale Fristen, auch für Notfristen (Kap. 5.4)."""
        return self in {Fristart.PROZESSUAL, Fristart.NOTFRIST}

    @property
    def warntage(self) -> tuple[int, ...]:
        """Tage vor Ablauf, an denen gewarnt wird (Kap. 5.4)."""
        return _WARNTAGE[self]


_WARNTAGE: dict[Fristart, tuple[int, ...]] = {
    Fristart.NOTFRIST: (7, 3, 1),
    Fristart.PROZESSUAL: (7, 3),
    Fristart.INFORMATION: (30,),
    Fristart.MATERIELL: (),
    Fristart.AUFGABE: (),
}


def fristende(
    ereignistag: date,
    dauer: Dauer,
    art: Fristart,
    kalender: Feiertagskalender | None = None,
    land: str | None = None,
) -> date:
    """Letzter Tag einer Frist, die mit dem Ereignis am ``ereignistag`` beginnt.

    - § 187 Abs. 1 BGB: Der Tag des Ereignisses wird nicht mitgerechnet.
    - § 188 Abs. 1 BGB: Eine Frist nach Tagen endet mit dem Ablauf ihres letzten Tages.
    - § 188 Abs. 2 BGB: Eine Frist nach Wochen, Monaten oder Jahren endet mit dem Ablauf des
      Tages, der durch seine Benennung oder Zahl dem Tag des Ereignisses entspricht.
    - § 188 Abs. 3 BGB: Fehlt dieser Tag im letzten Monat, endet sie mit dem letzten Tag dieses
      Monats.
    - § 222 Abs. 2 ZPO, bei prozessualen Fristen einschließlich Notfristen: Fällt das Ende auf
      einen Samstag, Sonntag oder allgemeinen Feiertag, endet die Frist mit Ablauf des nächsten
      Werktags. Feiertage nach ``land`` aus dem ``kalender``, nur landesweite (Kap. 5.4, E-36).

    Raises:
        ValueError: wenn § 222 Abs. 2 ZPO gilt, aber Kalender oder Land fehlen.
        StammdatenFehlenError: wenn der Kalender für einen nötigen Tag nichts weiß.
    """
    ende = _ende_188_bgb(ereignistag, dauer)
    if not art.verschiebung_222_zpo:
        return ende
    if kalender is None or land is None:
        msg = "Für § 222 Abs. 2 ZPO braucht es Feiertagskalender und Land."
        raise ValueError(msg)
    while ende.weekday() >= SAMSTAG or kalender.ist_feiertag(ende, land):
        ende += EIN_TAG
    return ende


def warnstufen(ende: date, art: Fristart) -> tuple[date, ...]:
    """Tage, an denen vor dem Ablauf gewarnt wird, aufsteigend (Kap. 5.4)."""
    return tuple(ende - timedelta(days=tage) for tage in art.warntage)


def _ende_188_bgb(ereignistag: date, dauer: Dauer) -> date:
    if dauer.einheit is Einheit.TAGE:
        return ereignistag + timedelta(days=dauer.anzahl)
    if dauer.einheit is Einheit.WOCHEN:
        return ereignistag + timedelta(weeks=dauer.anzahl)
    monate = dauer.anzahl * (12 if dauer.einheit is Einheit.JAHRE else 1)
    jahr, monat = divmod(ereignistag.month - 1 + monate, 12)
    jahr += ereignistag.year
    monat += 1
    letzter = calendar.monthrange(jahr, monat)[1]
    return date(jahr, monat, min(ereignistag.day, letzter))
