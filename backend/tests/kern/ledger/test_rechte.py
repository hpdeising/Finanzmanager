# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rechte der Laufzeitrolle (Fachkonzept 11.1, E-19).

Die Anwendung verbindet sich mit der Laufzeitrolle. Sie darf auf buchung und posting nur
lesen und einfügen und kann die Trigger nicht abschalten. Das schützt gegen eigenen Code,
der Buchungen ändern will; gegen den Superuser schützt es nicht und soll es nicht.
"""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.datenbank import sqlstate

UNZULAESSIG = [
    "UPDATE buchung SET text = 'korrigiert'",
    "DELETE FROM buchung",
    "TRUNCATE buchung",
    "UPDATE posting SET betrag = 1",
    "DELETE FROM posting",
    "TRUNCATE posting",
    "UPDATE konto SET rolle = 'test.anders'",
    "DELETE FROM konto",
    "DELETE FROM haushalt",
    "ALTER TABLE buchung DISABLE TRIGGER buchung_pruefen",
    "ALTER TABLE posting DISABLE TRIGGER ALL",
    "ALTER TABLE posting ENABLE REPLICA TRIGGER posting_pruefen",
    "DROP TRIGGER posting_vor_insert ON posting",
    "ALTER TABLE posting DROP CONSTRAINT ck_posting_betrag_ungleich_null",
    "SET session_replication_role = replica",
    "CREATE OR REPLACE FUNCTION public.ledger_unveraenderlich() RETURNS trigger"
    " LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$",
    "CREATE TEMP TABLE schatten (wert integer)",
    "CREATE TABLE neu (wert integer)",
]


@pytest.mark.parametrize("anweisung", UNZULAESSIG)
def test_laufzeitrolle_darf_das_nicht(app_engine: Engine, anweisung: str) -> None:
    with app_engine.connect() as verbindung, pytest.raises(DBAPIError) as fehler:
        verbindung.execute(text(anweisung))
    assert sqlstate(fehler.value) == "42501"


@pytest.mark.parametrize("tabelle", ["haushalt", "konto", "buchung", "posting"])
def test_laufzeitrolle_darf_lesen_und_einfuegen(app_engine: Engine, tabelle: str) -> None:
    with app_engine.connect() as verbindung:
        rechte = verbindung.execute(
            text(
                "SELECT has_table_privilege(current_user, :t, 'SELECT'),"
                " has_table_privilege(current_user, :t, 'INSERT')"
            ),
            {"t": f"public.{tabelle}"},
        ).one()
    assert tuple(rechte) == (True, True)
