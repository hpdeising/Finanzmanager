# SPDX-License-Identifier: AGPL-3.0-or-later
"""PostgreSQL erzwingt Buchungsdatum, Kontosperre und Stornoschutz selbst (E-26 bis E-28).

Alle Tests schreiben per Roh-SQL am API vorbei und prüfen SQLSTATE und den Namen der
verletzten Regel. Die Kontosperre kennt kein Modul, nur Konto und Datum (E-17).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.datenbank import (
    constraint_name,
    pruefe_aufgeschobene,
    roh_buchung,
    roh_haushalt,
    roh_konto,
    roh_postings,
    roh_sperre,
    sqlstate,
)

STICHTAG = date(2024, 6, 30)
DAVOR = date(2024, 3, 1)
DANACH = date(2024, 8, 1)


@dataclass(frozen=True)
class RohKonten:
    haushalt_id: uuid.UUID
    a: uuid.UUID
    b: uuid.UUID
    c: uuid.UUID


@pytest.fixture
def k(session: Session) -> RohKonten:
    haushalt_id = roh_haushalt(session)
    return RohKonten(
        haushalt_id,
        roh_konto(session, haushalt_id),
        roh_konto(session, haushalt_id),
        roh_konto(session, haushalt_id),
    )


def erwarte(fehler: pytest.ExceptionInfo[BaseException], zustand: str, regel: str) -> None:
    assert (sqlstate(fehler.value), constraint_name(fehler.value)) == (zustand, regel)


def buchung_mit_postings(
    sitzung: Session,
    k: RohKonten,
    *,
    wertstellung: date,
    buchungsdatum: date | None = None,
    stornierbar: bool = True,
) -> uuid.UUID:
    buchung_id = roh_buchung(
        sitzung,
        k.haushalt_id,
        wertstellung=wertstellung,
        buchungsdatum=buchungsdatum,
        stornierbar=stornierbar,
    )
    roh_postings(sitzung, buchung_id, [(k.a, "10"), (k.b, "-10")])
    return buchung_id


# --- Buchungsdatum (E-26, E-27) -----------------------------------------------------------


def test_buchungsdatum_nicht_vor_wertstellung(session: Session, k: RohKonten) -> None:
    with pytest.raises(DBAPIError) as fehler:
        roh_buchung(session, k.haushalt_id, wertstellung=DANACH, buchungsdatum=DAVOR)
    erwarte(fehler, "23514", "ck_buchung_buchungsdatum_nicht_vor_wertstellung")


def test_buchungsdatum_ist_pflicht(session: Session, k: RohKonten) -> None:
    with pytest.raises(DBAPIError) as fehler:
        session.execute(
            text(
                "INSERT INTO buchung (haushalt_id, art, wertstellung)"
                " VALUES (:h, 'test.buchung', :w)"
            ),
            {"h": k.haushalt_id, "w": DAVOR},
        )
    assert sqlstate(fehler.value) == "23502"


def test_stornierbar_ist_ohne_angabe_wahr(session: Session, k: RohKonten) -> None:
    buchung_id = session.execute(
        text(
            "INSERT INTO buchung (haushalt_id, art, wertstellung, buchungsdatum)"
            " VALUES (:h, 'test.buchung', :w, :w) RETURNING id"
        ),
        {"h": k.haushalt_id, "w": DAVOR},
    ).scalar_one()
    stornierbar = session.execute(
        text("SELECT stornierbar FROM buchung WHERE id = :id"), {"id": buchung_id}
    ).scalar_one()
    assert stornierbar is True


# --- Kontosperre (E-27) ------------------------------------------------------------------


@pytest.mark.parametrize("buchungsdatum", [DAVOR, STICHTAG], ids=["davor", "am_sperrdatum"])
def test_posting_bis_zum_sperrdatum_wird_abgelehnt(
    session: Session, k: RohKonten, buchungsdatum: date
) -> None:
    roh_sperre(session, k.a, STICHTAG)
    buchung_id = roh_buchung(
        session, k.haushalt_id, wertstellung=DAVOR, buchungsdatum=buchungsdatum
    )
    with pytest.raises(DBAPIError) as fehler:
        roh_postings(session, buchung_id, [(k.a, "10")])
    erwarte(fehler, "23514", "posting_konto_gesperrt")


def test_nachtraegliche_buchung_mit_spaeterem_buchungsdatum(session: Session, k: RohKonten) -> None:
    """E-26: Wertstellung im gesperrten Zeitraum, Buchungsdatum danach – zulässig."""
    roh_sperre(session, k.a, STICHTAG)
    buchung_mit_postings(session, k, wertstellung=DAVOR, buchungsdatum=DANACH)
    pruefe_aufgeschobene(session)


def test_sperre_gilt_nur_fuer_das_gesperrte_konto(session: Session, k: RohKonten) -> None:
    roh_sperre(session, k.c, STICHTAG)
    buchung_mit_postings(session, k, wertstellung=DAVOR)
    pruefe_aufgeschobene(session)


def test_buchung_ueber_gesperrtes_und_offenes_konto_scheitert(
    session: Session, k: RohKonten
) -> None:
    roh_sperre(session, k.b, STICHTAG)
    buchung_id = roh_buchung(session, k.haushalt_id, wertstellung=DAVOR)
    roh_postings(session, buchung_id, [(k.a, "10")])
    with pytest.raises(DBAPIError) as fehler:
        roh_postings(session, buchung_id, [(k.b, "-10")])
    erwarte(fehler, "23514", "posting_konto_gesperrt")


def test_sperre_gilt_auch_fuer_ein_storno(app_engine: Engine) -> None:
    with Session(app_engine) as sitzung:
        haushalt_id = roh_haushalt(sitzung)
        k = RohKonten(
            haushalt_id,
            roh_konto(sitzung, haushalt_id),
            roh_konto(sitzung, haushalt_id),
            roh_konto(sitzung, haushalt_id),
        )
        original = buchung_mit_postings(sitzung, k, wertstellung=DAVOR)
        roh_sperre(sitzung, k.a, STICHTAG)
        sitzung.commit()

        storno = roh_buchung(
            sitzung, haushalt_id, art="kern.storno", wertstellung=DAVOR, storno_von=original
        )
        with pytest.raises(DBAPIError) as fehler:
            roh_postings(sitzung, storno, [(k.a, "-10")])
        erwarte(fehler, "23514", "posting_konto_gesperrt")
        sitzung.rollback()

        # Mit dem Tag der Erfassung nach dem Sperrdatum (E-26) geht es.
        storno = roh_buchung(
            sitzung,
            haushalt_id,
            art="kern.storno",
            wertstellung=DAVOR,
            buchungsdatum=DANACH,
            storno_von=original,
        )
        roh_postings(sitzung, storno, [(k.a, "-10"), (k.b, "10")])
        sitzung.commit()


def test_sperrdatum_steigt_nur(session: Session, k: RohKonten) -> None:
    roh_sperre(session, k.a, STICHTAG)
    for frueher in (STICHTAG, DAVOR):
        with pytest.raises(DBAPIError) as fehler, session.begin_nested():
            roh_sperre(session, k.a, frueher)
        erwarte(fehler, "23514", "konto_sperre_steigt")
    roh_sperre(session, k.a, DANACH)
    bis = session.execute(
        text("SELECT max(gesperrt_bis) FROM konto_sperre WHERE konto_id = :k"), {"k": k.a}
    ).scalar_one()
    assert bis == DANACH


def test_sperre_nur_fuer_vorhandene_konten(session: Session) -> None:
    with pytest.raises(DBAPIError) as fehler:
        roh_sperre(session, uuid.uuid4(), STICHTAG)
    assert sqlstate(fehler.value) == "23503"


def test_erfasst_am_der_sperre_setzt_die_datenbank(session: Session, k: RohKonten) -> None:
    session.execute(
        text(
            "INSERT INTO konto_sperre (konto_id, gesperrt_bis, erfasst_am) VALUES (:k, :bis, :am)"
        ),
        {"k": k.a, "bis": STICHTAG, "am": datetime.fromisoformat("2000-01-01T00:00:00+00:00")},
    )
    erfasst_am, jetzt = session.execute(
        text("SELECT erfasst_am, now() FROM konto_sperre WHERE konto_id = :k"), {"k": k.a}
    ).one()
    assert erfasst_am == jetzt


@pytest.mark.parametrize(
    "anweisung",
    [
        "UPDATE konto_sperre SET gesperrt_bis = '2000-01-01'",
        "DELETE FROM konto_sperre",
        "TRUNCATE konto_sperre",
    ],
)
def test_sperren_sind_unveraenderlich(owner_session: Session, anweisung: str) -> None:
    """Auch die Eigentümerrolle ändert keine Sperre; die Laufzeitrolle darf es ohnehin nicht."""
    haushalt_id = roh_haushalt(owner_session)
    roh_sperre(owner_session, roh_konto(owner_session, haushalt_id), STICHTAG)
    with pytest.raises(DBAPIError) as fehler:
        owner_session.execute(text(anweisung))
    erwarte(fehler, "23001", "konto_sperre_unveraenderlich")


# --- Stornoschutz (E-28) -----------------------------------------------------------------


def test_nicht_stornierbare_buchung(session: Session, k: RohKonten) -> None:
    original = buchung_mit_postings(session, k, wertstellung=DAVOR, stornierbar=False)
    with pytest.raises(DBAPIError) as fehler:
        roh_buchung(
            session, k.haushalt_id, art="kern.storno", wertstellung=DAVOR, storno_von=original
        )
    erwarte(fehler, "23514", "storno_stornierbar")


def test_storno_nicht_vor_dem_buchungsdatum_des_originals(session: Session, k: RohKonten) -> None:
    original = buchung_mit_postings(session, k, wertstellung=DAVOR, buchungsdatum=DANACH)
    with pytest.raises(DBAPIError) as fehler:
        roh_buchung(
            session,
            k.haushalt_id,
            art="kern.storno",
            wertstellung=DAVOR,
            buchungsdatum=STICHTAG,
            storno_von=original,
        )
    erwarte(fehler, "23514", "storno_buchungsdatum")


@pytest.mark.parametrize("buchungsdatum", [DANACH, date(2024, 9, 1)], ids=["gleich", "spaeter"])
def test_storno_am_oder_nach_dem_buchungsdatum_des_originals(
    session: Session, k: RohKonten, buchungsdatum: date
) -> None:
    original = buchung_mit_postings(session, k, wertstellung=DAVOR, buchungsdatum=DANACH)
    storno = roh_buchung(
        session,
        k.haushalt_id,
        art="kern.storno",
        wertstellung=DAVOR,
        buchungsdatum=buchungsdatum,
        storno_von=original,
    )
    roh_postings(session, storno, [(k.a, "-10"), (k.b, "10")])
    pruefe_aufgeschobene(session)


# --- Nur READ COMMITTED (Fachkonzept 4.4) --------------------------------------------------


@pytest.mark.parametrize("stufe", ["REPEATABLE READ", "SERIALIZABLE"])
def test_posting_nur_in_read_committed(app_engine: Engine, stufe: str) -> None:
    with Session(app_engine) as vorbereitung:
        haushalt_id = roh_haushalt(vorbereitung)
        konto_a, konto_b = (
            roh_konto(vorbereitung, haushalt_id),
            roh_konto(vorbereitung, haushalt_id),
        )
        vorbereitung.commit()
    with Session(app_engine) as sitzung:
        sitzung.execute(text(f"SET TRANSACTION ISOLATION LEVEL {stufe}"))
        buchung_id = roh_buchung(sitzung, haushalt_id)
        with pytest.raises(DBAPIError) as fehler:
            roh_postings(sitzung, buchung_id, [(konto_a, "1"), (konto_b, "-1")])
        erwarte(fehler, "25000", "nur_read_committed")


@pytest.mark.parametrize("stufe", ["REPEATABLE READ", "SERIALIZABLE"])
def test_sperre_nur_in_read_committed(app_engine: Engine, stufe: str) -> None:
    with Session(app_engine) as vorbereitung:
        konto = roh_konto(vorbereitung, roh_haushalt(vorbereitung))
        vorbereitung.commit()
    with Session(app_engine) as sitzung:
        sitzung.execute(text(f"SET TRANSACTION ISOLATION LEVEL {stufe}"))
        with pytest.raises(DBAPIError) as fehler:
            roh_sperre(sitzung, konto, STICHTAG)
        erwarte(fehler, "25000", "nur_read_committed")
    with Session(app_engine) as sitzung:
        sitzung.execute(text(f"SET TRANSACTION ISOLATION LEVEL {stufe}"))
        with pytest.raises(DBAPIError) as fehler:
            sitzung.execute(text("SELECT public.ledger_halte_konto(:k)"), {"k": konto})
        erwarte(fehler, "25000", "nur_read_committed")
