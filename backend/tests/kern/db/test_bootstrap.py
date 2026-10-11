# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bootstrap der Datenbankrollen (Fachkonzept 11.1, E-19).

Die Eigentümerrolle besitzt die Datenbank und führt nur die Migrationen aus; die
Laufzeitrolle darf sich verbinden, aber weder Objekte noch temporäre Tabellen anlegen.
"""

import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from sqlalchemy import URL, Engine, create_engine, text

from app.kern.db import erzeuge_engine
from app.kern.db.bootstrap import (
    ADMIN_URL_VARIABLE,
    APP_ROLE,
    MIGRATION_URL_VARIABLE,
    OWNER_ROLE,
    main,
    psycopg_verbindung,
    richte_datenbank_ein,
)
from app.kern.db.engine import URL_VARIABLE
from tests.datenbank import PRAEFIX, Sitzungsdatenbank, pruefe_cluster

# Erfundenes, falsches Passwort mit allem, was eine URI zerlegen könnte.
SONDERPASSWORT = "Wort mit Leerzeichen ' \\ % @ : / ? # + &"


@pytest.fixture
def admin(admin_url: URL) -> Iterator[Engine]:
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    yield engine
    engine.dispose()


def test_bootstrap_ist_wiederholbar(admin_url: URL, testdatenbank: Sitzungsdatenbank) -> None:
    """Ohne Passwörter ändert ein zweiter Lauf nichts und scheitert nicht."""
    richte_datenbank_ein(
        admin_url.render_as_string(hide_password=False), datenbank=testdatenbank.name
    )
    richte_datenbank_ein(
        admin_url.render_as_string(hide_password=False), datenbank=testdatenbank.name
    )


@pytest.mark.parametrize("rolle", [OWNER_ROLE, APP_ROLE])
def test_rollen_haben_keine_sonderrechte(admin: Engine, rolle: str) -> None:
    with admin.connect() as verbindung:
        zeile = verbindung.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls,"
                " rolcanlogin FROM pg_roles WHERE rolname = :rolle"
            ),
            {"rolle": rolle},
        ).one()
    assert tuple(zeile) == (False, False, False, False, False, True)


def test_laufzeitrolle_ist_nicht_mitglied_der_eigentuemerrolle(admin: Engine) -> None:
    with admin.connect() as verbindung:
        mitglied = verbindung.execute(
            text("SELECT pg_has_role(:app, :owner, 'MEMBER')"),
            {"app": APP_ROLE, "owner": OWNER_ROLE},
        ).scalar_one()
    assert mitglied is False


def test_eigentuemerrolle_besitzt_die_datenbank(
    admin: Engine, testdatenbank: Sitzungsdatenbank
) -> None:
    with admin.connect() as verbindung:
        besitzer = verbindung.execute(
            text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = :name"),
            {"name": testdatenbank.name},
        ).scalar_one()
    assert besitzer == OWNER_ROLE


@pytest.mark.parametrize(
    ("recht", "erwartet"),
    [("CONNECT", True), ("CREATE", False), ("TEMPORARY", False)],
)
def test_rechte_der_laufzeitrolle_an_der_datenbank(
    admin: Engine, testdatenbank: Sitzungsdatenbank, recht: str, erwartet: bool
) -> None:
    """Ohne TEMP kann die Laufzeitrolle keine Tabellen vor die echten schieben."""
    with admin.connect() as verbindung:
        hat_recht = verbindung.execute(
            text("SELECT has_database_privilege(:rolle, :name, :recht)"),
            {"rolle": APP_ROLE, "name": testdatenbank.name, "recht": recht},
        ).scalar_one()
    assert hat_recht is erwartet


def test_laufzeitrolle_kann_im_schema_nichts_anlegen(app_engine: Engine) -> None:
    with app_engine.connect() as verbindung:
        darf = verbindung.execute(
            text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        ).scalar_one()
    assert darf is False


def test_anmeldung_mit_den_gesetzten_passwoertern(testdatenbank: Sitzungsdatenbank) -> None:
    """Die Anmeldung läuft über scram; sie gelingt nur, wenn Bootstrap die Passwörter setzte."""
    for url, rolle in ((testdatenbank.app_url, APP_ROLE), (testdatenbank.owner_url, OWNER_ROLE)):
        engine = erzeuge_engine(url)
        try:
            with engine.connect() as verbindung:
                assert verbindung.execute(text("SELECT current_user")).scalar_one() == rolle
        finally:
            engine.dispose()


def test_kommandozeile_legt_eine_datenbank_an(
    monkeypatch: pytest.MonkeyPatch, admin: Engine, admin_url: URL, testdatenbank: Sitzungsdatenbank
) -> None:
    """Weg des Installers: Adressen aus der Umgebung, Rollen und Passwörter aus den URLs."""
    name = f"{PRAEFIX}{secrets.token_hex(6)}"
    app_url = testdatenbank.app_url.set(database=name)
    owner_url = testdatenbank.owner_url.set(database=name)
    monkeypatch.setenv(ADMIN_URL_VARIABLE, admin_url.render_as_string(hide_password=False))
    monkeypatch.setenv(URL_VARIABLE, app_url.render_as_string(hide_password=False))
    monkeypatch.setenv(MIGRATION_URL_VARIABLE, owner_url.render_as_string(hide_password=False))
    try:
        main()
        engine = erzeuge_engine(app_url)
        try:
            with engine.connect() as verbindung:
                assert verbindung.execute(text("SELECT current_database()")).scalar_one() == name
        finally:
            engine.dispose()
    finally:
        with admin.connect() as verbindung:
            verbindung.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.mark.parametrize(
    ("app_rolle", "owner_rolle", "app_db", "owner_db", "meldung"),
    [
        ("andere", OWNER_ROLE, "fm", "fm", APP_ROLE),
        (APP_ROLE, "andere", "fm", "fm", OWNER_ROLE),
        (APP_ROLE, OWNER_ROLE, "fm", "andere", "Datenbank"),
    ],
)
def test_kommandozeile_prueft_die_adressen(
    monkeypatch: pytest.MonkeyPatch,
    admin_url: URL,
    app_rolle: str,
    owner_rolle: str,
    app_db: str,
    owner_db: str,
    meldung: str,
) -> None:
    monkeypatch.setenv(ADMIN_URL_VARIABLE, admin_url.render_as_string(hide_password=False))
    monkeypatch.setenv(URL_VARIABLE, f"postgresql+psycopg://{app_rolle}:geheim@127.0.0.1/{app_db}")
    monkeypatch.setenv(
        MIGRATION_URL_VARIABLE, f"postgresql+psycopg://{owner_rolle}:geheim@127.0.0.1/{owner_db}"
    )
    with pytest.raises(SystemExit, match=meldung) as fehler:
        main()
    assert "geheim" not in str(fehler.value)


def test_kommandozeile_verlangt_alle_variablen(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (ADMIN_URL_VARIABLE, URL_VARIABLE, MIGRATION_URL_VARIABLE):
        monkeypatch.delenv(variable, raising=False)
    with pytest.raises(SystemExit, match=ADMIN_URL_VARIABLE):
        main()


def test_passwoerter_gehen_nur_als_scram_verifier_an_den_server(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    admin_url: URL,
    testdatenbank: Sitzungsdatenbank,
) -> None:
    """Ein Klartext in ALTER ROLE … PASSWORD kann im Serverlog landen (PostgreSQL-Doku).

    Das libpq-Protokoll der Verbindung zeigt, was tatsächlich an den Server geht. Gesetzt
    werden dieselben Passwörter wie für die Sitzung, damit sich nichts ändert.
    """
    protokoll = tmp_path / "libpq.trace"
    verbinde = psycopg.connect

    with protokoll.open("w") as datei:

        def mit_protokoll(*args: Any, **kwargs: Any) -> Any:
            verbindung = verbinde(*args, **kwargs)
            verbindung.pgconn.trace(datei.fileno())
            return verbindung

        monkeypatch.setattr(psycopg, "connect", mit_protokoll)
        richte_datenbank_ein(
            admin_url.render_as_string(hide_password=False),
            datenbank=testdatenbank.name,
            owner_passwort=testdatenbank.owner_url.password,
            app_passwort=testdatenbank.app_url.password,
        )
    inhalt = protokoll.read_text()
    assert inhalt.count("PASSWORD 'SCRAM-SHA-256$") == 2
    for passwort in (testdatenbank.owner_url.password, testdatenbank.app_url.password):
        assert passwort
        assert passwort not in inhalt


def test_admin_passwort_mit_sonderzeichen(admin_url: URL) -> None:
    """Die Adresse geht in Teilen an libpq, nicht als URI: nichts wird falsch zerlegt.

    Das Passwort ist absichtlich falsch; erwartet wird die Ablehnung durch den Server, nicht
    ein Fehler beim Zerlegen der Adresse, und keine Meldung nennt das Passwort.
    """
    falsch = admin_url.set(password=SONDERPASSWORT).render_as_string(hide_password=False)
    with pytest.raises(psycopg.OperationalError, match="password authentication failed") as fehler:
        richte_datenbank_ein(falsch, datenbank=f"{PRAEFIX}nie_angelegt")
    assert "Leerzeichen" not in str(fehler.value)


def test_kommandozeile_meldet_datenbankfehler_ohne_passwort(
    monkeypatch: pytest.MonkeyPatch, admin_url: URL, testdatenbank: Sitzungsdatenbank
) -> None:
    falsch = admin_url.set(password=SONDERPASSWORT).render_as_string(hide_password=False)
    monkeypatch.setenv(ADMIN_URL_VARIABLE, falsch)
    monkeypatch.setenv(URL_VARIABLE, testdatenbank.app_url.render_as_string(hide_password=False))
    monkeypatch.setenv(
        MIGRATION_URL_VARIABLE, testdatenbank.owner_url.render_as_string(hide_password=False)
    )
    with pytest.raises(SystemExit, match="fehlgeschlagen") as fehler:
        main()
    assert fehler.value.__cause__ is None
    assert fehler.value.__suppress_context__
    meldung = str(fehler.value)
    for geheim in (
        SONDERPASSWORT,
        testdatenbank.app_url.password,
        testdatenbank.owner_url.password,
    ):
        assert geheim
        assert geheim not in meldung
    assert "Leerzeichen" not in meldung


def test_vorhandene_datenbank_eines_anderen_eigentuemers(admin: Engine, admin_url: URL) -> None:
    """So legt etwa das offizielle Image eine Datenbank über POSTGRES_DB an.

    Die Eigentümerrolle könnte dort nichts anlegen; das Bootstrap bricht deshalb ab, statt
    Erfolg zu melden, und ändert nichts.
    """
    name = f"{PRAEFIX}{secrets.token_hex(6)}"
    with admin.connect() as verbindung:
        verbindung.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        with pytest.raises(RuntimeError, match=OWNER_ROLE):
            richte_datenbank_ein(admin_url.render_as_string(hide_password=False), datenbank=name)
        with admin.connect() as verbindung:
            verbindet = verbindung.execute(
                text("SELECT has_database_privilege(:rolle, :name, 'CONNECT')"),
                {"rolle": APP_ROLE, "name": name},
            ).scalar_one()
        # Unverändert: PUBLIC darf sich weiter verbinden, kein REVOKE ist gelaufen.
        assert verbindet is True
    finally:
        with admin.connect() as verbindung:
            verbindung.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.mark.parametrize("bezug", ["eigentuemer", "connect"])
def test_tests_verweigern_einen_cluster_mit_einer_instanz(
    admin: Engine, admin_url: URL, bezug: str
) -> None:
    """Tests setzen die Passwörter der clusterweiten Rollen neu; das träfe eine echte Instanz."""
    name = f"fm_instanz_{secrets.token_hex(6)}"
    with admin.connect() as verbindung:
        if bezug == "eigentuemer":
            verbindung.execute(text(f'CREATE DATABASE "{name}" OWNER {OWNER_ROLE}'))
        else:
            verbindung.execute(text(f'CREATE DATABASE "{name}"'))
            verbindung.execute(text(f'GRANT CONNECT ON DATABASE "{name}" TO {APP_ROLE}'))
    try:
        with pytest.raises(RuntimeError, match=name):
            pruefe_cluster(admin_url)
    finally:
        with admin.connect() as verbindung:
            verbindung.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def test_tests_akzeptieren_einen_cluster_ohne_instanz(admin_url: URL) -> None:
    pruefe_cluster(admin_url)


@pytest.mark.parametrize("variable", [ADMIN_URL_VARIABLE, URL_VARIABLE, MIGRATION_URL_VARIABLE])
def test_kommandozeile_nennt_bei_kaputter_adresse_kein_passwort(
    monkeypatch: pytest.MonkeyPatch, testdatenbank: Sitzungsdatenbank, variable: str
) -> None:
    """Ein nicht kodiertes ``@`` im Passwort: SQLAlchemy zitierte den Rest der Adresse."""
    gueltig = {
        ADMIN_URL_VARIABLE: "postgresql+psycopg://postgres:geheim@127.0.0.1/postgres",
        URL_VARIABLE: testdatenbank.app_url.render_as_string(hide_password=False),
        MIGRATION_URL_VARIABLE: testdatenbank.owner_url.render_as_string(hide_password=False),
    }
    rolle = {ADMIN_URL_VARIABLE: "postgres", URL_VARIABLE: APP_ROLE}.get(variable, OWNER_ROLE)
    for name, wert in gueltig.items():
        monkeypatch.setenv(name, wert)
    monkeypatch.setenv(variable, f"postgresql+psycopg://{rolle}:ab@cd:GEHEIMTEIL@127.0.0.1/fm")
    with pytest.raises(SystemExit, match=variable) as fehler:
        main()
    assert "GEHEIMTEIL" not in str(fehler.value)
    assert fehler.value.__cause__ is None
    assert fehler.value.__suppress_context__


def test_verbindung_aus_kaputter_adresse_nennt_kein_passwort() -> None:
    with pytest.raises(ValueError, match="Adresse") as fehler:
        psycopg_verbindung("postgresql+psycopg://postgres:ab@cd:GEHEIMTEIL@127.0.0.1/postgres")
    assert "GEHEIMTEIL" not in str(fehler.value)
    assert fehler.value.__suppress_context__
