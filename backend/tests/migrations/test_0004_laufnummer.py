# SPDX-License-Identifier: AGPL-3.0-or-later
"""Migration 0004: Laufnummer der Bestandteile (E-35, Entscheidung vom 21.11.2026).

Die Laufnummer hält die Reihenfolge der Eingabe fest. Sie ist eine Identity-Spalte und kein
Zeitstempel, weil mehrere Bestandteile in einer Transaktion dasselbe now() hätten.
"""

import uuid
from typing import Any

import pytest
from alembic import command
from sqlalchemy import URL, Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.kern.db import erzeuge_engine
from app.kern.db.bootstrap import APP_ROLE
from tests.datenbank import (
    HEAD,
    alembic_config,
    migriere,
    neue_testdatenbank,
    roh_haushalt,
    sqlstate,
)


def katalog(engine: Engine, sql: str, **parameter: object) -> list[Any]:
    with engine.connect() as verbindung:
        return list(verbindung.execute(text(sql), parameter).all())


def bestandteil(sitzung: Session, kennung: str) -> int:
    """Bestandteil am API vorbei anlegen; liefert seine Laufnummer."""
    haushalt_id = roh_haushalt(sitzung)
    glaeubiger_id = sitzung.execute(
        text("INSERT INTO glaeubiger (haushalt_id, name) VALUES (:h, 'Muster GmbH') RETURNING id"),
        {"h": haushalt_id},
    ).scalar_one()
    akte_id = sitzung.execute(
        text("INSERT INTO akte (haushalt_id, glaeubiger_id) VALUES (:h, :g) RETURNING id"),
        {"h": haushalt_id, "g": glaeubiger_id},
    ).scalar_one()
    konto_id = sitzung.execute(
        text(
            "INSERT INTO konto (haushalt_id, kontoart, rolle, bezeichnung)"
            " VALUES (:h, 'passiv', 'verbindlichkeiten.kosten_verfahren', 'K') RETURNING id"
        ),
        {"h": haushalt_id},
    ).scalar_one()
    return sitzung.execute(
        text(
            "INSERT INTO bestandteil (akte_id, kennung, art, konto_id, ursprungsbetrag)"
            " VALUES (:a, :k, 'kosten_verfahren', :ko, 10) RETURNING laufnummer"
        ),
        {"a": akte_id, "k": kennung, "ko": konto_id},
    ).scalar_one()


def test_laufnummer_ist_identity_always(owner_engine: Engine) -> None:
    zeilen = katalog(
        owner_engine,
        "SELECT format_type(atttypid, atttypmod), attidentity, attnotnull FROM pg_attribute"
        " WHERE attrelid = 'public.bestandteil'::regclass AND attname = 'laufnummer'",
    )
    assert zeilen == [("bigint", "a", True)]


def test_laufnummer_steigt_in_der_reihenfolge_der_eingabe(session: Session) -> None:
    """Auch innerhalb einer Transaktion: zuerst erfasst, kleinere Laufnummer."""
    erste = bestandteil(session, "z_zuerst")
    zweite = bestandteil(session, "a_danach")
    assert erste < zweite


def test_laufnummer_setzt_nur_die_datenbank(session: Session) -> None:
    """GENERATED ALWAYS: Die Laufzeitrolle kann keine eigene Laufnummer vorgeben."""
    laufnummer = bestandteil(session, "kosten")
    with pytest.raises(DBAPIError) as fehler:
        session.execute(
            text(
                "INSERT INTO bestandteil (akte_id, kennung, art, konto_id, ursprungsbetrag,"
                " laufnummer) SELECT akte_id, 'neu', art, konto_id, 1, 1 FROM bestandteil"
                " WHERE laufnummer = :l"
            ),
            {"l": laufnummer},
        )
    assert sqlstate(fehler.value) == "428C9"


def test_laufnummer_nicht_aenderbar(owner_engine: Engine) -> None:
    zeilen = katalog(
        owner_engine,
        "SELECT has_column_privilege(:rolle, 'public.bestandteil', 'laufnummer', 'UPDATE')",
        rolle=APP_ROLE,
    )
    assert zeilen == [(False,)]


def test_rueckweg_ohne_bestandteile(admin_url: URL) -> None:
    with neue_testdatenbank(admin_url) as datenbank:
        owner = erzeuge_engine(datenbank.owner_url)
        try:
            with owner.begin() as verbindung:
                command.downgrade(alembic_config(verbindung), "0003")
            spalten = katalog(
                owner,
                "SELECT attname FROM pg_attribute WHERE attrelid = 'public.bestandteil'::regclass"
                " AND attname = 'laufnummer' AND NOT attisdropped",
            )
            assert spalten == []
            migriere(datenbank.owner_url)
            assert katalog(owner, "SELECT version_num FROM alembic_version") == [(HEAD,)]
        finally:
            owner.dispose()


def test_rueckweg_bricht_ab_wenn_bestandteile_existieren(admin_url: URL) -> None:
    """Die Reihenfolge der Eingabe ginge verloren; dann nicht (wie bei 0002)."""
    with neue_testdatenbank(admin_url) as datenbank:
        app = erzeuge_engine(datenbank.app_url)
        owner = erzeuge_engine(datenbank.owner_url)
        try:
            with Session(app) as sitzung:
                bestandteil(sitzung, f"k_{uuid.uuid4().hex[:6]}")
                sitzung.commit()
            with pytest.raises(DBAPIError) as fehler, owner.begin() as verbindung:
                command.downgrade(alembic_config(verbindung), "0003")
            assert sqlstate(fehler.value) == "55000"
            assert katalog(owner, "SELECT version_num FROM alembic_version") == [(HEAD,)]
        finally:
            app.dispose()
            owner.dispose()
