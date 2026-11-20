# SPDX-License-Identifier: AGPL-3.0-or-later
"""Basiszinssatz nach § 247 BGB aus ``stammdaten/basiszinssatz.yaml`` (Fachkonzept Kap. 7).

Der Basiszinssatz verändert sich zum 1. Januar und 1. Juli jedes Jahres (§ 247 Abs. 1 BGB).
Die Datei enthält deshalb für jedes Halbjahr einen Eintrag, auch wenn der Satz gleich bleibt,
und zwar lückenlos. Ein Eintrag gilt genau für sein Halbjahr. Für einen Tag vor dem ersten oder
nach dem Halbjahr des letzten Eintrags gibt es keinen Satz: Dann wird ein Fehler geworfen, nicht
der letzte Satz weiterverwendet (CLAUDE.md, Stammdaten; Fachkonzept Kap. 7).
"""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.kern.geld import betrag
from app.kern.stammdaten.fehler import StammdatenFehlenError, StammdatenUngueltigError
from app.kern.stammdaten.yaml_datei import (
    STAMMDATEN_VERZEICHNIS,
    datum,
    lies_yaml,
    liste,
    text,
    zuordnung,
)

DATEINAME = "basiszinssatz.yaml"
HALBJAHRESBEGINN = ((1, 1), (7, 1))


@dataclass(frozen=True, slots=True)
class Basiszinseintrag:
    """Basiszinssatz in Prozent, gültig vom ersten bis zum letzten Tag eines Halbjahrs."""

    gueltig_ab: date
    satz: Decimal

    @property
    def gueltig_bis(self) -> date:
        """Letzter Tag des Halbjahrs."""
        if self.gueltig_ab.month == 1:
            return date(self.gueltig_ab.year, 6, 30)
        return date(self.gueltig_ab.year, 12, 31)


@dataclass(frozen=True, slots=True)
class Basiszinsreihe:
    """Lückenlose Reihe der Basiszinssätze, aufsteigend nach Halbjahr."""

    quelle: str
    geprueft_von: str
    eintraege: tuple[Basiszinseintrag, ...]

    @classmethod
    def aus_daten(cls, daten: object) -> "Basiszinsreihe":
        """Reihe aus dem ausgewerteten YAML prüfen und erzeugen.

        Raises:
            StammdatenUngueltigError: wenn ein Pflichtfeld fehlt, ein Feld unbekannt ist, ein
                Satz nicht als Text in der Form ``"1.27"`` steht, ein Datum kein Halbjahresbeginn
                ist oder die Halbjahre nicht lückenlos aufsteigen.
        """
        felder = zuordnung(
            daten, DATEINAME, pflicht={"quelle", "geprueft_von", "eintraege"}, erlaubt={"hinweis"}
        )
        quelle = text(felder["quelle"], f"{DATEINAME}, quelle")
        geprueft_von = text(felder["geprueft_von"], f"{DATEINAME}, geprueft_von")
        if "hinweis" in felder:
            text(felder["hinweis"], f"{DATEINAME}, hinweis")
        eintraege: list[Basiszinseintrag] = []
        for nummer, roh in enumerate(liste(felder["eintraege"], f"{DATEINAME}, eintraege"), 1):
            ort = f"{DATEINAME}, Eintrag {nummer}"
            eintrag_felder = zuordnung(roh, ort, pflicht={"gueltig_ab", "satz"}, erlaubt=set())
            gueltig_ab = datum(eintrag_felder["gueltig_ab"], f"{ort}, gueltig_ab")
            if (gueltig_ab.month, gueltig_ab.day) not in HALBJAHRESBEGINN:
                msg = f"{ort}: gueltig_ab muss der 1. Januar oder 1. Juli sein (§ 247 Abs. 1 BGB)."
                raise StammdatenUngueltigError(msg)
            satz = _satz(eintrag_felder["satz"], f"{ort}, satz")
            if eintraege and gueltig_ab != _naechstes_halbjahr(eintraege[-1].gueltig_ab):
                msg = f"{ort}: Halbjahre müssen lückenlos aufsteigen."
                raise StammdatenUngueltigError(msg)
            eintraege.append(Basiszinseintrag(gueltig_ab, satz))
        return cls(quelle, geprueft_von, tuple(eintraege))

    def satz_am(self, tag: date) -> Decimal:
        """Basiszinssatz in Prozent, der an ``tag`` gilt (§ 247 Abs. 1 BGB).

        Raises:
            StammdatenFehlenError: wenn kein Eintrag für ``tag`` gilt.
        """
        index = bisect_right([e.gueltig_ab for e in self.eintraege], tag) - 1
        if index < 0 or tag > self.eintraege[index].gueltig_bis:
            msg = f"Kein Basiszinssatz für {tag.isoformat()} in {DATEINAME}."
            raise StammdatenFehlenError(msg)
        return self.eintraege[index].satz


def lade_basiszinsreihe(pfad: Path | None = None) -> Basiszinsreihe:
    """Basiszinsreihe aus ``stammdaten/basiszinssatz.yaml`` oder ``pfad`` laden.

    Raises:
        StammdatenUngueltigError: wie ``Basiszinsreihe.aus_daten`` oder wenn die Datei fehlt.
    """
    return Basiszinsreihe.aus_daten(lies_yaml(pfad or STAMMDATEN_VERZEICHNIS / DATEINAME))


def _satz(wert: object, ort: str) -> Decimal:
    """Satz in Prozent, als Text wie ``"1.27"`` oder ``"-0.88"``: nie als YAML-Zahl."""
    if not isinstance(wert, str):
        msg = f'{ort}: Satz als Text in Anführungszeichen erwartet, etwa "1.27".'
        raise StammdatenUngueltigError(msg)
    try:
        return betrag(wert)
    except ValueError:
        msg = f'{ort}: Satz muss die Form "-1.23" haben.'
        raise StammdatenUngueltigError(msg) from None


def _naechstes_halbjahr(tag: date) -> date:
    if tag.month == 1:
        return date(tag.year, 7, 1)
    return date(tag.year + 1, 1, 1)
