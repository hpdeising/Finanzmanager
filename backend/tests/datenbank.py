# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hilfen für Tests gegen echtes PostgreSQL 16.

Jede Testsitzung legt über das Bootstrap-Skript eine eigene Datenbank ``fm_test_<hex>``
an, migriert sie als Eigentümerrolle und löscht sie am Ende wieder. Die Tests laufen als
Laufzeitrolle (Fachkonzept 11.1); Eigentümer und Superuser nur dort, wo ein Test genau
deren Verhalten prüft.

Zurückgestellte Prüfungen (DEFERRABLE INITIALLY DEFERRED) feuern erst beim COMMIT. Tests,
die mit Rollback arbeiten, lösen sie mit ``pruefe_aufgeschobene()`` aus.
"""

import os
import secrets
import uuid
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Final

import psycopg
from alembic import command
from alembic.config import Config
from hypothesis import settings
from sqlalchemy import URL, Connection, Engine, create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.kern.db import erzeuge_engine
from app.kern.db.bootstrap import APP_ROLE, OWNER_ROLE, richte_datenbank_ein

BACKEND: Final = Path(__file__).resolve().parent.parent
# Neueste Migration; die Katalogtests prüfen den Stand nach ``alembic upgrade head``.
HEAD: Final = "0002"
TEST_ADMIN_URL_VARIABLE: Final = "FINANZMANAGER_TEST_ADMIN_DATABASE_URL"
PRAEFIX: Final = "fm_test_"
MINDESTVERSION: Final = 160000

# --- Hypothesis-Profile für Property-Tests mit Datenbank ---------------------------
# Die CI begrenzt die Beispielzahl, damit der Job unter etwa fünf Minuten bleibt; lokal
# läuft standardmäßig das gründlichere Profil. Ein unbekannter Name ist ein Fehler.

DB_PROFIL_VARIABLE: Final = "FINANZMANAGER_HYPOTHESIS_DB_PROFIL"
settings.register_profile("db-ci", deadline=None, max_examples=50)
settings.register_profile("db-gruendlich", deadline=None, max_examples=200)
DB_EINSTELLUNGEN: Final = settings.get_profile(os.environ.get(DB_PROFIL_VARIABLE, "db-gruendlich"))


@dataclass(frozen=True)
class Sitzungsdatenbank:
    """Adressen einer frisch migrierten Sitzungsdatenbank, je Rolle."""

    name: str
    admin_url: URL
    owner_url: URL
    app_url: URL


def alembic_config(verbindung: Connection) -> Config:
    """Alembic-Konfiguration, die eine offene Verbindung nutzt statt einer URL als Text."""
    config = Config(BACKEND / "alembic.ini")
    config.attributes["connection"] = verbindung
    return config


def pruefe_testdatenbank(verbindung: Connection) -> None:
    """Schutz: Migrationen in Tests laufen nur gegen Datenbanken mit Präfix ``fm_test_``."""
    name = verbindung.execute(text("SELECT current_database()")).scalar_one()
    if not str(name).startswith(PRAEFIX):
        msg = f"Keine Sitzungsdatenbank: {name}"
        raise RuntimeError(msg)


def pruefe_cluster(admin_url: URL) -> None:
    """Schutz: Jede Testsitzung setzt die Passwörter der clusterweiten Rollen neu.

    Liegt auf dem Cluster eine echte Instanz, könnte sie sich danach nicht mehr anmelden.
    Erkennbar ist sie an einer Datenbank ohne Präfix ``fm_test_``, die einer der beiden Rollen
    gehört oder ihnen ausdrücklich Rechte gibt. Dann bricht der Testlauf ab.
    """
    engine = create_engine(admin_url, hide_parameters=True)
    try:
        with engine.connect() as verbindung:
            namen = (
                verbindung.execute(
                    text(
                        "SELECT d.datname FROM pg_database AS d"
                        " WHERE d.datname NOT LIKE 'fm\\_test\\_%'"
                        " AND (pg_get_userbyid(d.datdba) IN (:owner, :app)"
                        " OR EXISTS (SELECT 1 FROM aclexplode(d.datacl) AS a"
                        " JOIN pg_roles AS r ON r.oid = a.grantee"
                        " WHERE r.rolname IN (:owner, :app)))"
                        " ORDER BY d.datname"
                    ),
                    {"owner": OWNER_ROLE, "app": APP_ROLE},
                )
                .scalars()
                .all()
            )
    finally:
        engine.dispose()
    if namen:
        msg = (
            f"Der Test-Cluster enthält Datenbanken einer Finanzmanager-Instanz: {', '.join(namen)}."
            " Die Tests setzen die Passwörter der Rollen neu; bitte einen eigenen Cluster nur für"
            " Tests verwenden (CONTRIBUTING.md, Abschnitt „Test-Datenbank“)."
        )
        raise RuntimeError(msg)


def migriere(url: URL, ziel: str = "head") -> None:
    """Als Eigentümerrolle auf ``ziel`` migrieren."""
    engine = erzeuge_engine(url)
    try:
        with engine.begin() as verbindung:
            pruefe_testdatenbank(verbindung)
            command.upgrade(alembic_config(verbindung), ziel)
    finally:
        engine.dispose()


@contextmanager
def neue_testdatenbank(admin_url: URL, *, migrieren: bool = True) -> Generator[Sitzungsdatenbank]:
    """Rollen und Datenbank per Bootstrap anlegen, migrieren und am Ende löschen.

    Die Datenbank bekommt absichtlich die Zeitzone Europe/Berlin. So prüfen die Tests,
    dass die Engine Zeitstempel trotzdem in UTC liefert.
    """
    pruefe_cluster(admin_url)
    name = f"{PRAEFIX}{secrets.token_hex(6)}"
    owner_passwort = secrets.token_urlsafe(24)
    app_passwort = secrets.token_urlsafe(24)
    richte_datenbank_ein(
        admin_url,
        datenbank=name,
        owner_passwort=owner_passwort,
        app_passwort=app_passwort,
    )
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    try:
        with admin.connect() as verbindung:
            verbindung.execute(text(f"ALTER DATABASE \"{name}\" SET timezone = 'Europe/Berlin'"))
        datenbank = Sitzungsdatenbank(
            name=name,
            admin_url=admin_url.set(database=name),
            owner_url=admin_url.set(username=OWNER_ROLE, password=owner_passwort, database=name),
            app_url=admin_url.set(username=APP_ROLE, password=app_passwort, database=name),
        )
        if migrieren:
            migriere(datenbank.owner_url)
        yield datenbank
    finally:
        with admin.connect() as verbindung:
            verbindung.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@contextmanager
def sitzung_mit_rollback(engine: Engine) -> Generator[Session]:
    """Session in einer äußeren Transaktion, die am Ende immer zurückgerollt wird."""
    with engine.connect() as verbindung:
        transaktion = verbindung.begin()
        sitzung = Session(bind=verbindung, join_transaction_mode="create_savepoint")
        try:
            yield sitzung
        finally:
            sitzung.close()
            if transaktion.is_active:
                transaktion.rollback()


def pruefe_aufgeschobene(sitzung: Session) -> None:
    """Zurückgestellte Prüfungen jetzt auslösen, danach wieder zurückstellen.

    ``SET CONSTRAINTS … IMMEDIATE`` prüft alle ausstehenden Ereignisse rückwirkend
    (PostgreSQL-Doku zu SET CONSTRAINTS). Danach gilt wieder DEFERRED, damit spätere
    Buchungen im selben Test nicht schon beim INSERT der Buchung scheitern.
    """
    sitzung.flush()
    sitzung.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    sitzung.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def sqlstate(fehler: BaseException) -> str | None:
    """SQLSTATE eines Datenbankfehlers, auch wenn SQLAlchemy ihn eingepackt hat."""
    ursprung = fehler.orig if isinstance(fehler, DBAPIError) else fehler
    return ursprung.sqlstate if isinstance(ursprung, psycopg.Error) else None


def constraint_name(fehler: BaseException) -> str | None:
    """Name der verletzten Regel (``RAISE … USING CONSTRAINT`` oder Constraint der Tabelle)."""
    ursprung = fehler.orig if isinstance(fehler, DBAPIError) else fehler
    return ursprung.diag.constraint_name if isinstance(ursprung, psycopg.Error) else None


# --- Roh-SQL am API vorbei -------------------------------------------------------------

WERTSTELLUNG: Final = date(2024, 1, 15)


def roh_haushalt(sitzung: Session) -> uuid.UUID:
    return sitzung.execute(
        text("INSERT INTO haushalt (betriebsart) VALUES ('einzel') RETURNING id")
    ).scalar_one()


def roh_konto(sitzung: Session, haushalt_id: uuid.UUID, rolle: str = "test.konto") -> uuid.UUID:
    return sitzung.execute(
        text(
            "INSERT INTO konto (haushalt_id, kontoart, rolle, bezeichnung)"
            " VALUES (:haushalt_id, 'passiv', :rolle, 'Testkonto') RETURNING id"
        ),
        {"haushalt_id": haushalt_id, "rolle": rolle},
    ).scalar_one()


def roh_buchung(
    sitzung: Session,
    haushalt_id: uuid.UUID,
    *,
    art: str = "test.buchung",
    wertstellung: date = WERTSTELLUNG,
    buchungsdatum: date | None = None,
    storno_von: uuid.UUID | None = None,
    stornierbar: bool = True,
) -> uuid.UUID:
    """Buchung ohne Postings; ohne Buchungsdatum gilt die Wertstellung (offener Zeitraum)."""
    return sitzung.execute(
        text(
            "INSERT INTO buchung"
            " (haushalt_id, art, wertstellung, buchungsdatum, storno_von, stornierbar)"
            " VALUES (:haushalt_id, :art, :wertstellung, :buchungsdatum, :storno_von,"
            " :stornierbar) RETURNING id"
        ),
        {
            "haushalt_id": haushalt_id,
            "art": art,
            "wertstellung": wertstellung,
            "buchungsdatum": wertstellung if buchungsdatum is None else buchungsdatum,
            "storno_von": storno_von,
            "stornierbar": stornierbar,
        },
    ).scalar_one()


def roh_sperre(sitzung: Session, konto_id: uuid.UUID, gesperrt_bis: date) -> None:
    """Konto bis einschließlich ``gesperrt_bis`` sperren (E-27), am API vorbei."""
    sitzung.execute(
        text("INSERT INTO konto_sperre (konto_id, gesperrt_bis) VALUES (:konto_id, :bis)"),
        {"konto_id": konto_id, "bis": gesperrt_bis},
    )


def roh_postings(
    sitzung: Session, buchung_id: uuid.UUID, postings: Sequence[tuple[uuid.UUID, str]]
) -> None:
    """Postings einzeln einfügen; Beträge als Text, ohne den Betragstyp der Anwendung."""
    for konto_id, betrag in postings:
        sitzung.execute(
            text(
                "INSERT INTO posting (buchung_id, konto_id, betrag)"
                " VALUES (:buchung_id, :konto_id, CAST(:betrag AS numeric))"
            ),
            {"buchung_id": buchung_id, "konto_id": konto_id, "betrag": betrag},
        )


def roh_salden(sitzung: Session, haushalt_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    """Summe je Konto eines Haushalts, unabhängig von der Anwendung berechnet."""
    zeilen = sitzung.execute(
        text(
            "SELECT k.id, coalesce(sum(p.betrag), 0) FROM konto AS k"
            " LEFT JOIN posting AS p ON p.konto_id = k.id"
            " WHERE k.haushalt_id = :haushalt_id GROUP BY k.id"
        ),
        {"haushalt_id": haushalt_id},
    ).all()
    return {zeile[0]: zeile[1] for zeile in zeilen}
