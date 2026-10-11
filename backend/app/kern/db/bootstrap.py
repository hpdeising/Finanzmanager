# SPDX-License-Identifier: AGPL-3.0-or-later
"""Datenbankrollen und Datenbank anlegen (Fachkonzept 11.1, E-19).

- Die Eigentümerrolle besitzt die Datenbank und führt nur die Migrationen aus.
- Die Laufzeitrolle nutzt die Anwendung. Ihre Rechte an den Tabellen vergibt die
  Migration; an der Datenbank darf sie sich nur verbinden, also auch keine temporären
  Tabellen anlegen.

Rollen gelten für den ganzen Cluster. Deshalb legt sie dieses Skript an und nicht Alembic.
CI, Tests und der Installer nutzen es gleichermaßen. Es ist wiederholbar.

Aufruf (mit Superuser-Rechten)::

    python -m app.kern.db.bootstrap

Gelesen werden ``FINANZMANAGER_ADMIN_DATABASE_URL`` (Superuser),
``FINANZMANAGER_DATABASE_URL`` (Laufzeitrolle) und ``FINANZMANAGER_MIGRATION_DATABASE_URL``
(Eigentümerrolle). Rollennamen, Passwörter und Datenbankname kommen aus den beiden letzten.

Passwörter gehen nie im Klartext an den Server, sondern als SCRAM-Verifier, und keine
Meldung nennt sie.
"""

import os
from typing import Final

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import TupleRow
from sqlalchemy import URL, make_url

from app.kern.db.engine import URL_VARIABLE

OWNER_ROLE: Final = "finanzmanager_owner"
APP_ROLE: Final = "finanzmanager_app"
ADMIN_URL_VARIABLE: Final = "FINANZMANAGER_ADMIN_DATABASE_URL"
MIGRATION_URL_VARIABLE: Final = "FINANZMANAGER_MIGRATION_DATABASE_URL"

# Keine der Rollen braucht Sonderrechte.
_ROLLENATTRIBUTE: Final = sql.SQL(
    "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
)


def psycopg_verbindung(url: str | URL, *, autocommit: bool = True) -> psycopg.Connection[TupleRow]:
    """psycopg-Verbindung aus einer SQLAlchemy-Adresse (``postgresql+psycopg://…``).

    Die Teile gehen einzeln an libpq, nicht als URI. So braucht ein Passwort mit Leerzeichen
    oder Sonderzeichen keine Kodierung, und keine Meldung beim Zerlegen kann es enthalten.
    """
    adresse = make_url(url)
    zusatz: dict[str, str] = {}
    for schluessel, wert in adresse.query.items():
        if not isinstance(wert, str):
            msg = f"Parameter {schluessel} steht mehrfach in der Adresse."
            raise ValueError(msg)
        zusatz[schluessel] = wert
    return psycopg.connect(
        make_conninfo(**zusatz),
        host=adresse.host,
        port=adresse.port,
        user=adresse.username,
        password=adresse.password,
        dbname=adresse.database,
        autocommit=autocommit,
    )


def _richte_rolle_ein(verbindung: psycopg.Connection[TupleRow], rolle: str) -> None:
    vorhanden = verbindung.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (rolle,)).fetchone()
    befehl = "ALTER ROLE {} WITH {}" if vorhanden else "CREATE ROLE {} WITH {}"
    verbindung.execute(sql.SQL(befehl).format(sql.Identifier(rolle), _ROLLENATTRIBUTE))


def _setze_passwort(verbindung: psycopg.Connection[TupleRow], rolle: str, passwort: str) -> None:
    """Passwort als SCRAM-Verifier setzen; der Klartext verlässt den Client nicht.

    Ein Klartext in ``ALTER ROLE … PASSWORD`` kann im Serverlog landen (``log_statement``,
    bei einem Fehler auch ``log_min_error_statement``); davor warnt die PostgreSQL-Doku.
    """
    verifier = verbindung.pgconn.encrypt_password(
        passwort.encode(), rolle.encode(), b"scram-sha-256"
    )
    verbindung.execute(
        sql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(
            sql.Identifier(rolle), sql.Literal(verifier.decode("ascii"))
        )
    )


def richte_datenbank_ein(
    admin_url: str | URL,
    *,
    datenbank: str,
    owner_passwort: str | None = None,
    app_passwort: str | None = None,
) -> None:
    """Rollen und Datenbank anlegen oder angleichen; Passwörter nur setzen, wenn angegeben.

    Raises:
        RuntimeError: wenn die Datenbank schon existiert und nicht der Eigentümerrolle gehört.
            Dann ändert das Skript nichts.
        psycopg.Error: bei Fehlern der Verbindung oder einer Anweisung.
    """
    with psycopg_verbindung(admin_url) as verbindung:
        eigentuemer = verbindung.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (datenbank,)
        ).fetchone()
        if eigentuemer is not None and eigentuemer[0] != OWNER_ROLE:
            msg = (
                f"Die Datenbank {datenbank} gibt es schon, sie gehört aber nicht {OWNER_ROLE}."
                f" Eigentümer ändern (ALTER DATABASE … OWNER TO {OWNER_ROLE}) oder einen"
                " anderen Namen wählen."
            )
            raise RuntimeError(msg)
        for rolle, passwort in ((OWNER_ROLE, owner_passwort), (APP_ROLE, app_passwort)):
            _richte_rolle_ein(verbindung, rolle)
            if passwort is not None:
                _setze_passwort(verbindung, rolle, passwort)
        if eigentuemer is None:
            verbindung.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(datenbank), sql.Identifier(OWNER_ROLE)
                )
            )
        verbindung.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(datenbank))
        )
        verbindung.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(datenbank), sql.Identifier(APP_ROLE)
            )
        )


def _umgebung(variable: str) -> str:
    wert = os.environ.get(variable)
    if not wert:
        msg = f"Umgebungsvariable {variable} ist nicht gesetzt."
        raise SystemExit(msg)
    return wert


def main() -> None:
    """Einstieg für CI und Installer; Meldungen nennen nie Passwörter."""
    admin_url = _umgebung(ADMIN_URL_VARIABLE)
    app_url = make_url(_umgebung(URL_VARIABLE))
    owner_url = make_url(_umgebung(MIGRATION_URL_VARIABLE))
    if app_url.username != APP_ROLE:
        msg = f"{URL_VARIABLE} muss die Rolle {APP_ROLE} verwenden."
        raise SystemExit(msg)
    if owner_url.username != OWNER_ROLE:
        msg = f"{MIGRATION_URL_VARIABLE} muss die Rolle {OWNER_ROLE} verwenden."
        raise SystemExit(msg)
    if not app_url.database or app_url.database != owner_url.database:
        msg = f"{URL_VARIABLE} und {MIGRATION_URL_VARIABLE} müssen dieselbe Datenbank nennen."
        raise SystemExit(msg)
    try:
        richte_datenbank_ein(
            admin_url,
            datenbank=app_url.database,
            owner_passwort=owner_url.password,
            app_passwort=app_url.password,
        )
    except RuntimeError as fehler:
        raise SystemExit(str(fehler)) from None
    except psycopg.Error as fehler:
        # Nur Klasse und SQLSTATE: Der Text einer Datenbankmeldung ist nicht unter Kontrolle.
        msg = (
            f"Einrichtung der Datenbank fehlgeschlagen ({type(fehler).__name__},"
            f" SQLSTATE {fehler.sqlstate or 'unbekannt'}). Adresse, Erreichbarkeit und Rechte"
            f" des Superusers in {ADMIN_URL_VARIABLE} prüfen."
        )
        raise SystemExit(msg) from None


if __name__ == "__main__":
    main()
