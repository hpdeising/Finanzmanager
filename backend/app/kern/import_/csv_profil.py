# SPDX-License-Identifier: AGPL-3.0-or-later
"""CSV-Import mit Profilen je Bank (Fachkonzept Kap. 8).

Ein Profil beschreibt Trennzeichen, Kodierung, Datumsformat, Schreibweise der Beträge und
welche Spalte was enthält. Negative Beträge sind Belastungen, positive Gutschriften.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.kern.geld import betrag as kanonischer_betrag
from app.kern.import_.umsatz import ImportUngueltigError, Richtung, Umsatz, iban_normiert


@dataclass(frozen=True, slots=True)
class CsvProfil:
    """Spalten werden über ihre Überschrift angesprochen. Mehrere Spalten für den
    Verwendungszweck werden mit Leerzeichen verbunden."""

    name: str
    spalte_buchungstag: str
    spalte_betrag: str
    spalten_verwendungszweck: tuple[str, ...]
    spalte_valuta: str | None = None
    spalte_gegen_name: str | None = None
    spalte_gegen_iban: str | None = None
    trennzeichen: str = ";"
    kodierung: str = "utf-8"
    datumsformat: str = "%d.%m.%Y"
    dezimaltrennzeichen: str = ","
    tausendertrennzeichen: str | None = "."
    kopfzeilen_ueberspringen: int = 0

    def __post_init__(self) -> None:
        if not self.spalten_verwendungszweck:
            msg = "Ein Profil braucht mindestens eine Spalte für den Verwendungszweck."
            raise ValueError(msg)
        if self.dezimaltrennzeichen == self.tausendertrennzeichen:
            msg = "Dezimal- und Tausendertrennzeichen müssen sich unterscheiden."
            raise ValueError(msg)

    @property
    def spalten(self) -> tuple[str, ...]:
        """Alle Spalten, die das Profil nennt; jede muss in der Datei vorkommen."""
        pflicht = (self.spalte_buchungstag, self.spalte_betrag, *self.spalten_verwendungszweck)
        optional = (self.spalte_valuta, self.spalte_gegen_name, self.spalte_gegen_iban)
        return pflicht + tuple(s for s in optional if s)


def lies_csv(daten: bytes, profil: CsvProfil) -> list[Umsatz]:
    """Umsätze einer CSV-Datei nach ``profil``; leere Zeilen werden übersprungen.

    Raises:
        ImportUngueltigError: bei falscher Kodierung, fehlenden Spalten oder ungültigen Werten.
            Die Meldung nennt Zeile und Spalte, nie den Wert.
    """
    try:
        text = daten.decode(profil.kodierung)
    except (UnicodeDecodeError, LookupError) as fehler:
        msg = f"Die Datei passt nicht zur Kodierung des Profils ({profil.kodierung})."
        raise ImportUngueltigError(msg) from fehler
    zeilen = text.removeprefix("﻿").splitlines()[profil.kopfzeilen_ueberspringen :]
    leser = csv.DictReader(io.StringIO("\n".join(zeilen)), delimiter=profil.trennzeichen)
    vorhanden = set(leser.fieldnames or ())
    for spalte in profil.spalten:
        if spalte not in vorhanden:
            msg = f"Spalte fehlt: {spalte}"
            raise ImportUngueltigError(msg)
    umsaetze: list[Umsatz] = []
    for nummer, zeile in enumerate(leser, start=profil.kopfzeilen_ueberspringen + 2):
        if not any((wert or "").strip() for wert in zeile.values() if isinstance(wert, str)):
            continue
        umsaetze.append(_umsatz(zeile, profil, nummer))
    return umsaetze


def _umsatz(zeile: dict[str, str | None], profil: CsvProfil, nummer: int) -> Umsatz:
    def wert(spalte: str | None) -> str:
        return (zeile.get(spalte) or "").strip() if spalte else ""

    buchungstag = _datum(wert(profil.spalte_buchungstag), profil, nummer, "Buchungstag")
    valuta_text = wert(profil.spalte_valuta)
    valuta = _datum(valuta_text, profil, nummer, "Valuta") if valuta_text else None
    betrag = _betrag(wert(profil.spalte_betrag), profil, nummer)
    zweck = " ".join(teil for teil in (wert(s) for s in profil.spalten_verwendungszweck) if teil)
    return Umsatz(
        buchungstag=buchungstag,
        valuta=valuta,
        betrag=abs(betrag),
        richtung=Richtung.BELASTUNG if betrag < 0 else Richtung.GUTSCHRIFT,
        gegen_name=wert(profil.spalte_gegen_name) or None,
        gegen_iban=iban_normiert(wert(profil.spalte_gegen_iban)),
        verwendungszweck=zweck,
    )


def _datum(text: str, profil: CsvProfil, nummer: int, feld: str) -> date:
    try:
        return datetime.strptime(text, profil.datumsformat).date()  # noqa: DTZ007
    except ValueError as fehler:
        msg = f"Zeile {nummer}: {feld} passt nicht zum Datumsformat des Profils."
        raise ImportUngueltigError(msg) from fehler


def _betrag(text: str, profil: CsvProfil, nummer: int) -> Decimal:
    """Betrag in der Schreibweise des Profils in den kanonischen Text und dann in Decimal."""
    roh = text.replace(" ", "")
    if profil.tausendertrennzeichen:
        teile = roh.split(profil.dezimaltrennzeichen)
        ganz = teile[0]
        if profil.tausendertrennzeichen in ganz:
            if not re.fullmatch(
                rf"[+-]?\d{{1,3}}({re.escape(profil.tausendertrennzeichen)}\d{{3}})+", ganz
            ):
                return _ungueltig(nummer)
            teile[0] = ganz.replace(profil.tausendertrennzeichen, "")
        roh = profil.dezimaltrennzeichen.join(teile)
    if roh.count(profil.dezimaltrennzeichen) > 1:
        return _ungueltig(nummer)
    kanonisch = roh.replace(profil.dezimaltrennzeichen, ".").removeprefix("+")
    try:
        ergebnis = kanonischer_betrag(kanonisch)
    except (TypeError, ValueError):
        return _ungueltig(nummer)
    if ergebnis == 0:
        return _ungueltig(nummer)
    return ergebnis


def _ungueltig(nummer: int) -> Decimal:
    msg = f"Zeile {nummer}: Betrag ungültig oder null."
    raise ImportUngueltigError(msg)
