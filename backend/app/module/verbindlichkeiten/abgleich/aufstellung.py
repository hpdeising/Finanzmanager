# SPDX-License-Identifier: AGPL-3.0-or-later
"""Forderungsaufstellung des Gläubigers und Ergebnis des Abgleichs (Fachkonzept Kap. 5.3).

Die Aufstellung hat dieselbe Form wie die Erwartungswerte eines Golden Files (Kap. 12): Summen
zum Stichtag wie ``erwartung``, Zinsen je Zeitraum wie die Zeilen von ``<id>.rechenweg.csv``,
verrechnete Zahlungen wie ``<id>.anrechnung.csv``, dazu die Kosten je Position. Werte stehen als
Text in der Schreibweise der CSV-Dateien; ein leerer Wert heißt: die Aufstellung nennt ihn nicht.
So entspricht jede Position des Abgleichs genau einem ``ort`` im Block ``abweichungen``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from app.module.verbindlichkeiten.domain import EingabeUngueltigError

SUMMEN = ("hauptforderung", "zinsen", "kosten", "gesamt")
SPALTEN_RECHENWEG = (
    "bestandteil",
    "von",
    "bis",
    "grund",
    "tage",
    "tagesbasis",
    "basis",
    "basiszins",
    "satz",
    "zins_ungerundet",
    "zins_gerundet",
)
SPALTEN_ANRECHNUNG = ("zahlung", "betrag", "bestandteil", "gruppe", "angerechnet", "offen_danach")


class Bereich(StrEnum):
    """Wo eine Position der Aufstellung steht."""

    SUMME = "summe"
    RECHENWEG = "rechenweg"
    ANRECHNUNG = "anrechnung"
    KOSTEN = "kosten"


class Ursache(StrEnum):
    """Mögliche Ursache einer Abweichung (Kap. 5.3)."""

    ZINSSATZ = "zinssatz"
    TAGESZAEHLUNG = "tageszaehlung"
    ZINSBEGINN = "zinsbeginn"
    ZAHLTAG = "zahltag"
    TEILUNG = "teilung"
    ANRECHNUNGSREIHENFOLGE = "anrechnungsreihenfolge"
    UNBEKANNTE_KOSTEN = "unbekannte_kosten"
    FEHLENDE_ZAHLUNGEN = "fehlende_zahlungen"

    @property
    def anzeige(self) -> str:
        """Bezeichnung wie in Kap. 5.3."""
        return _ANZEIGE[self]


_ANZEIGE = {
    Ursache.ZINSSATZ: "Zinssatz",
    Ursache.TAGESZAEHLUNG: "Tageszählung",
    Ursache.ZINSBEGINN: "Zinsbeginn",
    Ursache.ZAHLTAG: "Zahltag",
    Ursache.TEILUNG: "Teilung der Abschnitte",
    Ursache.ANRECHNUNGSREIHENFOLGE: "Anrechnungsreihenfolge",
    Ursache.UNBEKANNTE_KOSTEN: "unbekannte Kosten",
    Ursache.FEHLENDE_ZAHLUNGEN: "fehlende Zahlungen",
}
KEINE_URSACHE = "keine Ursache gefunden"


@dataclass(frozen=True, slots=True)
class Kostenposition:
    """Kostenposition der Aufstellung; ``kennung`` ist der erfasste Bestandteil, falls bekannt."""

    kennung: str | None
    betrag: str


@dataclass(frozen=True, slots=True)
class Aufstellung:
    """Positionen der Forderungsaufstellung, wie der Nutzer sie erfasst (Kap. 5.3)."""

    stichtag: date
    summen: Mapping[str, str] = field(default_factory=dict[str, str])
    rechenweg: tuple[Mapping[str, str], ...] = ()
    anrechnung: tuple[Mapping[str, str], ...] = ()
    kosten: tuple[Kostenposition, ...] = ()

    def __post_init__(self) -> None:
        if unbekannt := set(self.summen) - set(SUMMEN):
            _fehler(f"Unbekannte Summe: {', '.join(sorted(unbekannt))}.")
        for zeilen, spalten in (
            (self.rechenweg, SPALTEN_RECHENWEG),
            (self.anrechnung, SPALTEN_ANRECHNUNG),
        ):
            for zeile in zeilen:
                if unbekannt := set(zeile) - set(spalten):
                    _fehler(f"Unbekannte Spalte: {', '.join(sorted(unbekannt))}.")


@dataclass(frozen=True, slots=True)
class Position:
    """Eine Position der Aufstellung.

    ``nummer`` zählt die Datenzeilen von Rechenweg und Anrechnung und die Kostenpositionen ab 1;
    bei Summen ist sie leer. ``spalte`` ist die Spalte der CSV-Datei, der Name der Summe oder bei
    Kosten ``betrag``.
    """

    bereich: Bereich
    spalte: str
    nummer: int | None = None


@dataclass(frozen=True, slots=True)
class Abweichung:
    """Ein Wert der Aufstellung, den das Programm anders berechnet.

    ``laut_aufstellung`` ist leer, wenn das Programm eine Zeile mehr hat als die Aufstellung,
    ``programm`` ist leer, wenn es die Position im Programm nicht gibt. Sind die ``ursachen``
    leer, erklärt keine der Ursachen aus Kap. 5.3 die Abweichung; angezeigt wird dann „keine
    Ursache gefunden“.
    """

    position: Position
    laut_aufstellung: str | None
    programm: str | None
    ursachen: frozenset[Ursache]

    @property
    def ursachen_anzeige(self) -> tuple[str, ...]:
        """Die Ursachen in der Reihenfolge von Kap. 5.3, sonst „keine Ursache gefunden“."""
        if not self.ursachen:
            return (KEINE_URSACHE,)
        return tuple(u.anzeige for u in Ursache if u in self.ursachen)


@dataclass(frozen=True, slots=True)
class Abgleich:
    """Alle Abweichungen einer Aufstellung, in der Reihenfolge der Aufstellung."""

    abweichungen: tuple[Abweichung, ...]

    @property
    def ursachen(self) -> frozenset[Ursache]:
        """Alle möglichen Ursachen zusammen."""
        return frozenset(u for a in self.abweichungen for u in a.ursachen)


def _fehler(meldung: str) -> None:
    raise EingabeUngueltigError(meldung)
