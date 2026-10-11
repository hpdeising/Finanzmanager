# SPDX-License-Identifier: AGPL-3.0-or-later
"""Zwei Transaktionen stornieren gleichzeitig dieselbe Buchung.

Höchstens ein Storno je Buchung trägt der eindeutige Index auf storno_von, nicht eine
Abfrage im Trigger. Die zweite Transaktion wartet deshalb auf die erste und scheitert
nach deren Commit.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.kern.ledger import PostingEingabe, StornoNichtMoeglichError, buche, storniere
from tests.datenbank import constraint_name, roh_buchung, sqlstate
from tests.kern.ledger.conftest import lege_konten_an


def test_doppeltes_storno_gleichzeitig(app_engine: Engine) -> None:
    with Session(app_engine) as sitzung:
        konten = lege_konten_an(sitzung)
        original = buche(
            sitzung,
            haushalt_id=konten.haushalt_id,
            art="test.zahlung",
            wertstellung=date(2024, 1, 15),
            postings=[
                PostingEingabe(konten.hauptforderung, Decimal(50)),
                PostingEingabe(konten.eroeffnung, Decimal(-50)),
            ],
        ).id
        sitzung.commit()

    with Session(app_engine) as erste, Session(app_engine) as zweite:
        storniere(erste, buchung_id=original)
        zweite.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError) as gewartet:
            roh_buchung(zweite, konten.haushalt_id, art="kern.storno", storno_von=original)
        assert sqlstate(gewartet.value) == "55P03"
        zweite.rollback()

        erste.commit()

        with pytest.raises(IntegrityError) as doppelt:
            roh_buchung(zweite, konten.haushalt_id, art="kern.storno", storno_von=original)
        assert (sqlstate(doppelt.value), constraint_name(doppelt.value)) == (
            "23505",
            "uq_buchung_storno_von",
        )
        zweite.rollback()

        with pytest.raises(StornoNichtMoeglichError, match="bereits storniert"):
            storniere(zweite, buchung_id=original)
