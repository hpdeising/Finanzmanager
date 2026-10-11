# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alembic-Umgebung.

Migrationen laufen mit der Eigentümerrolle (Fachkonzept 11.1, E-19). Die Adresse kommt aus
``FINANZMANAGER_MIGRATION_DATABASE_URL`` oder, in Tests, als offene Verbindung über
``config.attributes["connection"]``; eine übergebene Verbindung hat Vorrang. Offline-
Migrationen (``--sql``) sind nicht vorgesehen.
"""

import os

from alembic import context
from sqlalchemy import Connection

from app.kern.db import Basis, erzeuge_engine
from app.kern.db.bootstrap import MIGRATION_URL_VARIABLE
from app.kern.haushalt import Haushalt
from app.kern.ledger import Buchung, Konto, Posting

# Der Import registriert die Tabellen in Basis.metadata; der Vergleich von Modellen und
# Migration (tests/migrations) braucht sie.
MODELLE = (Haushalt, Konto, Buchung, Posting)


def _migriere(verbindung: Connection) -> None:
    context.configure(connection=verbindung, target_metadata=Basis.metadata)
    with context.begin_transaction():
        context.run_migrations()


def _starte() -> None:
    if context.is_offline_mode():
        msg = "Offline-Migrationen (--sql) sind nicht vorgesehen."
        raise RuntimeError(msg)
    uebergeben = context.config.attributes.get("connection")
    if isinstance(uebergeben, Connection):
        _migriere(uebergeben)
        return
    url = os.environ.get(MIGRATION_URL_VARIABLE)
    if not url:
        msg = f"Umgebungsvariable {MIGRATION_URL_VARIABLE} ist nicht gesetzt."
        raise RuntimeError(msg)
    engine = erzeuge_engine(url)
    try:
        with engine.begin() as verbindung:
            _migriere(verbindung)
    finally:
        engine.dispose()


_starte()
