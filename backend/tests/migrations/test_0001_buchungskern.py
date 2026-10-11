# SPDX-License-Identifier: AGPL-3.0-or-later
"""Migration 0001: Tabellen, Trigger, Rechte und Rückweg (Fachkonzept 4.4, 11.1).

Alembic vergleicht Trigger, Funktionen und Rechte nicht. Deshalb prüfen die Tests den
Katalog von PostgreSQL direkt. Tests, die migrieren oder zurückmigrieren, bekommen eine
eigene, frische Datenbank.
"""

from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import URL, Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.kern.db import Basis, erzeuge_engine
from app.kern.db.bootstrap import APP_ROLE, MIGRATION_URL_VARIABLE
from tests.datenbank import (
    BACKEND,
    alembic_config,
    migriere,
    neue_testdatenbank,
    roh_buchung,
    roh_haushalt,
    roh_konto,
    roh_postings,
    sqlstate,
)

TABELLEN = ("haushalt", "konto", "buchung", "posting")

TRIGGER = {
    ("buchung", "buchung_pruefen"),
    ("buchung", "buchung_vor_insert"),
    ("buchung", "buchung_merken"),
    ("buchung", "buchung_unveraenderlich"),
    ("posting", "posting_pruefen"),
    ("posting", "posting_vor_insert"),
    ("posting", "posting_unveraenderlich"),
    ("konto", "konto_vor_update"),
}

CONSTRAINTS = {
    "pk_haushalt",
    "ck_haushalt_betriebsart",
    "pk_konto",
    "fk_konto_haushalt_id_haushalt",
    "ck_konto_kontoart",
    "ck_konto_rolle_format",
    "ck_konto_nur_eur",
    "pk_buchung",
    "fk_buchung_haushalt_id_haushalt",
    "fk_buchung_storno_von_buchung",
    "uq_buchung_storno_von",
    "ck_buchung_art_format",
    "ck_buchung_storno_art",
    "ck_buchung_storno_nicht_selbst",
    "pk_posting",
    "fk_posting_buchung_id_buchung",
    "fk_posting_konto_id_konto",
    "ck_posting_betrag_ungleich_null",
}


def katalog(engine: Engine, sql: str, **parameter: str) -> list[Any]:
    with engine.connect() as verbindung:
        return list(verbindung.execute(text(sql), parameter).all())


def test_stand_ist_0001(owner_engine: Engine) -> None:
    assert katalog(owner_engine, "SELECT version_num FROM alembic_version") == [("0001",)]


def test_modelle_und_migration_stimmen_ueberein(owner_engine: Engine) -> None:
    """Spalten, Typen, Defaults, Indizes, Fremdschlüssel und Namen der CHECKs."""
    with owner_engine.connect() as verbindung:
        kontext = MigrationContext.configure(
            verbindung,
            opts={
                "compare_type": True,
                "compare_server_default": True,
                "autogenerate_plugins": [
                    "alembic.autogenerate.*",
                    "alembic.autogenerate.checkconstraint_byname",
                ],
            },
        )
        unterschiede = compare_metadata(kontext, Basis.metadata)
    assert unterschiede == []


def test_trigger_sind_angelegt_und_immer_aktiv(owner_engine: Engine) -> None:
    """tgenabled = 'A': Die Trigger feuern auch bei session_replication_role = replica."""
    zeilen = katalog(
        owner_engine,
        "SELECT c.relname, t.tgname, t.tgenabled FROM pg_trigger AS t"
        " JOIN pg_class AS c ON c.oid = t.tgrelid"
        " WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::regnamespace",
    )
    assert {(tabelle, name) for tabelle, name, _ in zeilen} == TRIGGER
    assert {aktiv for _, _, aktiv in zeilen} == {"A"}


@pytest.mark.parametrize("name", ["buchung_pruefen", "posting_pruefen"])
def test_pruefungen_sind_zurueckgestellt(owner_engine: Engine, name: str) -> None:
    zeilen = katalog(
        owner_engine,
        "SELECT tgdeferrable, tginitdeferred FROM pg_trigger"
        " WHERE tgname = :name AND tgconstraint <> 0",
        name=name,
    )
    assert zeilen == [(True, True)]


def test_constraint_namen(owner_engine: Engine) -> None:
    zeilen = katalog(
        owner_engine,
        "SELECT conname FROM pg_constraint"
        " WHERE conrelid IN ('public.haushalt'::regclass, 'public.konto'::regclass,"
        " 'public.buchung'::regclass, 'public.posting'::regclass) AND contype <> 't'",
    )
    assert {name for (name,) in zeilen} == CONSTRAINTS


def test_funktionen_mit_festem_suchpfad(owner_engine: Engine) -> None:
    """Fester search_path: keine gleichnamige temporäre Tabelle schiebt sich davor."""
    zeilen = katalog(
        owner_engine,
        "SELECT proname, proconfig FROM pg_proc"
        " WHERE pronamespace = 'public'::regnamespace AND proname LIKE 'ledger\\_%'",
    )
    assert len(zeilen) >= 5
    for name, konfiguration in zeilen:
        assert konfiguration == ["search_path=pg_catalog, pg_temp"], name


@pytest.mark.parametrize("tabelle", TABELLEN)
def test_rechte_der_laufzeitrolle(owner_engine: Engine, tabelle: str) -> None:
    zeilen = katalog(
        owner_engine,
        "SELECT privilege_type FROM information_schema.role_table_grants"
        " WHERE grantee = :rolle AND table_name = :tabelle",
        rolle=APP_ROLE,
        tabelle=tabelle,
    )
    assert {recht for (recht,) in zeilen} == {"SELECT", "INSERT"}


def test_rueckweg_und_erneuter_aufbau(admin_url: URL) -> None:
    with neue_testdatenbank(admin_url) as datenbank:
        engine = erzeuge_engine(datenbank.owner_url)
        try:
            with engine.begin() as verbindung:
                command.downgrade(alembic_config(verbindung), "base")
            uebrig = katalog(
                engine,
                "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace"
                " AND relkind = 'r' UNION ALL SELECT proname FROM pg_proc"
                " WHERE pronamespace = 'public'::regnamespace",
            )
            assert {name for (name,) in uebrig} == {"alembic_version"}
            migriere(datenbank.owner_url)
            assert katalog(engine, "SELECT version_num FROM alembic_version") == [("0001",)]
        finally:
            engine.dispose()


def test_rueckweg_bricht_ab_wenn_buchungen_existieren(admin_url: URL) -> None:
    """DROP TABLE ist weder DELETE noch TRUNCATE; deshalb schützt der Rückweg selbst."""
    with neue_testdatenbank(admin_url) as datenbank:
        app = erzeuge_engine(datenbank.app_url)
        owner = erzeuge_engine(datenbank.owner_url)
        try:
            with Session(app) as sitzung:
                haushalt_id = roh_haushalt(sitzung)
                konto_a, konto_b = roh_konto(sitzung, haushalt_id), roh_konto(sitzung, haushalt_id)
                buchung_id = roh_buchung(sitzung, haushalt_id)
                roh_postings(sitzung, buchung_id, [(konto_a, "1"), (konto_b, "-1")])
                sitzung.commit()
            with pytest.raises(DBAPIError) as fehler, owner.begin() as verbindung:
                command.downgrade(alembic_config(verbindung), "base")
            assert sqlstate(fehler.value) == "55000"
            assert katalog(owner, "SELECT count(*) FROM buchung") == [(1,)]
        finally:
            app.dispose()
            owner.dispose()


def test_uebergebene_verbindung_hat_vorrang(
    admin_url: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests treffen nie die Datenbank aus der Umgebung."""
    monkeypatch.setenv(MIGRATION_URL_VARIABLE, "postgresql+psycopg://niemand@127.0.0.1:1/keine")
    with neue_testdatenbank(admin_url, migrieren=False) as datenbank:
        migriere(datenbank.owner_url)
        engine = erzeuge_engine(datenbank.owner_url)
        try:
            assert katalog(engine, "SELECT version_num FROM alembic_version") == [("0001",)]
        finally:
            engine.dispose()


def test_offline_migrationen_sind_nicht_vorgesehen() -> None:
    with pytest.raises(RuntimeError, match="Offline"):
        command.upgrade(Config(BACKEND / "alembic.ini"), "head", sql=True)
