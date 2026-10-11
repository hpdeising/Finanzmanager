# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gemeinsame Fixtures für Tests gegen echtes PostgreSQL 16.

Fehlt ``FINANZMANAGER_TEST_ADMIN_DATABASE_URL``, schlagen alle Datenbanktests fehl; sie
werden nicht übersprungen (CLAUDE.md). Einrichtung: CONTRIBUTING.md, Abschnitt
„Test-Datenbank“.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import URL, Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from app.kern.db import erzeuge_engine
from app.kern.db.bootstrap import ADMIN_URL_VARIABLE, MIGRATION_URL_VARIABLE
from app.kern.db.engine import URL_VARIABLE
from tests.datenbank import (
    MINDESTVERSION,
    TEST_ADMIN_URL_VARIABLE,
    Sitzungsdatenbank,
    neue_testdatenbank,
    sitzung_mit_rollback,
)

# Tests dürfen nie eine echte Datenbank der Anwendung treffen.
for _variable in (URL_VARIABLE, MIGRATION_URL_VARIABLE, ADMIN_URL_VARIABLE):
    os.environ.pop(_variable, None)


@pytest.fixture(scope="session")
def admin_url() -> URL:
    """Superuser-Adresse des Test-Clusters; nur für Bootstrap und Superuser-Tests."""
    roh = os.environ.get(TEST_ADMIN_URL_VARIABLE)
    if not roh:
        pytest.fail(
            f"{TEST_ADMIN_URL_VARIABLE} fehlt. PostgreSQL 16 starten und die Variable setzen "
            "(CONTRIBUTING.md, Abschnitt „Test-Datenbank“). Datenbanktests werden nicht "
            "übersprungen (CLAUDE.md).",
            pytrace=False,
        )
    url = make_url(roh)
    pruef_engine = create_engine(url, hide_parameters=True)
    try:
        with pruef_engine.connect() as verbindung:
            version = int(verbindung.execute(text("SHOW server_version_num")).scalar_one())
    finally:
        pruef_engine.dispose()
    if version < MINDESTVERSION:
        pytest.fail(f"PostgreSQL ab 16 erforderlich, gefunden: {version}.", pytrace=False)
    return url


@pytest.fixture(scope="session")
def testdatenbank(admin_url: URL) -> Iterator[Sitzungsdatenbank]:
    with neue_testdatenbank(admin_url) as datenbank:
        yield datenbank


@pytest.fixture(scope="session")
def app_engine(testdatenbank: Sitzungsdatenbank) -> Iterator[Engine]:
    """Laufzeitrolle: so verbindet sich die Anwendung. Standard für Tests."""
    engine = erzeuge_engine(testdatenbank.app_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def owner_engine(testdatenbank: Sitzungsdatenbank) -> Iterator[Engine]:
    """Eigentümerrolle: nur für Tests, die das Verhalten der Trigger gegenüber ihr prüfen."""
    engine = erzeuge_engine(testdatenbank.owner_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def superuser_engine(testdatenbank: Sitzungsdatenbank) -> Iterator[Engine]:
    """Superuser auf der Sitzungsdatenbank: nur für den Nachweis von ENABLE ALWAYS."""
    engine = erzeuge_engine(testdatenbank.admin_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(app_engine: Engine) -> Iterator[Session]:
    """Session der Laufzeitrolle; am Testende wird alles zurückgerollt."""
    with sitzung_mit_rollback(app_engine) as sitzung:
        yield sitzung


@pytest.fixture
def owner_session(owner_engine: Engine) -> Iterator[Session]:
    with sitzung_mit_rollback(owner_engine) as sitzung:
        yield sitzung
