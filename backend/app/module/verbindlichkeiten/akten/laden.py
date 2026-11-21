# SPDX-License-Identifier: AGPL-3.0-or-later
"""Akten laden, als Eingaben für Berechnung, Fristen, Verjährung und Status (E-21).

Zinsen, Anrechnung, Fristen und Status werden nicht gespeichert, sondern aus diesen Eingaben
berechnet. Ein Ereignis ``zahlung``, dessen Buchung storniert ist, gilt als nie geschehen
(E-26): Es fehlt in ``zahlungen`` und ``ereignisse`` und steht nur in ``erfasst``.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.kern.haushalt import Haushalt
from app.kern.ledger import Buchung, Posting
from app.module.verbindlichkeiten.akten.anlegen import ereignis_aus, zahlungskonto_id
from app.module.verbindlichkeiten.akten.fehler import AkteUnbekanntError
from app.module.verbindlichkeiten.db import (
    Akte,
    AkteTeilungstag,
    BestandteilZeile,
    EreignisZeile,
    Glaeubiger,
    ZinsregelZeile,
)
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Anrechnungsregel,
    Bestandteil,
    Bestandteilart,
    Ereignis,
    Gruppe,
    Tageszaehlung,
    Teilung,
    Zahltag,
    Zahlung,
    Zinsbeginn,
    Zinsregel,
    Zinsregeltyp,
)


@dataclass(frozen=True, slots=True)
class AktenKopf:
    """Was die Aktenliste von einer Akte zeigt."""

    id: uuid.UUID
    glaeubiger_id: uuid.UUID
    glaeubiger_name: str
    aktenzeichen_glaeubiger: str | None
    richtung: str
    verbraucherdarlehen: bool
    angelegt_am: datetime


@dataclass(frozen=True, slots=True)
class ErfasstesEreignis:
    """Ein gespeichertes Ereignis mit seiner ID; bei Zahlungen mit Betrag und Storno."""

    id: uuid.UUID
    ereignis: Ereignis
    erfasst_am: datetime
    betrag: Decimal | None = None
    storniert: bool = False


@dataclass(frozen=True, slots=True)
class Akteninhalt:
    """Eine Akte mit allen Eingaben ihrer Berechnung."""

    kopf: AktenKopf
    parameter: Aktenparameter
    verbraucherdarlehen: bool
    haushalt_land: str | None
    bestandteile: tuple[Bestandteil, ...]
    zahlungen: tuple[Zahlung, ...]
    ereignisse: tuple[Ereignis, ...]
    erfasst: tuple[ErfasstesEreignis, ...]


def akten(session: Session, *, haushalt_id: uuid.UUID) -> list[AktenKopf]:
    """Akten des Haushalts, die zuletzt angelegte zuerst."""
    zeilen = session.execute(
        select(Akte, Glaeubiger.name)
        .join(Glaeubiger, Glaeubiger.id == Akte.glaeubiger_id)
        .where(Akte.haushalt_id == haushalt_id)
        .order_by(Akte.angelegt_am.desc(), Akte.id)
    ).all()
    return [_kopf(akte, name) for akte, name in zeilen]


def lade_akte(session: Session, *, haushalt_id: uuid.UUID, akte_id: uuid.UUID) -> Akteninhalt:
    """Akte mit allen Eingaben laden.

    Raises:
        AkteUnbekanntError: wenn die Akte nicht zum Haushalt gehört.
        ValueError: wenn ein gespeicherter Wert keinem Fachbegriff entspricht.
    """
    zeile = session.execute(
        select(Akte, Glaeubiger.name, Haushalt.bundesland)
        .join(Glaeubiger, Glaeubiger.id == Akte.glaeubiger_id)
        .join(Haushalt, Haushalt.id == Akte.haushalt_id)
        .where(Akte.id == akte_id, Akte.haushalt_id == haushalt_id)
    ).one_or_none()
    if zeile is None:
        raise AkteUnbekanntError(str(akte_id))
    akte, name, land = zeile
    erfasst = _erfasst(session, akte_id)
    gueltig = [e for e in erfasst if not e.storniert]
    return Akteninhalt(
        kopf=_kopf(akte, name),
        parameter=_parameter(session, akte),
        verbraucherdarlehen=akte.verbraucherdarlehen,
        haushalt_land=land,
        bestandteile=_bestandteile(session, akte_id),
        zahlungen=tuple(
            Zahlung(e.ereignis.datum, e.betrag)
            for e in sorted(gueltig, key=_reihenfolge)
            if e.betrag is not None and e.ereignis.datum is not None
        ),
        ereignisse=tuple(e.ereignis for e in gueltig),
        erfasst=erfasst,
    )


def _kopf(akte: Akte, name: str) -> AktenKopf:
    return AktenKopf(
        id=akte.id,
        glaeubiger_id=akte.glaeubiger_id,
        glaeubiger_name=name,
        aktenzeichen_glaeubiger=akte.aktenzeichen_glaeubiger,
        richtung=akte.richtung,
        verbraucherdarlehen=akte.verbraucherdarlehen,
        angelegt_am=akte.angelegt_am,
    )


def _parameter(session: Session, akte: Akte) -> Aktenparameter:
    tage = session.scalars(select(AkteTeilungstag.tag).where(AkteTeilungstag.akte_id == akte.id))
    return Aktenparameter(
        anrechnung=Anrechnungsregel(akte.anrechnung),
        tageszaehlung=Tageszaehlung(akte.tageszaehlung),
        zinsbeginn=Zinsbeginn(akte.zinsbeginn),
        zahltag=Zahltag(akte.zahltag),
        teilung=Teilung(akte.teilung),
        teilungstage=frozenset(tage),
        reihenfolge=tuple(Gruppe(g) for g in akte.reihenfolge) if akte.reihenfolge else None,
    )


def _bestandteile(session: Session, akte_id: uuid.UUID) -> tuple[Bestandteil, ...]:
    zeilen = session.scalars(
        select(BestandteilZeile)
        .where(BestandteilZeile.akte_id == akte_id)
        .order_by(BestandteilZeile.entstanden_am.asc().nulls_first(), BestandteilZeile.laufnummer)
    ).all()
    regeln: dict[uuid.UUID, list[Zinsregel]] = {z.id: [] for z in zeilen}
    for regel in session.scalars(
        select(ZinsregelZeile).where(ZinsregelZeile.bestandteil_id.in_(regeln))
    ):
        regeln[regel.bestandteil_id].append(
            Zinsregel(
                Zinsregeltyp(regel.typ),
                ab=regel.ab,
                bis=regel.bis,
                aufschlag=regel.aufschlag,
                satz=regel.satz,
            )
        )
    return tuple(
        Bestandteil(
            z.kennung,
            Bestandteilart(z.art),
            z.ursprungsbetrag,
            regeln[z.id],
            z.entstanden_am,
            faellig_am=z.faellig_am,
            kenntnis_am=z.kenntnis_am,
        )
        for z in zeilen
    )


def _erfasst(session: Session, akte_id: uuid.UUID) -> tuple[ErfasstesEreignis, ...]:
    """Alle Ereignisse der Akte, nach Datum (ohne Datum zuletzt), dann nach Erfassung."""
    konto_id = zahlungskonto_id(session, akte_id)
    storno = aliased(Buchung)
    zeilen = session.execute(
        select(EreignisZeile, Posting.betrag, storno.id.is_not(None))
        .outerjoin(
            Posting,
            (Posting.buchung_id == EreignisZeile.buchung_id) & (Posting.konto_id == konto_id),
        )
        .outerjoin(storno, storno.storno_von == EreignisZeile.buchung_id)
        .where(EreignisZeile.akte_id == akte_id)
    ).all()
    erfasst = [
        ErfasstesEreignis(
            id=zeile.id,
            ereignis=ereignis_aus(zeile.typ, zeile.datum, zeile.details),
            erfasst_am=zeile.erfasst_am,
            betrag=betrag,
            storniert=bool(storniert),
        )
        for zeile, betrag, storniert in zeilen
    ]
    return tuple(sorted(erfasst, key=_reihenfolge))


def _reihenfolge(e: ErfasstesEreignis) -> tuple[bool, date, datetime, str]:
    datum = e.ereignis.datum
    return (datum is None, datum or date.min, e.erfasst_am, str(e.id))
