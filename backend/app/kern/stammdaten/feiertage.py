# SPDX-License-Identifier: AGPL-3.0-or-later
"""Feiertage je Bundesland aus ``stammdaten/feiertage.yaml`` (Fachkonzept Kap. 5.4 und 7).

Die Datei nennt einen Gültigkeitszeitraum und darin jeden Feiertag mit Datum, Name und den
Ländern, in denen er landesweit gilt (``alle`` für bundesweite). Feiertage, die nur in Teilen
eines Landes gelten, stehen gesondert unter ``regionale_feiertage``: Sie sind keine Feiertage des
Landes, ein Fristende an einem solchen Tag bekommt aber einen Hinweis (Kap. 5.4). Für einen Tag
außerhalb des Zeitraums gibt es keine Auskunft: Dann wird ein Fehler geworfen, nicht geschätzt
(CLAUDE.md, Stammdaten).

Länder als Kürzel nach ISO 3166-2:DE ohne ``DE-``.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.kern.stammdaten.fehler import StammdatenFehlenError, StammdatenUngueltigError
from app.kern.stammdaten.yaml_datei import (
    STAMMDATEN_VERZEICHNIS,
    datum,
    lies_yaml,
    liste,
    text,
    zuordnung,
)

DATEINAME = "feiertage.yaml"
ALLE = "alle"
LAENDER = frozenset(
    {
        "BW",
        "BY",
        "BE",
        "BB",
        "HB",
        "HH",
        "HE",
        "MV",
        "NI",
        "NW",
        "RP",
        "SL",
        "SN",
        "ST",
        "SH",
        "TH",
    }
)


@dataclass(frozen=True, slots=True)
class Feiertag:
    """Ein Feiertag und die Länder, in denen er gilt."""

    datum: date
    name: str
    laender: frozenset[str]


@dataclass(frozen=True, slots=True)
class Feiertagskalender:
    """Feiertage aller Länder für einen Gültigkeitszeitraum."""

    quelle: str
    geprueft_von: str
    gueltig_ab: date
    gueltig_bis: date
    feiertage: tuple[Feiertag, ...]
    regionale_feiertage: tuple[Feiertag, ...] = ()

    @classmethod
    def aus_daten(cls, daten: object) -> "Feiertagskalender":
        """Kalender aus dem ausgewerteten YAML prüfen und erzeugen.

        Raises:
            StammdatenUngueltigError: bei fehlenden oder unbekannten Feldern, unbekannten Ländern,
                einem Feiertag außerhalb des Zeitraums oder nicht streng aufsteigenden Daten.
        """
        felder = zuordnung(
            daten,
            DATEINAME,
            pflicht={"quelle", "geprueft_von", "gueltig_ab", "gueltig_bis", "feiertage"},
            erlaubt={"hinweis", "regionale_feiertage"},
        )
        quelle = text(felder["quelle"], f"{DATEINAME}, quelle")
        geprueft_von = text(felder["geprueft_von"], f"{DATEINAME}, geprueft_von")
        if "hinweis" in felder:
            text(felder["hinweis"], f"{DATEINAME}, hinweis")
        ab = datum(felder["gueltig_ab"], f"{DATEINAME}, gueltig_ab")
        bis = datum(felder["gueltig_bis"], f"{DATEINAME}, gueltig_bis")
        if bis < ab:
            msg = f"{DATEINAME}: gueltig_bis liegt vor gueltig_ab."
            raise StammdatenUngueltigError(msg)
        feiertage = _feiertage(felder["feiertage"], "feiertage", ab, bis)
        regionale = (
            _feiertage(felder["regionale_feiertage"], "regionale_feiertage", ab, bis)
            if "regionale_feiertage" in felder
            else ()
        )
        return cls(quelle, geprueft_von, ab, bis, feiertage, regionale)

    def ist_feiertag(self, tag: date, land: str) -> bool:
        """Ist ``tag`` im Land ``land`` ein gesetzlicher Feiertag?

        Raises:
            StammdatenFehlenError: wenn ``tag`` außerhalb des Gültigkeitszeitraums liegt.
            ValueError: bei einem unbekannten Land.
        """
        self._pruefe(tag, land)
        return any(f.datum == tag and land in f.laender for f in self.feiertage)

    def regionaler_feiertag(self, tag: date, land: str) -> str | None:
        """Name des Feiertags, der am ``tag`` nur in Teilen von ``land`` gilt, sonst nichts.

        Raises:
            StammdatenFehlenError: wenn ``tag`` außerhalb des Gültigkeitszeitraums liegt.
            ValueError: bei einem unbekannten Land.
        """
        self._pruefe(tag, land)
        return next(
            (f.name for f in self.regionale_feiertage if f.datum == tag and land in f.laender),
            None,
        )

    def _pruefe(self, tag: date, land: str) -> None:
        if land not in LAENDER:
            msg = "Unbekanntes Land."
            raise ValueError(msg)
        if not self.gueltig_ab <= tag <= self.gueltig_bis:
            msg = f"Keine Feiertage für {tag.isoformat()} in {DATEINAME}."
            raise StammdatenFehlenError(msg)


def lade_feiertagskalender(pfad: Path | None = None) -> Feiertagskalender:
    """Kalender aus ``stammdaten/feiertage.yaml`` oder ``pfad`` laden.

    Raises:
        StammdatenUngueltigError: wie ``Feiertagskalender.aus_daten`` oder wenn die Datei fehlt.
    """
    return Feiertagskalender.aus_daten(lies_yaml(pfad or STAMMDATEN_VERZEICHNIS / DATEINAME))


def _feiertage(wert: object, feld: str, ab: date, bis: date) -> tuple[Feiertag, ...]:
    feiertage: list[Feiertag] = []
    for nummer, roh in enumerate(liste(wert, f"{DATEINAME}, {feld}"), 1):
        ort = f"{DATEINAME}, {feld} {nummer}"
        f = zuordnung(roh, ort, pflicht={"datum", "name", "laender"}, erlaubt=set())
        tag = datum(f["datum"], f"{ort}, datum")
        if not ab <= tag <= bis:
            msg = f"{ort}: Datum außerhalb des Gültigkeitszeitraums."
            raise StammdatenUngueltigError(msg)
        if feiertage and tag <= feiertage[-1].datum:
            msg = f"{ort}: Daten müssen streng aufsteigen, jedes nur einmal."
            raise StammdatenUngueltigError(msg)
        name = text(f["name"], f"{ort}, name")
        laender = _laender(f["laender"], f"{ort}, laender")
        feiertage.append(Feiertag(tag, name, laender))
    return tuple(feiertage)


def _laender(wert: object, ort: str) -> frozenset[str]:
    eintraege = liste(wert, ort)
    if eintraege == [ALLE]:
        return LAENDER
    if not all(isinstance(e, str) and e in LAENDER for e in eintraege):
        msg = f"{ort}: Kürzel der Länder oder [alle] erwartet."
        raise StammdatenUngueltigError(msg)
    return frozenset(str(e) for e in eintraege)
