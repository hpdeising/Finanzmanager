# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gleichzeitige Transaktionen.

- Zwei Transaktionen stornieren dieselbe Buchung: Höchstens ein Storno je Buchung trägt der
  eindeutige Index auf storno_von, nicht eine Abfrage im Trigger. Die zweite Transaktion
  wartet deshalb auf die erste und scheitert nach deren Commit.
- Kontosperre und Posting (Fachkonzept 4.4, E-27): Läuft eine Transaktion, die ein Konto
  sperrt, gleichzeitig mit einer, die darauf bucht, scheitert die zweite sofort, ohne zu
  warten. Die Kern-API meldet das als KontoBelegtError; der Aufrufer rollt zurück und
  versucht es erneut.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.kern.ledger import (
    KontoBelegtError,
    KontoGesperrtError,
    PostingEingabe,
    StornoNichtMoeglichError,
    buche,
    halte_konten,
    sperre_konten,
    storniere,
)
from tests.datenbank import constraint_name, roh_buchung, roh_postings, sqlstate
from tests.kern.ledger.conftest import Konten, lege_konten_an

STICHTAG = date(2024, 6, 30)


def committete_konten(app_engine: Engine) -> Konten:
    with Session(app_engine) as sitzung:
        konten = lege_konten_an(sitzung)
        sitzung.commit()
    return konten


def zahlung(sitzung: Session, konten: Konten, wertstellung: date = date(2024, 3, 1)) -> uuid.UUID:
    return buche(
        sitzung,
        haushalt_id=konten.haushalt_id,
        art="test.zahlung",
        wertstellung=wertstellung,
        postings=[
            PostingEingabe(konten.hauptforderung, Decimal(5)),
            PostingEingabe(konten.eroeffnung, Decimal(-5)),
        ],
    ).id


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


# --- Kontosperre und Posting ---------------------------------------------------------------


def test_sperre_laeuft_buchung_scheitert_sofort(app_engine: Engine) -> None:
    konten = committete_konten(app_engine)
    with Session(app_engine) as sperrend, Session(app_engine) as buchend:
        sperre_konten(sperrend, konto_ids=[konten.hauptforderung], bis=STICHTAG)
        # Ohne Wartezeit: Ein lock_timeout würde ein Warten als 55P03 sichtbar machen.
        buchend.execute(text("SET LOCAL lock_timeout = '5s'"))
        with pytest.raises(KontoBelegtError, match="erneut versuchen") as fehler:
            zahlung(buchend, konten, wertstellung=date(2024, 8, 1))
        assert fehler.value.__cause__ is not None
        assert sqlstate(fehler.value.__cause__) == "55P03"
        buchend.rollback()

        sperrend.commit()

        # Nach dem Commit der Sperre gilt sie: in den gesperrten Zeitraum nicht mehr …
        with pytest.raises(KontoGesperrtError):
            zahlung(buchend, konten, wertstellung=date(2024, 3, 1))
        # … danach schon.
        zahlung(buchend, konten, wertstellung=date(2024, 8, 1))
        buchend.commit()


def test_buchung_laeuft_sperre_scheitert_sofort(app_engine: Engine) -> None:
    konten = committete_konten(app_engine)
    with Session(app_engine) as buchend, Session(app_engine) as sperrend:
        zahlung(buchend, konten)
        with pytest.raises(KontoBelegtError, match="erneut versuchen") as fehler:
            sperre_konten(sperrend, konto_ids=[konten.hauptforderung], bis=STICHTAG)
        assert fehler.value.__cause__ is not None
        assert sqlstate(fehler.value.__cause__) == "55P03"
        sperrend.rollback()

        buchend.commit()

        # Die Buchung ist vor der Sperre committet und liegt danach im gesperrten Zeitraum.
        sperre_konten(sperrend, konto_ids=[konten.hauptforderung], bis=STICHTAG)
        sperrend.commit()


def test_halte_konten_friert_die_postings_ein(app_engine: Engine) -> None:
    """Die Festschreibung hält die Konten, bevor sie rechnet (Kap. 5.2 Schritt 7)."""
    konten = committete_konten(app_engine)
    with Session(app_engine) as haltend, Session(app_engine) as buchend:
        halte_konten(haltend, konto_ids=[konten.hauptforderung, konten.eroeffnung])
        with pytest.raises(KontoBelegtError):
            zahlung(buchend, konten)
        buchend.rollback()

        haltend.rollback()

        zahlung(buchend, konten)
        buchend.commit()


def test_halte_konten_scheitert_bei_laufender_buchung(app_engine: Engine) -> None:
    konten = committete_konten(app_engine)
    with Session(app_engine) as buchend, Session(app_engine) as haltend:
        zahlung(buchend, konten)
        with pytest.raises(KontoBelegtError):
            halte_konten(haltend, konto_ids=[konten.eroeffnung])
        haltend.rollback()
        buchend.rollback()


def test_zwei_buchungen_auf_dasselbe_konto_gleichzeitig(app_engine: Engine) -> None:
    """Gewöhnliche Buchungen halten das Konto nur gemeinsam und behindern sich nicht."""
    konten = committete_konten(app_engine)
    with Session(app_engine) as erste, Session(app_engine) as zweite:
        zahlung(erste, konten)
        zahlung(zweite, konten)
        erste.commit()
        zweite.commit()


def test_committete_sperre_gilt_in_laufender_transaktion(app_engine: Engine) -> None:
    """READ COMMITTED: Der Trigger liest das Sperrdatum erst nach seiner Advisory-Sperre."""
    konten = committete_konten(app_engine)
    with Session(app_engine) as buchend, Session(app_engine) as sperrend:
        buchend.execute(text("SELECT 1"))  # Transaktion läuft schon
        sperre_konten(sperrend, konto_ids=[konten.hauptforderung], bis=STICHTAG)
        sperrend.commit()

        buchung_id = roh_buchung(buchend, konten.haushalt_id, wertstellung=date(2024, 3, 1))
        with pytest.raises(DBAPIError) as fehler:
            roh_postings(buchend, buchung_id, [(konten.hauptforderung, "5")])
        assert (sqlstate(fehler.value), constraint_name(fehler.value)) == (
            "23514",
            "posting_konto_gesperrt",
        )
        buchend.rollback()
