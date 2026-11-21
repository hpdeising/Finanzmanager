# SPDX-License-Identifier: AGPL-3.0-or-later
"""Status, Merkmale und Nachwirkungs-Aufgaben einer Akte (Fachkonzept Kap. 6).

Der Status wird aus Ereignissen und der Restschuld berechnet und nie gespeichert (Entscheidung
vom 20.11.2026). Wie bei Fristen und Verjährung zählen nur Ereignisse mit Datum bis zum Stichtag;
ein Ereignis ``zahlung``, dessen Buchung storniert ist, liefert der Aufrufer nicht (E-26).

Ablauf:

1. Status aus den Ereignissen: ``offen``, ``mahnverfahren`` ab Zustellung des Mahnbescheids
   und zurück nach ``offen``, wenn das Mahnverfahren ohne Titel endet, ``tituliert`` ab einem
   Titel-Ereignis.
2. Ist die Restschuld 0,00 € und wurde sie durch Zahlungen erreicht, entstehen die
   Nachwirkungs-Aufgaben. Solange eine von ihnen offen ist, ist die Akte in der
   ``nachwirkung``; sind alle erledigt, die keine Information sind, ist sie ``ausgeglichen``,
   also bereit zum Schließen (Entscheidung vom 21.11.2026).
3. ``geschlossen`` setzt der Nutzer mit dem Ereignis ``akte_geschlossen``, frühestens wenn die
   Restschuld 0,00 € ist und alle Nachwirkungs-Aufgaben erledigt sind. Informationen bleiben
   sichtbar.
4. Rückweg (E-37): Steigt die Restschuld wieder über 0,00 €, gilt wieder der Status aus 1.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from app.module.verbindlichkeiten.berechnung import Ergebnis
from app.module.verbindlichkeiten.domain import Ereignis, Ereignistyp
from app.module.verbindlichkeiten.fristen import Dauer, Einheit, Fristart, fristende

EIN_TAG = timedelta(days=1)
HINWEIS_VOLLSTRECKUNG_TROTZ_ERFUELLUNG = (
    "Der Gläubiger vollstreckt nach dem Ausgleich weiter. Dagegen kommen die "
    "Vollstreckungsabwehrklage (§ 767 ZPO) und die einstweilige Einstellung der "
    "Zwangsvollstreckung (§ 769 ZPO) in Betracht. Anwaltliche Hilfe wird empfohlen."
)

_TITEL = {
    Ereignistyp.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID,
    Ereignistyp.ZUSTELLUNG_URTEIL,
    Ereignistyp.ERRICHTUNG_TITEL,
    Ereignistyp.ZUSTELLUNG_KOSTENFESTSETZUNGSBESCHLUSS,
}
_VOLLSTRECKUNG = {
    Ereignistyp.VOLLSTRECKUNGSANTRAG,
    Ereignistyp.VOLLSTRECKUNGSHANDLUNG,
    Ereignistyp.VOLLSTRECKUNGSMASSNAHME_BEGONNEN,
}


class Status(StrEnum):
    """Lebenszyklus einer Akte (Kap. 6), in seiner Reihenfolge."""

    OFFEN = "offen"
    MAHNVERFAHREN = "mahnverfahren"
    TITULIERT = "tituliert"
    NACHWIRKUNG = "nachwirkung"
    AUSGEGLICHEN = "ausgeglichen"
    GESCHLOSSEN = "geschlossen"


class Merkmal(StrEnum):
    """Merkmale unabhängig vom Status (Kap. 6), abgeleitet aus Ereignissen."""

    RATENPLAN_AKTIV = "ratenplan_aktiv"
    VOLLSTRECKUNG_AKTIV = "vollstreckung_aktiv"
    BESTRITTEN = "bestritten"
    SCHULDNERVERZEICHNIS_EINGETRAGEN = "schuldnerverzeichnis_eingetragen"
    VERJAEHRUNG_EINGEWANDT = "verjaehrung_eingewandt"


class Aufgabentyp(StrEnum):
    """Nachwirkungs-Aufgaben bei Ausgleich (Kap. 6), in der Reihenfolge des Fachkonzepts."""

    QUITTUNG_ANFORDERN = "quittung_anfordern"
    TITEL_HERAUSVERLANGEN = "titel_herausverlangen"
    VORZEITIGE_LOESCHUNG = "vorzeitige_loeschung"
    AUSKUNFTEI_PRUEFEN = "auskunftei_pruefen"
    AUSKUNFTEI_LOESCHDATUM_UEBERWACHEN = "auskunftei_loeschdatum_ueberwachen"

    @property
    def norm(self) -> str:
        return _NORM[self]

    @property
    def information(self) -> bool:
        """Eine Information ist nie zu erledigen und hindert das Schließen nicht."""
        return self is Aufgabentyp.AUSKUNFTEI_LOESCHDATUM_UEBERWACHEN


_NORM = {
    Aufgabentyp.QUITTUNG_ANFORDERN: "§ 368 BGB",
    Aufgabentyp.TITEL_HERAUSVERLANGEN: "§ 371 BGB analog; § 757 Abs. 1 ZPO",
    Aufgabentyp.VORZEITIGE_LOESCHUNG: "§ 882e Abs. 3 Nr. 1 ZPO",
    Aufgabentyp.AUSKUNFTEI_PRUEFEN: "Art. 15 DSGVO",
    Aufgabentyp.AUSKUNFTEI_LOESCHDATUM_UEBERWACHEN: (
        "Verhaltensregeln der Auskunfteien (Code of Conduct)"
    ),
}
_ERLEDIGT_DURCH = {
    Aufgabentyp.QUITTUNG_ANFORDERN: Ereignistyp.QUITTUNG_ERHALTEN,
    Aufgabentyp.TITEL_HERAUSVERLANGEN: Ereignistyp.TITEL_ERHALTEN,
    Aufgabentyp.AUSKUNFTEI_PRUEFEN: Ereignistyp.ERLEDIGT_GEMELDET_AUSKUNFTEI,
}


@dataclass(frozen=True, slots=True)
class Aufgabe:
    """Eine Nachwirkungs-Aufgabe. ``faellig_ab`` fehlt, wo es kein Datum gibt."""

    typ: Aufgabentyp
    faellig_ab: date | None
    erledigt_am: date | None = None

    @property
    def norm(self) -> str:
        return self.typ.norm

    @property
    def information(self) -> bool:
        return self.typ.information


@dataclass(frozen=True, slots=True)
class Statusergebnis:
    status: Status
    merkmale: frozenset[Merkmal]
    aufgaben: tuple[Aufgabe, ...] = ()
    ausgeglichen_am: date | None = None
    hinweise: tuple[str, ...] = ()
    warnungen: tuple[str, ...] = ()


def status_berechnen(
    ereignisse: Sequence[Ereignis], stichtag: date, ergebnis: Ergebnis
) -> Statusergebnis:
    """Status, Merkmale und Nachwirkungs-Aufgaben zum ``stichtag`` (Kap. 6).

    ``ergebnis`` ist die Berechnung zum selben Stichtag (``berechne``); aus ihr kommen Restschuld
    und Ausgleichstag.
    """
    erfasst = sorted(
        (e for e in ereignisse if e.datum is not None and e.datum <= stichtag),
        key=lambda e: e.datum or date.min,
    )
    grundstatus = _grundstatus(erfasst)
    merkmale = _merkmale(erfasst, stichtag)
    warnungen: list[str] = []
    schliessen = [e.datum for e in erfasst if e.typ is Ereignistyp.AKTE_GESCHLOSSEN and e.datum]

    ausgeglichen_am = _ausgleichstag(ergebnis)
    if ausgeglichen_am is None:
        if schliessen:
            warnungen.append(
                "Die Akte ist nicht geschlossen: Die Restschuld liegt über 0,00 € (E-37)."
            )
        return Statusergebnis(grundstatus, merkmale, warnungen=tuple(warnungen))

    aufgaben = _aufgaben(erfasst, ausgeglichen_am, grundstatus, stichtag)
    hinweise: list[str] = []
    if _vollstreckung_nach_ausgleich(erfasst, ausgeglichen_am, merkmale):
        hinweise.append(HINWEIS_VOLLSTRECKUNG_TROTZ_ERFUELLUNG)

    status = Status.AUSGEGLICHEN if _darf_schliessen(aufgaben, stichtag) else Status.NACHWIRKUNG
    gueltig = [tag for tag in schliessen if tag >= ausgeglichen_am]
    if any(_darf_schliessen(aufgaben, tag) for tag in gueltig):
        status = Status.GESCHLOSSEN
    elif gueltig:
        warnungen.append(
            "Schließen nicht wirksam: Am Tag des Schließens waren Nachwirkungs-Aufgaben offen."
        )
    return Statusergebnis(
        status, merkmale, aufgaben, ausgeglichen_am, tuple(hinweise), tuple(warnungen)
    )


def _grundstatus(erfasst: Sequence[Ereignis]) -> Status:
    """Status vor dem Ausgleich: ``tituliert`` mit einem Titel-Ereignis, sonst
    ``mahnverfahren`` mit der Zustellung eines Mahnbescheids, sonst ``offen`` (Kap. 6).

    Endet das Mahnverfahren ohne Titel, ist die Akte wieder ``offen``, bis ein neuer Mahnbescheid
    zugestellt wird (Entscheidung vom 21.11.2026)."""
    if any(e.typ in _TITEL for e in erfasst):
        return Status.TITULIERT
    if _zuletzt(
        erfasst, Ereignistyp.ZUSTELLUNG_MAHNBESCHEID, Ereignistyp.MAHNVERFAHREN_OHNE_TITEL_BEENDET
    ):
        return Status.MAHNVERFAHREN
    return Status.OFFEN


def _ausgleichstag(ergebnis: Ergebnis) -> date | None:
    """Tag der letzten Zahlung, die auf einen Bestandteil angerechnet wurde, wenn die Restschuld
    danach 0,00 € ist. Ohne Zahlung ist eine Restschuld von 0,00 € kein Ausgleich."""
    if ergebnis.gesamt != 0:
        return None
    tage = [z.zahlung.datum for z in ergebnis.anrechnungen if z.bestandteil and z.angerechnet > 0]
    return max(tage, default=None)


def _merkmale(erfasst: Sequence[Ereignis], stichtag: date) -> frozenset[Merkmal]:
    merkmale: set[Merkmal] = set()
    if _zuletzt(erfasst, Ereignistyp.RATENPLAN_VEREINBART, Ereignistyp.RATENPLAN_BEENDET):
        merkmale.add(Merkmal.RATENPLAN_AKTIV)
    if _zuletzt(erfasst, Ereignistyp.FORDERUNG_BESTRITTEN, Ereignistyp.BESTREITEN_BEENDET):
        merkmale.add(Merkmal.BESTRITTEN)
    begonnen = sum(e.typ is Ereignistyp.VOLLSTRECKUNGSMASSNAHME_BEGONNEN for e in erfasst)
    aufgehoben = sum(e.typ is Ereignistyp.VOLLSTRECKUNGSMASSNAHME_AUFGEHOBEN for e in erfasst)
    if begonnen > aufgehoben:
        merkmale.add(Merkmal.VOLLSTRECKUNG_AKTIV)
    if _eintragung(erfasst, stichtag) is not None:
        merkmale.add(Merkmal.SCHULDNERVERZEICHNIS_EINGETRAGEN)
    if any(e.typ is Ereignistyp.VERJAEHRUNG_EINGEWANDT for e in erfasst):
        merkmale.add(Merkmal.VERJAEHRUNG_EINGEWANDT)
    return frozenset(merkmale)


def _zuletzt(erfasst: Sequence[Ereignis], beginn: Ereignistyp, ende: Ereignistyp) -> bool:
    """Ist das letzte Ereignis der beiden Typen ``beginn``?"""
    letztes = next((e for e in reversed(erfasst) if e.typ in (beginn, ende)), None)
    return letztes is not None and letztes.typ is beginn


def _eintragung(erfasst: Sequence[Ereignis], tag: date) -> Ereignis | None:
    """Eintragungsanordnung, die am ``tag`` im Schuldnerverzeichnis steht.

    Die Eintragung endet mit dem Ereignis ``loeschung_schuldnerverzeichnis`` oder von Amts wegen
    nach Ablauf von drei Jahren seit dem Tag der Eintragungsanordnung (§ 882e Abs. 1 ZPO).
    """
    for e in reversed(erfasst):
        if e.datum is None or e.datum > tag:
            continue
        if e.typ is Ereignistyp.LOESCHUNG_SCHULDNERVERZEICHNIS:
            return None
        if e.typ is Ereignistyp.EINTRAGUNGSANORDNUNG:
            return e if tag <= _loeschfrist(e.datum) else None
    return None


def _loeschfrist(anordnung: date) -> date:
    """Letzter Tag der Eintragung nach § 882e Abs. 1 ZPO."""
    return fristende(anordnung, Dauer(3, Einheit.JAHRE), Fristart.INFORMATION)


def _aufgaben(
    erfasst: Sequence[Ereignis], ausgeglichen_am: date, grundstatus: Status, stichtag: date
) -> tuple[Aufgabe, ...]:
    """Nachwirkungs-Aufgaben bei Ausgleich (Kap. 6).

    - Quittung anfordern (§ 368 BGB).
    - Titel herausverlangen (§ 371 BGB analog; § 757 Abs. 1 ZPO), nur bei Titel.
    - Vorzeitige Löschung im Schuldnerverzeichnis beantragen (§ 882e Abs. 3 Nr. 1 ZPO), nur wenn
      am Tag des Ausgleichs eingetragen.
    - Erledigungsmeldung bei Auskunfteien prüfen (Art. 15 DSGVO), frühestens vier Wochen nach
      Ausgleich.
    - Löschdatum der Auskunftei überwachen: Information ohne Datum, solange die Löschfristen der
      Auskunfteien zurückgestellt sind (Kap. 5.4).

    Erledigt ist eine Aufgabe durch ihr Ereignis am Tag des Ausgleichs oder danach.
    """

    def erledigt(typ: Ereignistyp) -> date | None:
        return next(
            (e.datum for e in erfasst if e.typ is typ and e.datum and e.datum >= ausgeglichen_am),
            None,
        )

    aufgaben = [
        Aufgabe(
            Aufgabentyp.QUITTUNG_ANFORDERN,
            ausgeglichen_am,
            erledigt(_ERLEDIGT_DURCH[Aufgabentyp.QUITTUNG_ANFORDERN]),
        )
    ]
    if grundstatus is Status.TITULIERT:
        aufgaben.append(
            Aufgabe(
                Aufgabentyp.TITEL_HERAUSVERLANGEN,
                ausgeglichen_am,
                erledigt(_ERLEDIGT_DURCH[Aufgabentyp.TITEL_HERAUSVERLANGEN]),
            )
        )
    eintragung = _eintragung(erfasst, ausgeglichen_am)
    if eintragung is not None and eintragung.datum is not None:
        geloescht = [erledigt(Ereignistyp.LOESCHUNG_SCHULDNERVERZEICHNIS)]
        von_amts_wegen = _loeschfrist(eintragung.datum) + EIN_TAG
        if von_amts_wegen <= stichtag:
            geloescht.append(von_amts_wegen)
        aufgaben.append(
            Aufgabe(
                Aufgabentyp.VORZEITIGE_LOESCHUNG,
                ausgeglichen_am,
                min((t for t in geloescht if t is not None), default=None),
            )
        )
    aufgaben.append(
        Aufgabe(
            Aufgabentyp.AUSKUNFTEI_PRUEFEN,
            fristende(ausgeglichen_am, Dauer(4, Einheit.WOCHEN), Fristart.INFORMATION),
            erledigt(_ERLEDIGT_DURCH[Aufgabentyp.AUSKUNFTEI_PRUEFEN]),
        )
    )
    aufgaben.append(Aufgabe(Aufgabentyp.AUSKUNFTEI_LOESCHDATUM_UEBERWACHEN, None))
    return tuple(aufgaben)


def _darf_schliessen(aufgaben: Sequence[Aufgabe], tag: date) -> bool:
    """Alle Aufgaben, die keine Information sind, am ``tag`` erledigt."""
    return all(
        a.information or (a.erledigt_am is not None and a.erledigt_am <= tag) for a in aufgaben
    )


def _vollstreckung_nach_ausgleich(
    erfasst: Sequence[Ereignis], ausgeglichen_am: date, merkmale: frozenset[Merkmal]
) -> bool:
    """Vollstreckt der Gläubiger trotz Erfüllung weiter (Kap. 6, Eskalation)?"""
    if Merkmal.VOLLSTRECKUNG_AKTIV in merkmale:
        return True
    return any(e.typ in _VOLLSTRECKUNG and e.datum and e.datum > ausgeglichen_am for e in erfasst)
