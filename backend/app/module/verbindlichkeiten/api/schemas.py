# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schemas der Schnittstelle des Moduls Verbindlichkeiten.

Beträge und Sätze stehen als Text (CLAUDE.md, Geld); Daten als ``YYYY-MM-DD``. Aus diesen
Schemas entsteht die OpenAPI-Beschreibung, aus der die Oberfläche ihre Typen erzeugt.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.kern.web import Betragstext, Dezimaltext
from app.module.verbindlichkeiten.domain import (
    Anrechnungsregel,
    Bestandteilart,
    Ereignistyp,
    Gruppe,
    Tageszaehlung,
    Teilung,
    Zahltag,
    Zinsbeginn,
    Zinsregeltyp,
)
from app.module.verbindlichkeiten.fristen import Fristart
from app.module.verbindlichkeiten.status import Aufgabentyp, Merkmal, Status
from app.module.verbindlichkeiten.verjaehrung import Verjaehrungsfall


class _Eingabe(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Eingaben ---------------------------------------------------------------------------------


class GlaeubigerEingabe(_Eingabe):
    name: str = Field(min_length=1)
    anschrift: str | None = None
    iban: str | None = None
    vertreter: str | None = None
    kontakt: str | None = None


class Parameter(_Eingabe):
    """Aktenparameter (Kap. 5.1) mit den Voreinstellungen des Fachkonzepts."""

    anrechnung: Anrechnungsregel = Anrechnungsregel.BGB_367
    reihenfolge: list[Gruppe] | None = None
    tageszaehlung: Tageszaehlung = Tageszaehlung.ACT_365
    zinsbeginn: Zinsbeginn = Zinsbeginn.GENANNTER_TAG
    zahltag: Zahltag = Zahltag.ALTER_BETRAG
    teilung: Teilung = Teilung.KALENDER
    teilungstage: list[date] = Field(default_factory=list[date])


class AkteEingabe(_Eingabe):
    glaeubiger_id: uuid.UUID
    aktenzeichen_glaeubiger: str | None = None
    verbraucherdarlehen: bool = False
    parameter: Parameter = Field(default_factory=Parameter)


class ZinsregelSchema(_Eingabe):
    typ: Zinsregeltyp
    ab: date | None = None
    bis: date | None = None
    aufschlag: Dezimaltext | None = None
    satz: Dezimaltext | None = None


class BestandteilEingabe(_Eingabe):
    kennung: str = Field(min_length=1)
    art: Bestandteilart
    betrag: Betragstext
    entstanden_am: date
    faellig_am: date | None = None
    kenntnis_am: date | None = None
    zinsregeln: list[ZinsregelSchema] = Field(default_factory=list[ZinsregelSchema])


class EreignisEingabe(_Eingabe):
    """Ereignis ohne Buchung; Zahlungen über ``/zahlungen``."""

    typ: Ereignistyp
    datum: date | None
    versaeumnisurteil: bool = False
    bekanntgabe_am: date | None = None
    gericht_land: str | None = None


class ZahlungEingabe(_Eingabe):
    datum: date
    betrag: Betragstext


# --- Ausgaben ---------------------------------------------------------------------------------


class Angelegt(BaseModel):
    id: uuid.UUID


class GlaeubigerAusgabe(BaseModel):
    id: uuid.UUID
    name: str


class AktenZeile(BaseModel):
    id: uuid.UUID
    glaeubiger_name: str
    aktenzeichen_glaeubiger: str | None
    angelegt_am: datetime
    status: Status | None
    restschuld: Betragstext | None


class BestandteilAusgabe(BaseModel):
    kennung: str
    art: Bestandteilart
    betrag: Betragstext
    entstanden_am: date | None
    faellig_am: date | None
    kenntnis_am: date | None
    zinsregeln: list[ZinsregelSchema]


class EreignisAusgabe(BaseModel):
    id: uuid.UUID
    typ: Ereignistyp
    datum: date | None
    versaeumnisurteil: bool
    bekanntgabe_am: date | None
    gericht_land: str | None
    betrag: Betragstext | None
    storniert: bool


class AbschnittAusgabe(BaseModel):
    bestandteil: str
    von: date
    bis: date
    gruende: list[str]
    tage: int
    tagesbasis: int
    basis: Betragstext
    basiszins: Dezimaltext | None
    satz: Dezimaltext
    zins: Betragstext


class Berechnung(BaseModel):
    """Zinsen und Anrechnung zum Stichtag (Kap. 5.2, 5.3); Restschuld nach Kap. 4.1."""

    hauptforderung: Betragstext
    zinsen: Betragstext
    kosten: Betragstext
    restschuld: Betragstext
    ueberzahlung: Betragstext
    abschnitte: list[AbschnittAusgabe]


class FristAusgabe(BaseModel):
    name: str
    norm: str
    ausloeser: Ereignistyp
    ende: date
    art: Fristart
    warnstufen: list[date]
    hinweis: str | None


class VerjaehrungAusgabe(BaseModel):
    gegenstand: str
    bestandteil: str
    fall: Verjaehrungsfall
    norm: str
    beginn: date | None
    ende: date | None
    hemmungstage: int
    neubeginn: date | None
    warnstufen: list[date]
    hinweise: list[str]


class AufgabeAusgabe(BaseModel):
    typ: Aufgabentyp
    norm: str
    faellig_ab: date | None
    erledigt_am: date | None
    information: bool


class StatusAusgabe(BaseModel):
    status: Status
    merkmale: list[Merkmal]
    aufgaben: list[AufgabeAusgabe]
    ausgeglichen_am: date | None
    hinweise: list[str]
    warnungen: list[str]


class AkteDetail(BaseModel):
    """Eine Akte mit allem, was zum Stichtag aus ihren Eingaben folgt.

    Ein Teil, der sich nicht berechnen lässt (etwa ohne Bundesland oder Stammdaten), fehlt;
    der Grund steht in ``hinweise``.
    """

    id: uuid.UUID
    stichtag: date
    glaeubiger_id: uuid.UUID
    glaeubiger_name: str
    aktenzeichen_glaeubiger: str | None
    verbraucherdarlehen: bool
    parameter: Parameter
    bestandteile: list[BestandteilAusgabe]
    ereignisse: list[EreignisAusgabe]
    berechnung: Berechnung | None
    fristen: list[FristAusgabe] | None
    verjaehrung: list[VerjaehrungAusgabe] | None
    verjaehrung_pflichthinweis: str
    status: StatusAusgabe | None
    hinweise: list[str]
