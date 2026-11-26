# SPDX-License-Identifier: AGPL-3.0-or-later
"""Migration 0005: Import von Zahlungen (Fachkonzept Kap. 8, 4.5).

Geprüft werden die Regeln, die nur die Datenbank durchsetzt: Rechte der Laufzeitrolle,
eindeutiger Schlüssel gebuchter Zeilen, Unveränderlichkeit gebuchter Zeilen und ihrer
Verknüpfungen, der Rückweg. Alle Daten sind erfunden.
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
    constraint_name,
    migriere,
    neue_testdatenbank,
    roh_buchung,
    roh_haushalt,
    sqlstate,
)

SCHLUESSEL = "a" * 64


def katalog(engine: Engine, sql: str, **parameter: object) -> list[Any]:
    with engine.connect() as verbindung:
        return list(verbindung.execute(text(sql), parameter).all())


def roh_lauf(sitzung: Session, haushalt_id: uuid.UUID) -> uuid.UUID:
    return sitzung.execute(
        text(
            "INSERT INTO import_lauf (haushalt_id, format, wertstellung_aus, umsaetze_gelesen)"
            " VALUES (:h, 'camt053', 'buchungstag', 1) RETURNING id"
        ),
        {"h": haushalt_id},
    ).scalar_one()


def roh_zeile(
    sitzung: Session,
    lauf_id: uuid.UUID,
    haushalt_id: uuid.UUID,
    *,
    position: int = 1,
    schluessel: str = SCHLUESSEL,
    status: str = "offen",
) -> uuid.UUID:
    return sitzung.execute(
        text(
            "INSERT INTO import_zeile (lauf_id, haushalt_id, position, datum, buchungstag,"
            " betrag, verwendungszweck, schluessel, status) VALUES (:l, :h, :p,"
            " DATE '2025-02-03', DATE '2025-02-03', 150, 'Rate', :s, :st) RETURNING id"
        ),
        {"l": lauf_id, "h": haushalt_id, "p": position, "s": schluessel, "st": status},
    ).scalar_one()


@pytest.mark.parametrize(
    ("tabelle", "rechte"),
    [
        ("csv_profil", {"SELECT", "INSERT", "UPDATE", "DELETE"}),
        ("import_lauf", {"SELECT", "INSERT"}),
        ("import_zeile", {"SELECT", "INSERT", "DELETE"}),
        ("import_zeile_buchung", {"SELECT", "INSERT"}),
    ],
)
def test_rechte_der_laufzeitrolle(owner_engine: Engine, tabelle: str, rechte: set[str]) -> None:
    """Tabellenrechte (E-19); Spaltenrechte zum Ändern prüft der nächste Test."""
    for recht in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        zeilen = katalog(
            owner_engine,
            "SELECT has_table_privilege(:rolle, :tabelle, :recht)",
            rolle=APP_ROLE,
            tabelle=f"public.{tabelle}",
            recht=recht,
        )
        assert zeilen == [(recht in rechte,)], recht


@pytest.mark.parametrize(
    ("tabelle", "spalte"),
    [("import_lauf", "abgeschlossen_am"), ("import_zeile", "status")],
)
def test_aendern_nur_einer_spalte(owner_engine: Engine, tabelle: str, spalte: str) -> None:
    zeilen = katalog(
        owner_engine,
        "SELECT attname FROM pg_attribute WHERE attrelid = CAST(:tabelle AS regclass)"
        " AND attnum > 0 AND NOT attisdropped"
        " AND has_column_privilege(:rolle, attrelid, attnum, 'UPDATE') ORDER BY attname",
        tabelle=f"public.{tabelle}",
        rolle=APP_ROLE,
    )
    assert zeilen == [(spalte,)]


def test_schluessel_je_haushalt_hoechstens_einmal_gebucht(session: Session) -> None:
    haushalt_id = roh_haushalt(session)
    erster, zweiter = roh_lauf(session, haushalt_id), roh_lauf(session, haushalt_id)
    roh_zeile(session, erster, haushalt_id, status="gebucht")
    roh_zeile(session, zweiter, haushalt_id)  # offen: erlaubt
    with pytest.raises(DBAPIError) as fehler:
        roh_zeile(session, zweiter, haushalt_id, position=2, status="gebucht")
    assert constraint_name(fehler.value) == "uq_import_zeile_gebucht_schluessel"


def test_gleicher_schluessel_in_anderem_haushalt(session: Session) -> None:
    for _ in range(2):
        haushalt_id = roh_haushalt(session)
        roh_zeile(session, roh_lauf(session, haushalt_id), haushalt_id, status="gebucht")


def test_zeile_gehoert_zum_haushalt_ihres_laufs(session: Session) -> None:
    lauf_id = roh_lauf(session, roh_haushalt(session))
    with pytest.raises(DBAPIError) as fehler:
        roh_zeile(session, lauf_id, roh_haushalt(session))
    assert constraint_name(fehler.value) == "fk_import_zeile_lauf_id_import_lauf"


def test_offene_zeile_wird_gebucht_oder_geloescht(session: Session) -> None:
    haushalt_id = roh_haushalt(session)
    lauf_id = roh_lauf(session, haushalt_id)
    gebucht = roh_zeile(session, lauf_id, haushalt_id)
    geloescht = roh_zeile(session, lauf_id, haushalt_id, position=2, schluessel="b" * 64)
    session.execute(
        text("UPDATE import_zeile SET status = 'gebucht' WHERE id = :id"), {"id": gebucht}
    )
    session.execute(text("DELETE FROM import_zeile WHERE id = :id"), {"id": geloescht})
    assert session.execute(text("SELECT status FROM import_zeile")).scalars().all() == ["gebucht"]


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE import_zeile SET status = 'offen' WHERE id = :id",
        "DELETE FROM import_zeile WHERE id = :id",
    ],
)
def test_gebuchte_zeile_unveraenderlich(session: Session, sql: str) -> None:
    haushalt_id = roh_haushalt(session)
    zeile_id = roh_zeile(session, roh_lauf(session, haushalt_id), haushalt_id, status="gebucht")
    with pytest.raises(DBAPIError) as fehler:
        session.execute(text(sql), {"id": zeile_id})
    assert constraint_name(fehler.value) == "import_zeile_unveraenderlich"


def test_beim_buchen_bleibt_der_rest_der_zeile(owner_session: Session) -> None:
    """Auch die Eigentümerrolle ändert beim Buchen nur den Status."""
    haushalt_id = roh_haushalt(owner_session)
    zeile_id = roh_zeile(owner_session, roh_lauf(owner_session, haushalt_id), haushalt_id)
    with pytest.raises(DBAPIError) as fehler:
        owner_session.execute(
            text("UPDATE import_zeile SET status = 'gebucht', betrag = 1 WHERE id = :id"),
            {"id": zeile_id},
        )
    assert constraint_name(fehler.value) == "import_zeile_unveraenderlich"


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE import_zeile_buchung SET buchung_id = buchung_id WHERE zeile_id = :id",
        "DELETE FROM import_zeile_buchung WHERE zeile_id = :id",
    ],
)
def test_verknuepfung_unveraenderlich(owner_session: Session, sql: str) -> None:
    haushalt_id = roh_haushalt(owner_session)
    zeile_id = roh_zeile(
        owner_session, roh_lauf(owner_session, haushalt_id), haushalt_id, status="gebucht"
    )
    buchung_id = roh_buchung(owner_session, haushalt_id)
    owner_session.execute(
        text("INSERT INTO import_zeile_buchung (zeile_id, buchung_id) VALUES (:z, :b)"),
        {"z": zeile_id, "b": buchung_id},
    )
    with pytest.raises(DBAPIError) as fehler:
        owner_session.execute(text(sql), {"id": zeile_id})
    assert constraint_name(fehler.value) == "import_zeile_buchung_unveraenderlich"


def test_buchung_stammt_aus_hoechstens_einer_zeile(session: Session) -> None:
    haushalt_id = roh_haushalt(session)
    lauf_id = roh_lauf(session, haushalt_id)
    buchung_id = roh_buchung(session, haushalt_id)
    for position in (1, 2):
        zeile_id = roh_zeile(
            session, lauf_id, haushalt_id, position=position, schluessel=f"{position}" * 64
        )
        sql = text("INSERT INTO import_zeile_buchung (zeile_id, buchung_id) VALUES (:z, :b)")
        if position == 1:
            session.execute(sql, {"z": zeile_id, "b": buchung_id})
            continue
        with pytest.raises(DBAPIError) as fehler:
            session.execute(sql, {"z": zeile_id, "b": buchung_id})
        assert constraint_name(fehler.value) == "uq_import_zeile_buchung_buchung_id"


@pytest.mark.parametrize(
    ("sql", "constraint"),
    [
        (
            "INSERT INTO import_lauf (haushalt_id, format, wertstellung_aus, umsaetze_gelesen)"
            " VALUES (:h, 'csv', 'buchungstag', 0)",
            "ck_import_lauf_profil_nur_bei_csv",
        ),
        (
            "INSERT INTO import_lauf (haushalt_id, format, wertstellung_aus, umsaetze_gelesen)"
            " VALUES (:h, 'camt053', 'heute', 0)",
            "ck_import_lauf_wertstellung_aus",
        ),
        (
            "INSERT INTO csv_profil (haushalt_id, name, spalte_buchungstag, spalte_betrag,"
            " spalten_verwendungszweck, trennzeichen, kodierung, datumsformat,"
            " dezimaltrennzeichen, tausendertrennzeichen, kopfzeilen_ueberspringen)"
            " VALUES (:h, 'Bank', 'Tag', 'Betrag', ARRAY['Zweck'], ';', 'utf-8', '%d.%m.%Y',"
            " ',', ',', 0)",
            "ck_csv_profil_tausendertrennzeichen",
        ),
        (
            "INSERT INTO csv_profil (haushalt_id, name, spalte_buchungstag, spalte_betrag,"
            " spalten_verwendungszweck, trennzeichen, kodierung, datumsformat,"
            " dezimaltrennzeichen, kopfzeilen_ueberspringen)"
            " VALUES (:h, 'Bank', 'Tag', 'Betrag', ARRAY[]::text[], ';', 'utf-8', '%d.%m.%Y',"
            " ',', 0)",
            "ck_csv_profil_verwendungszweck_vorhanden",
        ),
    ],
)
def test_pruefungen(session: Session, sql: str, constraint: str) -> None:
    with pytest.raises(DBAPIError) as fehler:
        session.execute(text(sql), {"h": roh_haushalt(session)})
    assert constraint_name(fehler.value) == constraint


def test_rueckweg_ohne_daten(admin_url: URL) -> None:
    with neue_testdatenbank(admin_url) as datenbank:
        owner = erzeuge_engine(datenbank.owner_url)
        try:
            with owner.begin() as verbindung:
                command.downgrade(alembic_config(verbindung), "0004")
            tabellen = katalog(
                owner,
                "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace"
                " AND relname IN ('csv_profil', 'import_lauf', 'import_zeile',"
                " 'import_zeile_buchung')",
            )
            assert tabellen == []
            migriere(datenbank.owner_url)
            assert katalog(owner, "SELECT version_num FROM alembic_version") == [(HEAD,)]
        finally:
            owner.dispose()


def test_rueckweg_bricht_ab_wenn_daten_existieren(admin_url: URL) -> None:
    with neue_testdatenbank(admin_url) as datenbank:
        app = erzeuge_engine(datenbank.app_url)
        owner = erzeuge_engine(datenbank.owner_url)
        try:
            with Session(app) as sitzung:
                roh_lauf(sitzung, roh_haushalt(sitzung))
                sitzung.commit()
            with pytest.raises(DBAPIError) as fehler, owner.begin() as verbindung:
                command.downgrade(alembic_config(verbindung), "0004")
            assert sqlstate(fehler.value) == "55000"
            assert katalog(owner, "SELECT version_num FROM alembic_version") == [(HEAD,)]
        finally:
            app.dispose()
            owner.dispose()
