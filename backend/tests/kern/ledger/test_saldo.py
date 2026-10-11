# SPDX-License-Identifier: AGPL-3.0-or-later
"""Saldo zum Stichtag (Fachkonzept 4.1): Summe der Postings mit Wertstellung bis
einschließlich Stichtag, exakt und ungerundet."""

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.kern.ledger import KontoUnbekanntError, PostingEingabe, buche, saldo
from tests.kern.ledger.conftest import Konten


def buche_betrag(session: Session, konten: Konten, betrag: str, wertstellung: date) -> None:
    buche(
        session,
        haushalt_id=konten.haushalt_id,
        art="test.buchung",
        wertstellung=wertstellung,
        postings=[
            PostingEingabe(konten.zinsaufwand, Decimal(betrag)),
            PostingEingabe(konten.hauptforderung, -Decimal(betrag)),
        ],
    )


def test_ohne_postings_ist_der_saldo_null(session: Session, konten: Konten) -> None:
    ergebnis = saldo(session, konto_id=konten.zinsaufwand, stichtag=date(2024, 1, 1))
    assert isinstance(ergebnis, Decimal)
    assert ergebnis == 0


def test_stichtag_ist_eingeschlossen(session: Session, konten: Konten) -> None:
    buche_betrag(session, konten, "12.34", date(2024, 2, 29))
    assert saldo(session, konto_id=konten.zinsaufwand, stichtag=date(2024, 2, 28)) == 0
    assert saldo(session, konto_id=konten.zinsaufwand, stichtag=date(2024, 2, 29)) == Decimal(
        "12.34"
    )


def test_spaet_erfasste_buchung_wirkt_zur_wertstellung(session: Session, konten: Konten) -> None:
    buche_betrag(session, konten, "10", date(2024, 5, 1))
    buche_betrag(session, konten, "1", date(2024, 1, 1))
    assert saldo(session, konto_id=konten.zinsaufwand, stichtag=date(2024, 3, 1)) == Decimal(1)
    assert saldo(session, konto_id=konten.zinsaufwand, stichtag=date(2024, 5, 1)) == Decimal(11)


def test_saldo_ist_exakt_und_ungerundet(session: Session, konten: Konten) -> None:
    for betrag in ("0.0001", "0.0002", "0.0003"):
        buche_betrag(session, konten, betrag, date(2024, 1, 1))
    assert saldo(session, konto_id=konten.zinsaufwand, stichtag=date(2024, 1, 1)) == Decimal(
        "0.0006"
    )


def test_unbekanntes_konto(session: Session) -> None:
    with pytest.raises(KontoUnbekanntError):
        saldo(session, konto_id=uuid.uuid4(), stichtag=date(2024, 1, 1))


def test_stichtag_ist_ein_datum(session: Session, konten: Konten) -> None:
    with pytest.raises(TypeError, match="Stichtag"):
        saldo(
            session,
            konto_id=konten.zinsaufwand,
            stichtag=datetime(2024, 1, 1, 12, 0),  # noqa: DTZ001
        )
