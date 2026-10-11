# SPDX-License-Identifier: AGPL-3.0-or-later
"""Haushalt und Konten anlegen (Fachkonzept 4.2, 4.4)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.kern.haushalt import Haushalt, lege_haushalt_an
from app.kern.ledger import HaushaltUnbekanntError, KontoUngueltigError, lege_konto_an
from tests.datenbank import constraint_name, roh_haushalt, sqlstate


def test_haushalt_anlegen(session: Session) -> None:
    haushalt = lege_haushalt_an(session, betriebsart="haushalt_gemeinsam")
    assert isinstance(haushalt.id, uuid.UUID)
    assert session.get(Haushalt, haushalt.id) is haushalt


def test_unbekannte_betriebsart(session: Session) -> None:
    with pytest.raises(ValueError, match="Betriebsart"):
        lege_haushalt_an(session, betriebsart="gemeinsam")  # pyright: ignore[reportArgumentType]


def test_konto_anlegen(session: Session) -> None:
    haushalt = lege_haushalt_an(session, betriebsart="einzel")
    konto = lege_konto_an(
        session,
        haushalt_id=haushalt.id,
        kontoart="eigenkapital",
        rolle="kern.externe_mittel",
        bezeichnung="Externe Mittel",
    )
    assert isinstance(konto.id, uuid.UUID)
    assert konto.waehrung == "EUR"
    assert konto.haushalt_id == haushalt.id


def test_konto_in_unbekanntem_haushalt(session: Session) -> None:
    with pytest.raises(HaushaltUnbekanntError):
        lege_konto_an(
            session,
            haushalt_id=uuid.uuid4(),
            kontoart="passiv",
            rolle="test.konto",
            bezeichnung="Testkonto",
        )


def test_ungueltige_rolle_wird_vor_der_datenbank_abgelehnt(session: Session) -> None:
    haushalt = lege_haushalt_an(session, betriebsart="einzel")
    with pytest.raises(KontoUngueltigError):
        lege_konto_an(
            session,
            haushalt_id=haushalt.id,
            kontoart="passiv",
            rolle="hauptforderung",
            bezeichnung="ohne Präfix",
        )
    assert not session.new


# --- Dieselben Regeln in der Datenbank (Roh-SQL am API vorbei) -------------------------


UNGUELTIGE_KONTOARTEN = ["Passiv", "bank", "", "passiv "]
UNGUELTIGE_ROLLEN = [
    "hauptforderung",
    "Kern.x",
    "kern.",
    ".x",
    "a.b.c",
    "kern.externe-mittel",
    "kern.x1",
    "kern.gläubiger",
    "kern.x\n",
]


@pytest.mark.parametrize(
    ("spalten", "constraint"),
    [
        *[
            ({"kontoart": kontoart, "rolle": "test.konto", "waehrung": "EUR"}, "ck_konto_kontoart")
            for kontoart in UNGUELTIGE_KONTOARTEN
        ],
        *[
            ({"kontoart": "passiv", "rolle": rolle, "waehrung": "EUR"}, "ck_konto_rolle_format")
            for rolle in UNGUELTIGE_ROLLEN
        ],
        ({"kontoart": "passiv", "rolle": "test.konto", "waehrung": "USD"}, "ck_konto_nur_eur"),
    ],
)
def test_checks_auf_konto(session: Session, spalten: dict[str, str], constraint: str) -> None:
    haushalt_id = roh_haushalt(session)
    with pytest.raises(IntegrityError) as fehler:
        session.execute(
            text(
                "INSERT INTO konto (haushalt_id, kontoart, rolle, waehrung, bezeichnung)"
                " VALUES (:haushalt_id, :kontoart, :rolle, :waehrung, 'Testkonto')"
            ),
            {"haushalt_id": haushalt_id, **spalten},
        )
    assert sqlstate(fehler.value) == "23514"
    assert constraint_name(fehler.value) == constraint


def test_check_auf_betriebsart(session: Session) -> None:
    with pytest.raises(IntegrityError) as fehler:
        session.execute(text("INSERT INTO haushalt (betriebsart) VALUES ('gemeinsam')"))
    assert constraint_name(fehler.value) == "ck_haushalt_betriebsart"


def test_waehrung_ist_standardmaessig_eur(session: Session) -> None:
    haushalt_id = roh_haushalt(session)
    waehrung = session.execute(
        text(
            "INSERT INTO konto (haushalt_id, kontoart, rolle, bezeichnung)"
            " VALUES (:haushalt_id, 'passiv', 'test.konto', 'Testkonto') RETURNING waehrung"
        ),
        {"haushalt_id": haushalt_id},
    ).scalar_one()
    assert waehrung == "EUR"
