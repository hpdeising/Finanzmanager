# SPDX-License-Identifier: AGPL-3.0-or-later
"""Umsatz aus einem Kontoauszug, Wertstellung (P-16) und Erkennung von Duplikaten (Kap. 8).

Ein Umsatz ist eine Zeile des Auszugs, noch keine Buchung. Erst wenn der Nutzer eine
Zuordnung bestätigt, entsteht im Modul je Akte eine Buchung (Kap. 8, Schritt 6). Der Kern
kennt keine Akten; die Zuordnung macht das Modul.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.kern.geld import als_text, ohne_nullen


class ImportUngueltigError(ValueError):
    """Die Datei lässt sich nicht lesen. Die Meldung nennt Zeile oder Feld, nie einen Wert."""


class Richtung(StrEnum):
    BELASTUNG = "belastung"
    GUTSCHRIFT = "gutschrift"


class WertstellungAus(StrEnum):
    """Prüfpunkt P-16: Welches Datum des Auszugs die Wertstellung wird.

    Das Fachkonzept legt keine Voreinstellung fest; die Wahl ist deshalb Pflicht.
    """

    BUCHUNGSTAG = "buchungstag"
    VALUTA = "valuta"


@dataclass(frozen=True, slots=True)
class Umsatz:
    """Eine Zeile des Auszugs. ``betrag`` ist positiv, die Richtung steht in ``richtung``.

    ``rueckbuchung`` markiert eine Rückbuchung der Bank (CAMT: ``RvslInd``); wie sie fachlich
    wirkt, klärt P-17.
    """

    buchungstag: date
    valuta: date | None
    betrag: Decimal
    richtung: Richtung
    gegen_name: str | None
    gegen_iban: str | None
    verwendungszweck: str
    rueckbuchung: bool = False

    def __post_init__(self) -> None:
        if self.betrag <= 0:
            msg = "Der Betrag eines Umsatzes ist positiv; die Richtung steht in richtung."
            raise ValueError(msg)

    @property
    def ist_kandidat(self) -> bool:
        """Zahlungskandidat: eine Belastung, die keine Rückbuchung ist (Kap. 8, Schritt 2)."""
        return self.richtung is Richtung.BELASTUNG and not self.rueckbuchung


def wertstellung(umsatz: Umsatz, aus: WertstellungAus) -> date:
    """Wertstellung nach der Einstellung zu P-16.

    Raises:
        ImportUngueltigError: wenn die Valuta gewählt ist, der Auszug aber keine nennt; es wird
            nicht geschätzt.
    """
    if aus is WertstellungAus.BUCHUNGSTAG:
        return umsatz.buchungstag
    if umsatz.valuta is None:
        msg = "Valuta fehlt, ist aber als Wertstellung eingestellt (P-16)."
        raise ImportUngueltigError(msg)
    return umsatz.valuta


def iban_normiert(iban: str | None) -> str | None:
    """IBAN ohne Leerzeichen, in Großbuchstaben; leer wird ``None``."""
    if iban is None:
        return None
    ergebnis = "".join(iban.split()).upper()
    return ergebnis or None


def duplikat_schluessel(umsatz: Umsatz, datum: date) -> str:
    """SHA-256 aus Datum, Betrag, Gegen-IBAN und Verwendungszweck (Kap. 8, Schritt 3).

    ``datum`` ist die Wertstellung nach P-16. Der Betrag zählt mit Richtung und ohne
    überzählige Nullen, der Verwendungszweck mit zusammengefassten Leerzeichen; der Name des
    Gegenübers zählt nicht.
    """
    vorzeichen = "-" if umsatz.richtung is Richtung.BELASTUNG else "+"
    teile = (
        datum.isoformat(),
        vorzeichen + als_text(ohne_nullen(umsatz.betrag)),
        iban_normiert(umsatz.gegen_iban) or "",
        " ".join(umsatz.verwendungszweck.split()),
    )
    return hashlib.sha256("\x1f".join(teile).encode()).hexdigest()
