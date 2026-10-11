# SPDX-License-Identifier: AGPL-3.0-or-later
"""Buchen über die Python-API (Fachkonzept 4.1, 4.3, 4.4)."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.kern.db import BetragNichtSpeicherbarError
from app.kern.haushalt import lege_haushalt_an
from app.kern.ledger import (
    Buchung,
    BuchungUngueltigError,
    HaushaltUnbekanntError,
    KontoUnbekanntError,
    Posting,
    PostingEingabe,
    buche,
    lege_konto_an,
    saldo,
)
from tests.datenbank import pruefe_aufgeschobene, roh_buchung, roh_haushalt, roh_konto, roh_postings
from tests.kern.ledger.conftest import Konten, lege_konten_an

TAG = date(2024, 1, 15)


def erfasse_altlast(session: Session, konten: Konten, betrag: str = "1000.00") -> Buchung:
    """Erfassung einer Altlast (Kap. 4.3): Soll Eröffnung, Haben Hauptforderung."""
    return buche(
        session,
        haushalt_id=konten.haushalt_id,
        art="test.entstehung",
        wertstellung=TAG,
        postings=[
            PostingEingabe(konten.eroeffnung, Decimal(betrag)),
            PostingEingabe(konten.hauptforderung, -Decimal(betrag)),
        ],
        text="Erfassung",
    )


def test_erfassung_einer_altlast(session: Session, konten: Konten) -> None:
    """Soll positiv, Haben negativ (Kap. 4.1): die Hauptforderung steht im Haben."""
    buchung = erfasse_altlast(session, konten)
    pruefe_aufgeschobene(session)
    assert buchung.art == "test.entstehung"
    assert buchung.wertstellung == TAG
    assert buchung.storno_von is None
    assert saldo(session, konto_id=konten.hauptforderung, stichtag=TAG) == Decimal("-1000.00")
    assert saldo(session, konto_id=konten.eroeffnung, stichtag=TAG) == Decimal("1000.00")


def test_postings_werden_gespeichert(session: Session, konten: Konten) -> None:
    buchung = erfasse_altlast(session, konten)
    gespeichert = session.execute(
        select(Posting.konto_id, Posting.betrag).where(Posting.buchung_id == buchung.id)
    ).all()
    assert sorted((str(k), b) for k, b in gespeichert) == sorted(
        [
            (str(konten.eroeffnung), Decimal("1000.00")),
            (str(konten.hauptforderung), Decimal("-1000.00")),
        ]
    )


def test_mehrere_postings_auf_einem_konto(session: Session, konten: Konten) -> None:
    buche(
        session,
        haushalt_id=konten.haushalt_id,
        art="test.buchung",
        wertstellung=TAG,
        postings=[
            PostingEingabe(konten.eroeffnung, Decimal(5)),
            PostingEingabe(konten.eroeffnung, Decimal(5)),
            PostingEingabe(konten.hauptforderung, Decimal(-10)),
        ],
    )
    pruefe_aufgeschobene(session)
    assert saldo(session, konto_id=konten.eroeffnung, stichtag=TAG) == Decimal(10)


def test_erfasst_am_ist_der_beginn_der_transaktion(session: Session, konten: Konten) -> None:
    jetzt = session.execute(select(func.now())).scalar_one()
    buchung = erfasse_altlast(session, konten)
    assert buchung.erfasst_am == jetzt
    assert buchung.erfasst_am.utcoffset() == timedelta(0)


def test_erfasst_am_vom_client_wird_ueberschrieben(session: Session) -> None:
    """Fachkonzept 4.4: Die Datenbank setzt erfasst_am selbst."""
    haushalt_id = roh_haushalt(session)
    erfasst_am, jetzt = session.execute(
        text(
            "INSERT INTO buchung (haushalt_id, art, wertstellung, erfasst_am)"
            " VALUES (:haushalt_id, 'test.buchung', '2024-01-15', '2000-01-01 00:00+00')"
            " RETURNING erfasst_am, now()"
        ),
        {"haushalt_id": haushalt_id},
    ).one()
    assert erfasst_am == jetzt


def test_buche_committet_nicht(app_engine: Engine, session: Session, konten: Konten) -> None:
    buchung = erfasse_altlast(session, konten)
    with app_engine.connect() as andere:
        sichtbar = andere.execute(
            text("SELECT count(*) FROM buchung WHERE id = :id"), {"id": buchung.id}
        ).scalar_one()
    assert sichtbar == 0


def test_echter_commit(app_engine: Engine) -> None:
    """Ohne Rollback: Die zurückgestellten Prüfungen laufen beim COMMIT und lassen durch."""
    with Session(app_engine) as sitzung:
        konten = lege_konten_an(sitzung)
        buchung_id = erfasse_altlast(sitzung, konten).id
        sitzung.commit()
    with Session(app_engine) as sitzung:
        buchung = sitzung.get(Buchung, buchung_id)
        assert buchung is not None
        assert buchung.erfasst_am.utcoffset() == timedelta(0)
        assert saldo(sitzung, konto_id=konten.hauptforderung, stichtag=TAG) == Decimal("-1000.00")


def test_konto_eines_anderen_haushalts(session: Session, konten: Konten) -> None:
    fremd = lege_haushalt_an(session, betriebsart="einzel")
    fremdes_konto = lege_konto_an(
        session, haushalt_id=fremd.id, kontoart="passiv", rolle="test.konto", bezeichnung="fremd"
    )
    with pytest.raises(BuchungUngueltigError, match="Haushalt"):
        buche(
            session,
            haushalt_id=konten.haushalt_id,
            art="test.buchung",
            wertstellung=TAG,
            postings=[
                PostingEingabe(konten.eroeffnung, Decimal(1)),
                PostingEingabe(fremdes_konto.id, Decimal(-1)),
            ],
        )
    assert not session.new


def test_unbekanntes_konto(session: Session, konten: Konten) -> None:
    with pytest.raises(KontoUnbekanntError):
        buche(
            session,
            haushalt_id=konten.haushalt_id,
            art="test.buchung",
            wertstellung=TAG,
            postings=[
                PostingEingabe(konten.eroeffnung, Decimal(1)),
                PostingEingabe(uuid.uuid4(), Decimal(-1)),
            ],
        )


def test_unbekannter_haushalt(session: Session, konten: Konten) -> None:
    with pytest.raises(HaushaltUnbekanntError):
        buche(
            session,
            haushalt_id=uuid.uuid4(),
            art="test.buchung",
            wertstellung=TAG,
            postings=[
                PostingEingabe(konten.eroeffnung, Decimal(1)),
                PostingEingabe(konten.hauptforderung, Decimal(-1)),
            ],
        )


def test_orm_lehnt_mehr_als_vier_nachkommastellen_ab(session: Session, konten: Konten) -> None:
    """Auch am API vorbei über das ORM rundet nichts still (CLAUDE.md, Geld)."""
    buchung = Buchung(haushalt_id=konten.haushalt_id, art="test.buchung", wertstellung=TAG)
    session.add(buchung)
    session.flush()
    session.add(
        Posting(buchung_id=buchung.id, konto_id=konten.eroeffnung, betrag=Decimal("1.00005"))
    )
    with pytest.raises(BetragNichtSpeicherbarError):
        session.flush()


def test_fehlermeldung_enthaelt_keine_gebundenen_werte(app_engine: Engine) -> None:
    """hide_parameters: Beträge erscheinen nicht in der Meldung (CLAUDE.md, Sicherheit)."""
    with Session(app_engine) as sitzung:
        haushalt_id = roh_haushalt(sitzung)
        konto_a, konto_b = roh_konto(sitzung, haushalt_id), roh_konto(sitzung, haushalt_id)
        buchung_id = roh_buchung(sitzung, haushalt_id)
        roh_postings(sitzung, buchung_id, [(konto_a, "10"), (konto_b, "-10")])
        sitzung.commit()
    with Session(app_engine) as sitzung, pytest.raises(IntegrityError) as fehler:
        roh_postings(sitzung, buchung_id, [(konto_a, "4711.0815")])
    assert "4711" not in str(fehler.value)
