# SPDX-License-Identifier: AGPL-3.0-or-later
"""Routen des Imports (Fachkonzept Kap. 8): CSV-Profile, Hochladen, Läufe, Abschluss.

Die Datei kommt als roher Inhalt (``application/octet-stream``) und wird nur im Speicher
gelesen, nie gespeichert (Kap. 8, Datenminimierung). Die Einstellung zu P-16 ist bei jedem
Hochladen anzugeben, solange das Fachkonzept keine Voreinstellung festlegt.

Gebucht wird hier nichts. Die Zuordnung zur Akte und die Bestätigung macht ein Modul.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Final

from fastapi import APIRouter, Body, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.kern.import_ import (
    CsvProfil,
    Format,
    ImportLauf,
    ImportUngueltigError,
    LaufUnbekanntError,
    ProfilUnbekanntError,
    ProfilVorhandenError,
    WertstellungAus,
    Zeilenstatus,
    importiere,
    kandidaten,
    laeufe,
    lauf,
    lies_datei,
    loesche_profil,
    profil,
    profile,
    schliesse_ab,
    speichere_profil,
)
from app.kern.web.abhaengigkeiten import HaushaltId, Sitzung
from app.kern.web.typen import Betragstext

# Obergrenze einer Importdatei. Monatsauszüge liegen weit darunter.
HOECHSTGROESSE: Final = 10 * 1024 * 1024

router = APIRouter(prefix="/api/import", tags=["import"])


class CsvProfilEingabe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    spalte_buchungstag: str = Field(min_length=1)
    spalte_betrag: str = Field(min_length=1)
    spalten_verwendungszweck: list[str] = Field(min_length=1)
    spalte_valuta: str | None = None
    spalte_gegen_name: str | None = None
    spalte_gegen_iban: str | None = None
    trennzeichen: str = Field(default=";", min_length=1, max_length=1)
    kodierung: str = "utf-8"
    datumsformat: str = "%d.%m.%Y"
    dezimaltrennzeichen: str = Field(default=",", min_length=1, max_length=1)
    tausendertrennzeichen: str | None = Field(default=".", min_length=1, max_length=1)
    kopfzeilen_ueberspringen: int = Field(default=0, ge=0)


class CsvProfilAusgabe(CsvProfilEingabe):
    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID


class ZeileAusgabe(BaseModel):
    """Zahlungskandidat (Kap. 8): eine Belastung; ``datum`` ist die Wertstellung nach P-16."""

    id: uuid.UUID
    position: int
    datum: date
    buchungstag: date
    valuta: date | None
    betrag: Betragstext
    gegen_name: str | None
    gegen_iban: str | None
    verwendungszweck: str
    status: Zeilenstatus
    duplikat: bool


class LaufKopf(BaseModel):
    id: uuid.UUID
    format: Format
    profil_name: str | None
    wertstellung_aus: WertstellungAus
    umsaetze_gelesen: int
    angelegt_am: datetime
    abgeschlossen_am: datetime | None


class LaufAusgabe(LaufKopf):
    zeilen: list[ZeileAusgabe]


def _profil_ausgabe(profil_id: uuid.UUID, gespeichert: CsvProfil) -> CsvProfilAusgabe:
    return CsvProfilAusgabe(
        id=profil_id,
        name=gespeichert.name,
        spalte_buchungstag=gespeichert.spalte_buchungstag,
        spalte_betrag=gespeichert.spalte_betrag,
        spalten_verwendungszweck=list(gespeichert.spalten_verwendungszweck),
        spalte_valuta=gespeichert.spalte_valuta,
        spalte_gegen_name=gespeichert.spalte_gegen_name,
        spalte_gegen_iban=gespeichert.spalte_gegen_iban,
        trennzeichen=gespeichert.trennzeichen,
        kodierung=gespeichert.kodierung,
        datumsformat=gespeichert.datumsformat,
        dezimaltrennzeichen=gespeichert.dezimaltrennzeichen,
        tausendertrennzeichen=gespeichert.tausendertrennzeichen,
        kopfzeilen_ueberspringen=gespeichert.kopfzeilen_ueberspringen,
    )


def _kopf(gefunden: ImportLauf) -> LaufKopf:
    return LaufKopf(
        id=gefunden.id,
        format=Format(gefunden.format),
        profil_name=gefunden.profil_name,
        wertstellung_aus=WertstellungAus(gefunden.wertstellung_aus),
        umsaetze_gelesen=gefunden.umsaetze_gelesen,
        angelegt_am=gefunden.angelegt_am,
        abgeschlossen_am=gefunden.abgeschlossen_am,
    )


def _lauf_ausgabe(session: Sitzung, gefunden: ImportLauf) -> LaufAusgabe:
    zeilen = [
        ZeileAusgabe(
            id=k.zeile.id,
            position=k.zeile.position,
            datum=k.zeile.datum,
            buchungstag=k.zeile.buchungstag,
            valuta=k.zeile.valuta,
            betrag=k.zeile.betrag,
            gegen_name=k.zeile.gegen_name,
            gegen_iban=k.zeile.gegen_iban,
            verwendungszweck=k.zeile.verwendungszweck,
            status=Zeilenstatus(k.zeile.status),
            duplikat=k.duplikat,
        )
        for k in kandidaten(session, gefunden)
    ]
    return LaufAusgabe(**_kopf(gefunden).model_dump(), zeilen=zeilen)


# --- CSV-Profile ------------------------------------------------------------------------------


@router.get("/csv-profile")
def liste_profile(session: Sitzung, haushalt_id: HaushaltId) -> list[CsvProfilAusgabe]:
    return [_profil_ausgabe(i, p) for i, p in profile(session, haushalt_id)]


@router.post("/csv-profile", status_code=status.HTTP_201_CREATED)
def lege_profil_an(
    eingabe: CsvProfilEingabe, session: Sitzung, haushalt_id: HaushaltId
) -> CsvProfilAusgabe:
    try:
        neu = CsvProfil(
            **eingabe.model_dump(exclude={"spalten_verwendungszweck"}),
            spalten_verwendungszweck=tuple(eingabe.spalten_verwendungszweck),
        )
        profil_id = speichere_profil(session, haushalt_id=haushalt_id, profil=neu)
    except ProfilVorhandenError as fehler:
        raise HTTPException(status.HTTP_409_CONFLICT, str(fehler)) from fehler
    except ValueError as fehler:  # ProfilUngueltigError und Prüfungen von CsvProfil
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(fehler)) from fehler
    return _profil_ausgabe(profil_id, neu)


@router.delete("/csv-profile/{profil_id}", status_code=status.HTTP_204_NO_CONTENT)
def entferne_profil(profil_id: uuid.UUID, session: Sitzung, haushalt_id: HaushaltId) -> Response:
    try:
        loesche_profil(session, haushalt_id, profil_id)
    except ProfilUnbekanntError as fehler:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CSV-Profil unbekannt.") from fehler
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Läufe ------------------------------------------------------------------------------------


@router.post("/laeufe", status_code=status.HTTP_201_CREATED)
def lade_hoch(
    daten: Annotated[bytes, Body(media_type="application/octet-stream")],
    session: Sitzung,
    haushalt_id: HaushaltId,
    dateiformat: Annotated[Format, Query()],
    wertstellung_aus: Annotated[WertstellungAus, Query(description="Einstellung zu P-16")],
    profil_id: Annotated[uuid.UUID | None, Query(description="Nur bei CSV")] = None,
) -> LaufAusgabe:
    """Datei hochladen: Zahlungskandidaten und Duplikate erkennen (Kap. 8, Schritte 1 bis 3).

    Gespeichert werden nur Belastungen, die keine Rückbuchung sind; die Datei selbst nicht.
    """
    if len(daten) > HOECHSTGROESSE:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Die Datei ist größer als 10 MiB.")
    if (dateiformat is Format.CSV) != (profil_id is not None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Ein CSV-Profil gehört genau zu CSV."
        )
    gewaehlt = None
    if profil_id is not None:
        try:
            gewaehlt = profil(session, haushalt_id, profil_id)
        except ProfilUnbekanntError as fehler:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "CSV-Profil unbekannt.") from fehler
    try:
        neu = importiere(
            session,
            haushalt_id=haushalt_id,
            umsaetze=lies_datei(daten, dateiformat, gewaehlt),
            dateiformat=dateiformat,
            profil_name=None if gewaehlt is None else gewaehlt.name,
            wertstellung_aus=wertstellung_aus,
        )
    except ImportUngueltigError as fehler:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(fehler)) from fehler
    session.refresh(neu)
    return _lauf_ausgabe(session, neu)


@router.get("/laeufe")
def liste_laeufe(session: Sitzung, haushalt_id: HaushaltId) -> list[LaufKopf]:
    return [_kopf(gefunden) for gefunden in laeufe(session, haushalt_id)]


@router.get("/laeufe/{lauf_id}")
def lies_lauf(lauf_id: uuid.UUID, session: Sitzung, haushalt_id: HaushaltId) -> LaufAusgabe:
    try:
        return _lauf_ausgabe(session, lauf(session, haushalt_id, lauf_id))
    except LaufUnbekanntError as fehler:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Importlauf unbekannt.") from fehler


@router.post("/laeufe/{lauf_id}/abschluss")
def schliesse_lauf_ab(lauf_id: uuid.UUID, session: Sitzung, haushalt_id: HaushaltId) -> LaufAusgabe:
    """Lauf abschließen; Zeilen ohne Buchung werden verworfen (Kap. 8, Datenminimierung)."""
    try:
        return _lauf_ausgabe(session, schliesse_ab(session, haushalt_id, lauf_id))
    except LaufUnbekanntError as fehler:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Importlauf unbekannt.") from fehler
