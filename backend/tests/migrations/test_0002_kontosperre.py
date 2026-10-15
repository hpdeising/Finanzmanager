# SPDX-License-Identifier: AGPL-3.0-or-later
"""Migration 0002: Buchungsdatum, stornierbar, Kontosperre (E-26 bis E-28, Fachkonzept 4.4).

Die Migration füllt das Buchungsdatum bestehender Buchungen ohne UPDATE: Die Spalte entsteht
als generierte Spalte aus der Wertstellung und wird danach zu einer normalen Spalte. Bis zur
ersten Festschreibung liegt jede Buchung im offenen Zeitraum, dort ist das Buchungsdatum
gleich der Wertstellung (E-26).
"""

import importlib.util
import uuid
from collections.abc import Callable
from datetime import date
from types import ModuleType
from typing import Any

import pytest
from alembic import command
from sqlalchemy import URL, Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.kern.db import erzeuge_engine
from tests.datenbank import (
    BACKEND,
    alembic_config,
    migriere,
    neue_testdatenbank,
    roh_buchung,
    roh_haushalt,
    roh_konto,
    roh_postings,
    roh_sperre,
    sqlstate,
)


def katalog(engine: Engine, sql: str, **parameter: Any) -> list[Any]:
    with engine.connect() as verbindung:
        return list(verbindung.execute(text(sql), parameter).all())


def buchung_in_0001(sitzung: Session, haushalt_id: uuid.UUID, wertstellung: date) -> uuid.UUID:
    """Buchung im Schema von 0001, also ohne buchungsdatum und stornierbar."""
    return sitzung.execute(
        text(
            "INSERT INTO buchung (haushalt_id, art, wertstellung)"
            " VALUES (:haushalt_id, 'test.buchung', :wertstellung) RETURNING id"
        ),
        {"haushalt_id": haushalt_id, "wertstellung": wertstellung},
    ).scalar_one()


def zurueck_auf_0001(owner: Engine) -> None:
    with owner.begin() as verbindung:
        command.downgrade(alembic_config(verbindung), "0001")


def test_bestehende_buchungen_bekommen_buchungsdatum_und_stornierbar(admin_url: URL) -> None:
    with neue_testdatenbank(admin_url, migrieren=False) as datenbank:
        migriere(datenbank.owner_url, "0001")
        app = erzeuge_engine(datenbank.app_url)
        owner = erzeuge_engine(datenbank.owner_url)
        try:
            with Session(app) as sitzung:
                haushalt_id = roh_haushalt(sitzung)
                konto_a, konto_b = roh_konto(sitzung, haushalt_id), roh_konto(sitzung, haushalt_id)
                for tag in (date(2024, 1, 15), date(2024, 2, 29), date(2025, 12, 31)):
                    buchung_id = buchung_in_0001(sitzung, haushalt_id, tag)
                    roh_postings(sitzung, buchung_id, [(konto_a, "1"), (konto_b, "-1")])
                sitzung.commit()

            migriere(datenbank.owner_url)

            zeilen = katalog(owner, "SELECT wertstellung, buchungsdatum, stornierbar FROM buchung")
            assert len(zeilen) == 3
            assert all(buchungsdatum == wertstellung for wertstellung, buchungsdatum, _ in zeilen)
            assert all(stornierbar is True for _, _, stornierbar in zeilen)
        finally:
            app.dispose()
            owner.dispose()


def test_buchungsdatum_ist_eine_normale_pflichtspalte(owner_engine: Engine) -> None:
    """Nach DROP EXPRESSION: nicht generiert, ohne Default, NOT NULL (E-26)."""
    zeilen = katalog(
        owner_engine,
        "SELECT format_type(atttypid, atttypmod), attnotnull, atthasdef, attgenerated"
        " FROM pg_attribute"
        " WHERE attrelid = 'public.buchung'::regclass AND attname = 'buchungsdatum'",
    )
    assert zeilen == [("date", True, False, "")]


def test_stornierbar_ist_pflicht_mit_voreinstellung_wahr(owner_engine: Engine) -> None:
    zeilen = katalog(
        owner_engine,
        "SELECT format_type(a.atttypid, a.atttypmod), a.attnotnull,"
        " pg_get_expr(d.adbin, d.adrelid)"
        " FROM pg_attribute AS a LEFT JOIN pg_attrdef AS d"
        " ON d.adrelid = a.attrelid AND d.adnum = a.attnum"
        " WHERE a.attrelid = 'public.buchung'::regclass AND a.attname = 'stornierbar'",
    )
    assert zeilen == [("boolean", True, "true")]


def test_rueckweg_auf_0001_ohne_neue_daten(admin_url: URL) -> None:
    """Ohne Sperren, Stornoschutz und abweichendes Buchungsdatum geht nichts verloren."""
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

            zurueck_auf_0001(owner)

            assert katalog(owner, "SELECT version_num FROM alembic_version") == [("0001",)]
            assert katalog(owner, "SELECT to_regclass('public.konto_sperre')") == [(None,)]
            spalten = katalog(
                owner,
                "SELECT attname FROM pg_attribute WHERE attrelid = 'public.buchung'::regclass"
                " AND attname IN ('buchungsdatum', 'stornierbar') AND NOT attisdropped",
            )
            assert spalten == []
            funktionen = katalog(
                owner,
                "SELECT proname, prosrc FROM pg_proc"
                " WHERE pronamespace = 'public'::regnamespace AND proname LIKE 'ledger\\_%'",
            )
            assert {name for name, _ in funktionen} == {
                "ledger_pruefe_buchung",
                "ledger_buchung_vor_insert",
                "ledger_posting_vor_insert",
                "ledger_unveraenderlich",
                "ledger_konto_vor_update",
            }
            quelltext = dict(funktionen)
            assert "konto_sperre" not in quelltext["ledger_posting_vor_insert"]
            assert "stornierbar" not in quelltext["ledger_buchung_vor_insert"]

            # Im Stand 0001 bucht die Laufzeitrolle wieder ohne die neuen Spalten.
            with Session(app) as sitzung:
                neue = buchung_in_0001(sitzung, haushalt_id, date(2024, 3, 1))
                roh_postings(sitzung, neue, [(konto_a, "2"), (konto_b, "-2")])
                sitzung.commit()

            migriere(datenbank.owner_url)
            assert katalog(owner, "SELECT count(*) FROM buchung") == [(2,)]
        finally:
            app.dispose()
            owner.dispose()


def _mit_sperre(sitzung: Session, konto: uuid.UUID, haushalt_id: uuid.UUID) -> None:
    roh_sperre(sitzung, konto, date(2024, 6, 30))


def _nicht_stornierbar(sitzung: Session, konto: uuid.UUID, haushalt_id: uuid.UUID) -> None:
    gegen = roh_konto(sitzung, haushalt_id)
    buchung_id = roh_buchung(sitzung, haushalt_id, stornierbar=False)
    roh_postings(sitzung, buchung_id, [(konto, "1"), (gegen, "-1")])


def _spaetes_buchungsdatum(sitzung: Session, konto: uuid.UUID, haushalt_id: uuid.UUID) -> None:
    gegen = roh_konto(sitzung, haushalt_id)
    buchung_id = roh_buchung(
        sitzung, haushalt_id, wertstellung=date(2024, 1, 15), buchungsdatum=date(2024, 8, 1)
    )
    roh_postings(sitzung, buchung_id, [(konto, "1"), (gegen, "-1")])


@pytest.mark.parametrize(
    "daten", [_mit_sperre, _nicht_stornierbar, _spaetes_buchungsdatum], ids=lambda f: f.__name__
)
def test_rueckweg_bricht_ab_wenn_er_daten_verlieren_wuerde(
    admin_url: URL, daten: Callable[[Session, uuid.UUID, uuid.UUID], None]
) -> None:
    with neue_testdatenbank(admin_url) as datenbank:
        app = erzeuge_engine(datenbank.app_url)
        owner = erzeuge_engine(datenbank.owner_url)
        try:
            with Session(app) as sitzung:
                haushalt_id = roh_haushalt(sitzung)
                daten(sitzung, roh_konto(sitzung, haushalt_id), haushalt_id)
                sitzung.commit()
            with pytest.raises(DBAPIError) as fehler:
                zurueck_auf_0001(owner)
            assert sqlstate(fehler.value) == "55000"
            assert katalog(owner, "SELECT version_num FROM alembic_version") == [("0002",)]
        finally:
            app.dispose()
            owner.dispose()


def _rumpf(sql: str) -> str:
    """Funktionsrumpf zwischen ``AS $$`` und ``$$``."""
    return sql.split("AS $$", 1)[1].rsplit("$$", 1)[0]


def _migration(datei: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        datei, BACKEND / "migrations" / "versions" / datei
    )
    assert spec is not None
    assert spec.loader is not None
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_rueckweg_stellt_die_fassungen_aus_0001_wortgleich_her() -> None:
    """0002 kopiert die alten Rümpfe, weil Migrationen einander nicht importieren."""
    alt = {_name(sql): _rumpf(sql) for sql in _migration("0001_buchungskern.py").FUNKTIONEN}
    kopie = {_name(sql): _rumpf(sql) for sql in _migration("0002_kontosperre.py").FASSUNGEN_0001}
    assert set(kopie) == {"ledger_buchung_vor_insert", "ledger_posting_vor_insert"}
    for name, rumpf in kopie.items():
        assert rumpf == alt[name], name


def _name(sql: str) -> str:
    return sql.split("FUNCTION public.", 1)[1].split("(", 1)[0]
