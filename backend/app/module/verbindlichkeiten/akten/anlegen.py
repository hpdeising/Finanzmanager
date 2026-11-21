# SPDX-License-Identifier: AGPL-3.0-or-later
"""Akten, Bestandteile, Ereignisse und Zahlungen speichern (Fachkonzept Kap. 4.2, 4.3, 4.5).

Gespeichert wird mit den Konten und Buchungen des Kontenrahmens:

- Eine Akte bekommt ein Zahlungskonto; beim ersten Mal legt das Modul die Konten des
  Haushalts an (Eröffnung Altlasten, Zinsaufwand, Kostenaufwand) und, falls es fehlt, das
  Konto Externe Mittel des Kerns (Kap. 4.2).
- Ein Bestandteil bekommt ein Passivkonto, jede verzinsliche Zinsregel ein Zinskonto. Sein
  Ursprungsbetrag wird gebucht: als Erfassung einer Altlast gegen Eröffnung Altlasten, neue
  Vollstreckungskosten gegen Kostenaufwand (Kap. 4.3).
- Eine Zahlung ist eine Buchung auf dem Zahlungskonto gegen Externe Mittel und ein Ereignis
  ``zahlung`` mit Verweis auf sie (Kap. 4.3, 4.5). Ereignisdatum und Wertstellung sind gleich
  (P-18 offen). Korrigiert wird durch Storno, nie durch Ändern oder Löschen (Kap. 4.1).

Alle Funktionen schreiben ohne Commit.
"""

import uuid
from datetime import date
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.kern.haushalt import Haushalt
from app.kern.ledger import (
    EXTERNE_MITTEL,
    Konto,
    Kontoart,
    PostingEingabe,
    buche,
    lege_konto_an,
    storniere,
)
from app.kern.zeit import tag_von
from app.module.verbindlichkeiten.akten.fehler import (
    AkteUnbekanntError,
    EreignisUnbekanntError,
    GlaeubigerUnbekanntError,
)
from app.module.verbindlichkeiten.db import (
    RICHTUNGEN,
    Akte,
    AkteKonto,
    AkteTeilungstag,
    BestandteilZeile,
    EreignisZeile,
    Glaeubiger,
    ZinsregelZeile,
)
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Bestandteil,
    EingabeUngueltigError,
    Ereignis,
    Ereignistyp,
    Gruppe,
    Zahlung,
)

ROLLE_ZAHLUNGEN: Final = "verbindlichkeiten.zahlungen"
ROLLE_ZINSEN: Final = "verbindlichkeiten.zinsen"
ART_ENTSTEHUNG: Final = "verbindlichkeiten.entstehung"
ART_KOSTEN: Final = "verbindlichkeiten.kosten"
ART_ZAHLUNG: Final = "verbindlichkeiten.zahlung"

# Konten je Haushalt (Kap. 4.2): Rolle, Kontoart, Bezeichnung.
EROEFFNUNG: Final[tuple[str, Kontoart, str]] = (
    "verbindlichkeiten.eroeffnung",
    "eigenkapital",
    "Eröffnung Altlasten",
)
ZINSAUFWAND: Final[tuple[str, Kontoart, str]] = (
    "verbindlichkeiten.zinsaufwand",
    "aufwand",
    "Zinsaufwand",
)
KOSTENAUFWAND: Final[tuple[str, Kontoart, str]] = (
    "verbindlichkeiten.kostenaufwand",
    "aufwand",
    "Kostenaufwand",
)
EXTERN: Final[tuple[str, Kontoart, str]] = (EXTERNE_MITTEL, "eigenkapital", "Externe Mittel")

# Namensraum der Advisory-Sperre beim Anlegen der Konten eines Haushalts: 0x56424B4F, „VBKO“.
_NAMENSRAUM: Final = 1447185231


def lege_glaeubiger_an(
    session: Session,
    *,
    haushalt_id: uuid.UUID,
    name: str,
    anschrift: str | None = None,
    iban: str | None = None,
    vertreter: str | None = None,
    kontakt: str | None = None,
) -> uuid.UUID:
    """Gläubiger anlegen (Kap. 4.5)."""
    if not name.strip():
        msg = "Ein Gläubiger braucht einen Namen."
        raise EingabeUngueltigError(msg)
    glaeubiger = Glaeubiger(
        haushalt_id=haushalt_id,
        name=name,
        anschrift=anschrift,
        iban=iban,
        vertreter=vertreter,
        kontakt=kontakt,
    )
    session.add(glaeubiger)
    session.flush()
    return glaeubiger.id


def lege_akte_an(
    session: Session,
    *,
    haushalt_id: uuid.UUID,
    glaeubiger_id: uuid.UUID,
    parameter: Aktenparameter | None = None,
    verbraucherdarlehen: bool = False,
    aktenzeichen_glaeubiger: str | None = None,
    richtung: str = "verbindlichkeit",
) -> uuid.UUID:
    """Akte mit Zahlungskonto anlegen; Voreinstellungen der Parameter wie in Kap. 5.1.

    Raises:
        GlaeubigerUnbekanntError: wenn der Gläubiger nicht zum Haushalt gehört.
    """
    parameter = parameter or Aktenparameter()
    if richtung not in RICHTUNGEN:
        msg = f"Unbekannte Richtung; zulässig sind {', '.join(RICHTUNGEN)}."
        raise EingabeUngueltigError(msg)
    glaeubiger = session.get(Glaeubiger, glaeubiger_id)
    if glaeubiger is None or glaeubiger.haushalt_id != haushalt_id:
        raise GlaeubigerUnbekanntError(str(glaeubiger_id))
    _konten_des_haushalts(session, haushalt_id)
    akte = Akte(
        haushalt_id=haushalt_id,
        glaeubiger_id=glaeubiger_id,
        aktenzeichen_glaeubiger=aktenzeichen_glaeubiger,
        richtung=richtung,
        verbraucherdarlehen=verbraucherdarlehen,
        anrechnung=parameter.anrechnung.value,
        reihenfolge=[g.value for g in parameter.reihenfolge] if parameter.reihenfolge else None,
        tageszaehlung=parameter.tageszaehlung.value,
        zinsbeginn=parameter.zinsbeginn.value,
        zahltag=parameter.zahltag.value,
        teilung=parameter.teilung.value,
    )
    session.add(akte)
    session.flush()
    session.add_all(AkteTeilungstag(akte_id=akte.id, tag=tag) for tag in parameter.teilungstage)
    _verknuepfe(session, akte, ROLLE_ZAHLUNGEN, "passiv", "Zahlungen")
    return akte.id


def lege_bestandteil_an(
    session: Session, *, akte_id: uuid.UUID, bestandteil: Bestandteil
) -> uuid.UUID:
    """Bestandteil mit Konto, Zinsregeln und Buchung seines Ursprungsbetrags anlegen.

    Gebucht wird nach Kap. 4.3 (Entscheidung vom 21.11.2026):

    - Kosten, die nach dem Tag der Eröffnung der Akte entstehen, sind neue Kosten:
      ``verbindlichkeiten.kosten``, Soll Kostenaufwand, Wertstellung ``entstanden_am``.
    - Alles andere ist Erfassung einer Altlast: ``verbindlichkeiten.entstehung``, Soll
      Eröffnung Altlasten, Wertstellung ``entstanden_am`` oder, ohne diesen Tag, der Tag der
      Eröffnung. Dazu gehören Kosten vom Tag der Eröffnung oder davor, Kosten ohne
      ``entstanden_am`` sowie Hauptforderung und Zinsen.

    Raises:
        AkteUnbekanntError: bei unbekannter Akte.
        EingabeUngueltigError: bei doppelter Kennung.
    """
    akte = _akte(session, akte_id)
    eroeffnet = tag_von(akte.angelegt_am)
    vorhanden = session.scalar(
        select(BestandteilZeile.id).where(
            BestandteilZeile.akte_id == akte_id, BestandteilZeile.kennung == bestandteil.kennung
        )
    )
    if vorhanden is not None:
        msg = "Die Kennung gibt es in dieser Akte schon."
        raise EingabeUngueltigError(msg)
    konto = _verknuepfe(
        session, akte, f"verbindlichkeiten.{bestandteil.art.value}", "passiv", bestandteil.kennung
    )
    zeile = BestandteilZeile(
        akte_id=akte_id,
        kennung=bestandteil.kennung,
        art=bestandteil.art.value,
        konto_id=konto.id,
        ursprungsbetrag=bestandteil.betrag,
        entstanden_am=bestandteil.entstanden_am,
        faellig_am=bestandteil.faellig_am,
        kenntnis_am=bestandteil.kenntnis_am,
    )
    session.add(zeile)
    session.flush()
    for regel in bestandteil.zinsregeln:
        zinskonto = (
            _verknuepfe(session, akte, ROLLE_ZINSEN, "passiv", f"{bestandteil.kennung}: Zinsen")
            if regel.typ.verzinslich
            else None
        )
        session.add(
            ZinsregelZeile(
                bestandteil_id=zeile.id,
                typ=regel.typ.value,
                aufschlag=regel.aufschlag,
                satz=regel.satz,
                ab=regel.ab,
                bis=regel.bis,
                konto_id=zinskonto.id if zinskonto else None,
            )
        )
    neue_kosten = (
        bestandteil.art.gruppe is Gruppe.KOSTEN
        and bestandteil.entstanden_am is not None
        and bestandteil.entstanden_am > eroeffnet
    )
    gegen = _konto_mit_rolle(
        session, akte.haushalt_id, (KOSTENAUFWAND if neue_kosten else EROEFFNUNG)[0]
    )
    buche(
        session,
        haushalt_id=akte.haushalt_id,
        art=ART_KOSTEN if neue_kosten else ART_ENTSTEHUNG,
        wertstellung=bestandteil.entstanden_am or eroeffnet,
        postings=[
            PostingEingabe(gegen.id, bestandteil.betrag),
            PostingEingabe(konto.id, -bestandteil.betrag),
        ],
    )
    session.flush()
    return zeile.id


def erfasse_ereignis(session: Session, *, akte_id: uuid.UUID, ereignis: Ereignis) -> uuid.UUID:
    """Ereignis ohne Buchung erfassen (Kap. 4.5); Zahlungen über ``erfasse_zahlung``.

    Raises:
        AkteUnbekanntError: bei unbekannter Akte.
        EingabeUngueltigError: bei einem Ereignis ``zahlung``.
    """
    _akte(session, akte_id)
    if ereignis.typ is Ereignistyp.ZAHLUNG:
        msg = "Eine Zahlung entsteht mit ihrer Buchung über erfasse_zahlung."
        raise EingabeUngueltigError(msg)
    zeile = EreignisZeile(
        akte_id=akte_id, typ=ereignis.typ.value, datum=ereignis.datum, details=details(ereignis)
    )
    session.add(zeile)
    session.flush()
    return zeile.id


def erfasse_zahlung(session: Session, *, akte_id: uuid.UUID, zahlung: Zahlung) -> uuid.UUID:
    """Zahlung buchen und als Ereignis ``zahlung`` erfassen; liefert die ID des Ereignisses.

    Buchung ``verbindlichkeiten.zahlung``: Soll Zahlungen, Haben Externe Mittel (Kap. 4.3).
    Das Ereignis trägt die Wertstellung als Datum.
    """
    akte = _akte(session, akte_id)
    zahlungskonto = _zahlungskonto(session, akte_id)
    extern = _konto_mit_rolle(session, akte.haushalt_id, EXTERN[0])
    buchung = buche(
        session,
        haushalt_id=akte.haushalt_id,
        art=ART_ZAHLUNG,
        wertstellung=zahlung.datum,
        postings=[
            PostingEingabe(zahlungskonto.id, zahlung.betrag),
            PostingEingabe(extern.id, -zahlung.betrag),
        ],
    )
    zeile = EreignisZeile(
        akte_id=akte_id, typ=Ereignistyp.ZAHLUNG.value, datum=zahlung.datum, buchung_id=buchung.id
    )
    session.add(zeile)
    session.flush()
    return zeile.id


def storniere_zahlung(session: Session, *, akte_id: uuid.UUID, ereignis_id: uuid.UUID) -> None:
    """Buchung einer falsch erfassten Zahlung stornieren (Kap. 4.1, E-18, E-26).

    Danach gilt die Zahlung als nie geschehen; das Ereignis bleibt mit seiner Buchung erhalten.

    Raises:
        EreignisUnbekanntError: wenn das Ereignis nicht zur Akte gehört.
        EingabeUngueltigError: wenn das Ereignis keine Zahlung ist.
        StornoNichtMoeglichError: wenn die Buchung schon storniert ist.
    """
    zeile = _ereignis(session, akte_id, ereignis_id)
    if zeile.buchung_id is None:
        msg = "Storniert wird nur eine Zahlung."
        raise EingabeUngueltigError(msg)
    storniere(session, buchung_id=zeile.buchung_id)
    session.flush()


def loesche_ereignis(session: Session, *, akte_id: uuid.UUID, ereignis_id: uuid.UUID) -> None:
    """Falsch erfasstes Ereignis ohne Buchung löschen; eine Zahlung wird storniert.

    Raises:
        EreignisUnbekanntError: wenn das Ereignis nicht zur Akte gehört.
        EingabeUngueltigError: bei einer Zahlung.
    """
    zeile = _ereignis(session, akte_id, ereignis_id)
    if zeile.buchung_id is not None:
        msg = "Eine Zahlung wird nicht gelöscht, sondern storniert (Kap. 4.1)."
        raise EingabeUngueltigError(msg)
    session.delete(zeile)
    session.flush()


def details(ereignis: Ereignis) -> dict[str, Any]:
    """Angaben eines Ereignisses neben Typ und Datum als JSON-Objekt (Kap. 4.5)."""
    werte: dict[str, Any] = {}
    if ereignis.versaeumnisurteil:
        werte["versaeumnisurteil"] = True
    if ereignis.bekanntgabe_am is not None:
        werte["bekanntgabe_am"] = ereignis.bekanntgabe_am.isoformat()
    if ereignis.gericht_land is not None:
        werte["gericht_land"] = ereignis.gericht_land
    if ereignis.zurueckgegeben:
        werte["zurueckgegeben"] = True
    return werte


def ereignis_aus(typ: str, datum: date | None, werte: dict[str, Any]) -> Ereignis:
    """Ereignis aus Typ, Datum und Details.

    Raises:
        ValueError: bei einem unbekannten Typ oder ungültigen Details.
    """
    bekanntgabe = werte.get("bekanntgabe_am")
    return Ereignis(
        Ereignistyp(typ),
        datum,
        versaeumnisurteil=bool(werte.get("versaeumnisurteil", False)),
        bekanntgabe_am=date.fromisoformat(bekanntgabe) if bekanntgabe else None,
        gericht_land=werte.get("gericht_land"),
        zurueckgegeben=bool(werte.get("zurueckgegeben", False)),
    )


# --- Hilfen -------------------------------------------------------------------------------------


def _akte(session: Session, akte_id: uuid.UUID) -> Akte:
    akte = session.get(Akte, akte_id)
    if akte is None:
        raise AkteUnbekanntError(str(akte_id))
    return akte


def _ereignis(session: Session, akte_id: uuid.UUID, ereignis_id: uuid.UUID) -> EreignisZeile:
    zeile = session.get(EreignisZeile, ereignis_id)
    if zeile is None or zeile.akte_id != akte_id:
        raise EreignisUnbekanntError(str(ereignis_id))
    return zeile


def _konten_des_haushalts(session: Session, haushalt_id: uuid.UUID) -> None:
    """Konten je Haushalt anlegen, die noch fehlen (Kap. 4.2).

    Eine Advisory-Sperre je Haushalt verhindert, dass zwei gleichzeitige erste Akten sie doppelt
    anlegen; sie gilt bis zum Ende der Transaktion.
    """
    if session.get(Haushalt, haushalt_id) is None:
        msg = f"Unbekannter Haushalt {haushalt_id}."
        raise EingabeUngueltigError(msg)
    session.execute(
        select(func.pg_advisory_xact_lock(_NAMENSRAUM, func.hashtext(str(haushalt_id))))
    )
    for rolle, kontoart, bezeichnung in (EROEFFNUNG, ZINSAUFWAND, KOSTENAUFWAND, EXTERN):
        if _finde_konto(session, haushalt_id, rolle) is None:
            lege_konto_an(
                session,
                haushalt_id=haushalt_id,
                kontoart=kontoart,
                rolle=rolle,
                bezeichnung=bezeichnung,
            )


def _finde_konto(session: Session, haushalt_id: uuid.UUID, rolle: str) -> Konto | None:
    return session.scalars(
        select(Konto)
        .where(Konto.haushalt_id == haushalt_id, Konto.rolle == rolle)
        .order_by(Konto.id)
    ).first()


def _konto_mit_rolle(session: Session, haushalt_id: uuid.UUID, rolle: str) -> Konto:
    konto = _finde_konto(session, haushalt_id, rolle)
    if konto is None:
        msg = f"Konto {rolle} fehlt im Haushalt."
        raise LookupError(msg)
    return konto


def _verknuepfe(
    session: Session, akte: Akte, rolle: str, kontoart: Kontoart, bezeichnung: str
) -> Konto:
    konto = lege_konto_an(
        session,
        haushalt_id=akte.haushalt_id,
        kontoart=kontoart,
        rolle=rolle,
        bezeichnung=bezeichnung,
    )
    session.add(AkteKonto(akte_id=akte.id, konto_id=konto.id))
    session.flush()
    return konto


def zahlungskonto_id(session: Session, akte_id: uuid.UUID) -> uuid.UUID:
    return _zahlungskonto(session, akte_id).id


def _zahlungskonto(session: Session, akte_id: uuid.UUID) -> Konto:
    return session.scalars(
        select(Konto)
        .join(AkteKonto, AkteKonto.konto_id == Konto.id)
        .where(AkteKonto.akte_id == akte_id, Konto.rolle == ROLLE_ZAHLUNGEN)
    ).one()
