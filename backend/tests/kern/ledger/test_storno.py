# SPDX-License-Identifier: AGPL-3.0-or-later
"""Storno über die Python-API (Fachkonzept 4.1, 4.4, E-18)."""

import uuid
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kern.ledger import (
    STORNO,
    Buchung,
    BuchungUnbekanntError,
    Posting,
    PostingEingabe,
    StornoNichtMoeglichError,
    buche,
    saldo,
    storniere,
)
from tests.datenbank import pruefe_aufgeschobene
from tests.kern.ledger.conftest import Konten

TAG = date(2024, 3, 1)


def bewegung(
    session: Session,
    konten: Konten,
    betrag: str,
    wertstellung: date = TAG,
    art: str = "test.zahlung",
) -> Buchung:
    """Zahlung (Kap. 4.3): Soll Hauptforderung, Haben Eröffnung als Platzhalter für Mittel."""
    return buche(
        session,
        haushalt_id=konten.haushalt_id,
        art=art,
        wertstellung=wertstellung,
        postings=[
            PostingEingabe(konten.hauptforderung, Decimal(betrag)),
            PostingEingabe(konten.eroeffnung, -Decimal(betrag)),
        ],
    )


def postings_von(session: Session, buchung_id: uuid.UUID) -> Counter[tuple[uuid.UUID, Decimal]]:
    zeilen = session.execute(
        select(Posting.konto_id, Posting.betrag).where(Posting.buchung_id == buchung_id)
    ).all()
    return Counter((konto_id, betrag) for konto_id, betrag in zeilen)


def test_storno_negiert_die_postings(session: Session, konten: Konten) -> None:
    original = bewegung(session, konten, "100.00")
    storno = storniere(session, buchung_id=original.id, text="falsch erfasst")
    pruefe_aufgeschobene(session)
    assert storno.art == STORNO
    assert storno.storno_von == original.id
    assert storno.text == "falsch erfasst"
    negiert = Counter({(k, -b): n for (k, b), n in postings_von(session, original.id).items()})
    assert postings_von(session, storno.id) == negiert


def test_storno_hat_die_wertstellung_des_originals(session: Session, konten: Konten) -> None:
    """E-18: Der Zeitpunkt der Korrektur steht in erfasst_am, nicht in der Wertstellung."""
    original = bewegung(session, konten, "100.00", wertstellung=date(2023, 6, 30))
    storno = storniere(session, buchung_id=original.id)
    assert storno.wertstellung == date(2023, 6, 30)


@pytest.mark.parametrize("abstand", [-1, 0, 1, 400])
def test_storno_stellt_den_saldo_zu_jedem_stichtag_wieder_her(
    session: Session, konten: Konten, abstand: int
) -> None:
    stichtag = TAG + timedelta(days=abstand)
    vorher = saldo(session, konto_id=konten.hauptforderung, stichtag=stichtag)
    original = bewegung(session, konten, "250.50")
    storniere(session, buchung_id=original.id)
    pruefe_aufgeschobene(session)
    assert saldo(session, konto_id=konten.hauptforderung, stichtag=stichtag) == vorher


def test_storno_plus_neubuchung_wie_die_korrigierte_buchung(
    session: Session, konten: Konten
) -> None:
    """Fachkonzept Kap. 12, an einem Beispiel; die Eigenschaft prüft test_ledger_eigenschaften."""
    falsch = bewegung(session, konten, "90.00")
    storniere(session, buchung_id=falsch.id)
    bewegung(session, konten, "100.00")
    pruefe_aufgeschobene(session)
    for stichtag in (TAG - timedelta(days=1), TAG, TAG + timedelta(days=1)):
        erwartet = Decimal("100.00") if stichtag >= TAG else Decimal(0)
        assert saldo(session, konto_id=konten.hauptforderung, stichtag=stichtag) == erwartet


def test_zweites_storno(session: Session, konten: Konten) -> None:
    original = bewegung(session, konten, "10")
    storniere(session, buchung_id=original.id)
    with pytest.raises(StornoNichtMoeglichError, match="bereits storniert"):
        storniere(session, buchung_id=original.id)


def test_kein_storno_eines_stornos(session: Session, konten: Konten) -> None:
    original = bewegung(session, konten, "10")
    storno = storniere(session, buchung_id=original.id)
    with pytest.raises(StornoNichtMoeglichError, match="Storno"):
        storniere(session, buchung_id=storno.id)


def test_unbekannte_buchung(session: Session) -> None:
    with pytest.raises(BuchungUnbekanntError):
        storniere(session, buchung_id=uuid.uuid4())
