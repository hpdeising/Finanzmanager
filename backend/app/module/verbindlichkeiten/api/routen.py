# SPDX-License-Identifier: AGPL-3.0-or-later
"""Routen des Moduls Verbindlichkeiten unter ``/api/verbindlichkeiten``.

Die Routen speichern über das Paket ``akten`` und berechnen bei jeder Abfrage neu (E-21):
Zinsen und Anrechnung, Fristen, Verjährung und Status. Gespeichert wird davon nichts.
"""

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime
from typing import Annotated, Final
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.kern.ledger import EingabeUngueltigError as LedgerEingabeError
from app.kern.ledger import KontoBelegtError, StornoNichtMoeglichError
from app.kern.stammdaten import StammdatenError
from app.kern.web import HaushaltId, Sitzung, Stammdaten, StammdatenAbh
from app.module.verbindlichkeiten.akten import (
    Akteninhalt,
    AkteUnbekanntError,
    EreignisUnbekanntError,
    GlaeubigerUnbekanntError,
    akten,
    erfasse_ereignis,
    erfasse_zahlung,
    lade_akte,
    lege_akte_an,
    lege_bestandteil_an,
    lege_glaeubiger_an,
    loesche_ereignis,
    storniere_zahlung,
)
from app.module.verbindlichkeiten.api.schemas import (
    AbschnittAusgabe,
    AkteDetail,
    AkteEingabe,
    AktenZeile,
    Angelegt,
    AufgabeAusgabe,
    Berechnung,
    BestandteilAusgabe,
    BestandteilEingabe,
    EreignisAusgabe,
    EreignisEingabe,
    FristAusgabe,
    GlaeubigerAusgabe,
    GlaeubigerEingabe,
    Parameter,
    StatusAusgabe,
    VerjaehrungAusgabe,
    ZahlungEingabe,
    ZinsregelSchema,
)
from app.module.verbindlichkeiten.berechnung import Ergebnis, berechne
from app.module.verbindlichkeiten.db import Glaeubiger
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Bestandteil,
    EingabeUngueltigError,
    Ereignis,
    Zahlung,
    Zinsregel,
)
from app.module.verbindlichkeiten.fristen import fristen_aus_ereignissen
from app.module.verbindlichkeiten.status import status_berechnen
from app.module.verbindlichkeiten.verjaehrung import PFLICHTHINWEIS, verjaehrung_berechnen

# Zeitzone der Installation für „heute“ (CLAUDE.md: fachliche Daten als date).
ZEITZONE: Final = ZoneInfo("Europe/Berlin")
OHNE_BUNDESLAND: Final = (
    "Bundesland des Haushalts fehlt: ohne Feiertage keine Fristen und keine Verjährung."
)

router = APIRouter(prefix="/api/verbindlichkeiten", tags=["verbindlichkeiten"])

Stichtag = Annotated[date | None, Query(description="Stichtag; ohne Angabe heute")]


def heute() -> date:
    return datetime.now(ZEITZONE).date()


@contextmanager
def _fachfehler() -> Generator[None]:
    """Fachliche Fehler in HTTP-Antworten übersetzen; die Meldungen nennen keine Personendaten."""
    try:
        yield
    except (AkteUnbekanntError, EreignisUnbekanntError, GlaeubigerUnbekanntError) as fehler:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nicht gefunden.") from fehler
    except (StornoNichtMoeglichError, KontoBelegtError) as fehler:
        raise HTTPException(status.HTTP_409_CONFLICT, str(fehler)) from fehler
    except (EingabeUngueltigError, LedgerEingabeError) as fehler:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(fehler)) from fehler


# --- Gläubiger ----------------------------------------------------------------------------------


@router.get("/glaeubiger")
def liste_glaeubiger(session: Sitzung, haushalt_id: HaushaltId) -> list[GlaeubigerAusgabe]:
    zeilen = session.scalars(
        select(Glaeubiger).where(Glaeubiger.haushalt_id == haushalt_id).order_by(Glaeubiger.name)
    )
    return [GlaeubigerAusgabe(id=g.id, name=g.name) for g in zeilen]


@router.post("/glaeubiger", status_code=status.HTTP_201_CREATED)
def neuer_glaeubiger(
    eingabe: GlaeubigerEingabe, session: Sitzung, haushalt_id: HaushaltId
) -> Angelegt:
    with _fachfehler():
        return Angelegt(
            id=lege_glaeubiger_an(session, haushalt_id=haushalt_id, **eingabe.model_dump())
        )


# --- Akten --------------------------------------------------------------------------------------


@router.get("/akten")
def liste_akten(
    session: Sitzung, haushalt_id: HaushaltId, stammdaten: StammdatenAbh, stichtag: Stichtag = None
) -> list[AktenZeile]:
    """Akten des Haushalts mit Status und Restschuld zum Stichtag."""
    tag = stichtag or heute()
    zeilen: list[AktenZeile] = []
    for kopf in akten(session, haushalt_id=haushalt_id):
        inhalt = lade_akte(session, haushalt_id=haushalt_id, akte_id=kopf.id)
        try:
            ergebnis = _berechne(inhalt, tag, stammdaten)
            akte_status = status_berechnen(inhalt.ereignisse, tag, ergebnis).status
            restschuld = ergebnis.gesamt
        except StammdatenError:
            akte_status, restschuld = None, None
        zeilen.append(
            AktenZeile(
                id=kopf.id,
                glaeubiger_name=kopf.glaeubiger_name,
                aktenzeichen_glaeubiger=kopf.aktenzeichen_glaeubiger,
                angelegt_am=kopf.angelegt_am,
                status=akte_status,
                restschuld=restschuld,
            )
        )
    return zeilen


@router.post("/akten", status_code=status.HTTP_201_CREATED)
def neue_akte(eingabe: AkteEingabe, session: Sitzung, haushalt_id: HaushaltId) -> Angelegt:
    with _fachfehler():
        p = eingabe.parameter
        parameter = Aktenparameter(
            anrechnung=p.anrechnung,
            reihenfolge=tuple(p.reihenfolge) if p.reihenfolge is not None else None,
            tageszaehlung=p.tageszaehlung,
            zinsbeginn=p.zinsbeginn,
            zahltag=p.zahltag,
            teilung=p.teilung,
            teilungstage=frozenset(p.teilungstage),
        )
        akte_id = lege_akte_an(
            session,
            haushalt_id=haushalt_id,
            glaeubiger_id=eingabe.glaeubiger_id,
            parameter=parameter,
            verbraucherdarlehen=eingabe.verbraucherdarlehen,
            aktenzeichen_glaeubiger=eingabe.aktenzeichen_glaeubiger,
        )
    return Angelegt(id=akte_id)


@router.get("/akten/{akte_id}")
def lies_akte(
    akte_id: uuid.UUID,
    session: Sitzung,
    haushalt_id: HaushaltId,
    stammdaten: StammdatenAbh,
    stichtag: Stichtag = None,
) -> AkteDetail:
    """Akte mit Berechnung, Fristen, Verjährung und Status zum Stichtag."""
    with _fachfehler():
        inhalt = lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id)
    return _detail(inhalt, stichtag or heute(), stammdaten)


@router.post("/akten/{akte_id}/bestandteile", status_code=status.HTTP_201_CREATED)
def neuer_bestandteil(
    akte_id: uuid.UUID, eingabe: BestandteilEingabe, session: Sitzung, haushalt_id: HaushaltId
) -> Angelegt:
    with _fachfehler():
        lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id)
        bestandteil = Bestandteil(
            eingabe.kennung,
            eingabe.art,
            eingabe.betrag,
            [
                Zinsregel(r.typ, ab=r.ab, bis=r.bis, aufschlag=r.aufschlag, satz=r.satz)
                for r in eingabe.zinsregeln
            ],
            eingabe.entstanden_am,
            faellig_am=eingabe.faellig_am,
            kenntnis_am=eingabe.kenntnis_am,
        )
        return Angelegt(id=lege_bestandteil_an(session, akte_id=akte_id, bestandteil=bestandteil))


@router.post("/akten/{akte_id}/ereignisse", status_code=status.HTTP_201_CREATED)
def neues_ereignis(
    akte_id: uuid.UUID, eingabe: EreignisEingabe, session: Sitzung, haushalt_id: HaushaltId
) -> Angelegt:
    with _fachfehler():
        lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id)
        ereignis = Ereignis(
            eingabe.typ,
            eingabe.datum,
            versaeumnisurteil=eingabe.versaeumnisurteil,
            bekanntgabe_am=eingabe.bekanntgabe_am,
            gericht_land=eingabe.gericht_land,
        )
        return Angelegt(id=erfasse_ereignis(session, akte_id=akte_id, ereignis=ereignis))


@router.delete("/akten/{akte_id}/ereignisse/{ereignis_id}", status_code=status.HTTP_204_NO_CONTENT)
def entferne_ereignis(
    akte_id: uuid.UUID, ereignis_id: uuid.UUID, session: Sitzung, haushalt_id: HaushaltId
) -> None:
    with _fachfehler():
        lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id)
        loesche_ereignis(session, akte_id=akte_id, ereignis_id=ereignis_id)


@router.post("/akten/{akte_id}/zahlungen", status_code=status.HTTP_201_CREATED)
def neue_zahlung(
    akte_id: uuid.UUID, eingabe: ZahlungEingabe, session: Sitzung, haushalt_id: HaushaltId
) -> Angelegt:
    with _fachfehler():
        lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id)
        zahlung = Zahlung(eingabe.datum, eingabe.betrag)
        return Angelegt(id=erfasse_zahlung(session, akte_id=akte_id, zahlung=zahlung))


@router.post(
    "/akten/{akte_id}/zahlungen/{ereignis_id}/storno", status_code=status.HTTP_204_NO_CONTENT
)
def storno(
    akte_id: uuid.UUID, ereignis_id: uuid.UUID, session: Sitzung, haushalt_id: HaushaltId
) -> None:
    """Falsch erfasste Zahlung stornieren (Kap. 4.1); sie gilt danach als nie geschehen."""
    with _fachfehler():
        lade_akte(session, haushalt_id=haushalt_id, akte_id=akte_id)
        storniere_zahlung(session, akte_id=akte_id, ereignis_id=ereignis_id)


# --- Auswertung ---------------------------------------------------------------------------------


def _berechne(inhalt: Akteninhalt, stichtag: date, stammdaten: Stammdaten) -> Ergebnis:
    return berechne(
        inhalt.parameter, inhalt.bestandteile, inhalt.zahlungen, stichtag, stammdaten.basiszinsreihe
    )


def _detail(inhalt: Akteninhalt, stichtag: date, stammdaten: Stammdaten) -> AkteDetail:
    hinweise: list[str] = []
    ergebnis: Ergebnis | None = None
    try:
        ergebnis = _berechne(inhalt, stichtag, stammdaten)
    except StammdatenError as fehler:
        hinweise.append(f"Keine Berechnung: {fehler}")

    fristen: list[FristAusgabe] | None = None
    verjaehrung: list[VerjaehrungAusgabe] | None = None
    land = inhalt.haushalt_land
    if land is None:
        hinweise.append(OHNE_BUNDESLAND)
    else:
        try:
            gefunden, warnungen = fristen_aus_ereignissen(
                inhalt.ereignisse, stammdaten.feiertage, land
            )
            fristen = [
                FristAusgabe(
                    name=f.name,
                    norm=f.norm,
                    ausloeser=f.ausloeser.typ,
                    ende=f.ende,
                    art=f.art,
                    warnstufen=list(f.warnstufen),
                    hinweis=f.hinweis,
                )
                for f in gefunden
            ]
            hinweise.extend(w.text for w in warnungen)
        except StammdatenError as fehler:
            hinweise.append(f"Keine Fristen: {fehler}")
        if ergebnis is not None:
            try:
                v = verjaehrung_berechnen(
                    inhalt.bestandteile,
                    inhalt.ereignisse,
                    stichtag,
                    stammdaten.feiertage,
                    land,
                    verbraucherdarlehen=inhalt.verbraucherdarlehen,
                    abschnitte=ergebnis.abschnitte,
                    anrechnungen=ergebnis.anrechnungen,
                )
                verjaehrung = [
                    VerjaehrungAusgabe(
                        gegenstand=e.gegenstand,
                        bestandteil=e.bestandteil,
                        fall=e.fall,
                        norm=e.norm,
                        beginn=e.beginn,
                        ende=e.ende,
                        hemmungstage=e.hemmungstage,
                        neubeginn=e.neubeginn,
                        warnstufen=list(e.warnstufen),
                        hinweise=list(e.hinweise),
                    )
                    for e in v.eintraege
                ]
                hinweise.extend(v.warnungen)
            except StammdatenError as fehler:
                hinweise.append(f"Keine Verjährung: {fehler}")

    akte_status: StatusAusgabe | None = None
    berechnung: Berechnung | None = None
    if ergebnis is not None:
        s = status_berechnen(inhalt.ereignisse, stichtag, ergebnis)
        akte_status = StatusAusgabe(
            status=s.status,
            merkmale=sorted(s.merkmale),
            aufgaben=[
                AufgabeAusgabe(
                    typ=a.typ,
                    norm=a.norm,
                    faellig_ab=a.faellig_ab,
                    erledigt_am=a.erledigt_am,
                    information=a.information,
                )
                for a in s.aufgaben
            ],
            ausgeglichen_am=s.ausgeglichen_am,
            hinweise=list(s.hinweise),
            warnungen=list(s.warnungen),
        )
        berechnung = Berechnung(
            hauptforderung=ergebnis.hauptforderung,
            zinsen=ergebnis.zinsen,
            kosten=ergebnis.kosten,
            restschuld=ergebnis.gesamt,
            ueberzahlung=ergebnis.ueberzahlung,
            abschnitte=[
                AbschnittAusgabe(
                    bestandteil=a.bestandteil,
                    von=a.von,
                    bis=a.bis,
                    gruende=[g.value for g in a.gruende],
                    tage=a.tage,
                    tagesbasis=a.tagesbasis,
                    basis=a.basis,
                    basiszins=a.basiszins,
                    satz=a.satz,
                    zins=a.zins,
                )
                for a in ergebnis.abschnitte
            ],
        )

    p = inhalt.parameter
    return AkteDetail(
        id=inhalt.kopf.id,
        stichtag=stichtag,
        glaeubiger_id=inhalt.kopf.glaeubiger_id,
        glaeubiger_name=inhalt.kopf.glaeubiger_name,
        aktenzeichen_glaeubiger=inhalt.kopf.aktenzeichen_glaeubiger,
        verbraucherdarlehen=inhalt.verbraucherdarlehen,
        parameter=Parameter(
            anrechnung=p.anrechnung,
            reihenfolge=list(p.reihenfolge) if p.reihenfolge is not None else None,
            tageszaehlung=p.tageszaehlung,
            zinsbeginn=p.zinsbeginn,
            zahltag=p.zahltag,
            teilung=p.teilung,
            teilungstage=sorted(p.teilungstage),
        ),
        bestandteile=[
            BestandteilAusgabe(
                kennung=b.kennung,
                art=b.art,
                betrag=b.betrag,
                entstanden_am=b.entstanden_am,
                faellig_am=b.faellig_am,
                kenntnis_am=b.kenntnis_am,
                zinsregeln=[
                    ZinsregelSchema(
                        typ=r.typ, ab=r.ab, bis=r.bis, aufschlag=r.aufschlag, satz=r.satz
                    )
                    for r in b.zinsregeln
                ],
            )
            for b in inhalt.bestandteile
        ],
        ereignisse=[
            EreignisAusgabe(
                id=e.id,
                typ=e.ereignis.typ,
                datum=e.ereignis.datum,
                versaeumnisurteil=e.ereignis.versaeumnisurteil,
                bekanntgabe_am=e.ereignis.bekanntgabe_am,
                gericht_land=e.ereignis.gericht_land,
                betrag=e.betrag,
                storniert=e.storniert,
            )
            for e in inhalt.erfasst
        ],
        berechnung=berechnung,
        fristen=fristen,
        verjaehrung=verjaehrung,
        verjaehrung_pflichthinweis=PFLICHTHINWEIS,
        status=akte_status,
        hinweise=hinweise,
    )
