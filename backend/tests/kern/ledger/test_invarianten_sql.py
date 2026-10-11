# SPDX-License-Identifier: AGPL-3.0-or-later
"""PostgreSQL erzwingt die Invarianten selbst (Fachkonzept 4.4, CLAUDE.md, Buchungen).

Alle Tests schreiben per Roh-SQL am API vorbei. Geprüft wird jeweils SQLSTATE und der
Name der verletzten Regel. Im ``pytest.raises``-Block steht nur die Anweisung, die den
Fehler auslösen soll; so zeigt jeder Test zugleich, dass die Prüfung zurückgestellt ist.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.kern.db.bootstrap import psycopg_verbindung
from tests.datenbank import (
    WERTSTELLUNG,
    Sitzungsdatenbank,
    constraint_name,
    pruefe_aufgeschobene,
    roh_buchung,
    roh_haushalt,
    roh_konto,
    roh_postings,
    sitzung_mit_rollback,
    sqlstate,
)


@dataclass(frozen=True)
class RohKonten:
    haushalt_id: uuid.UUID
    a: uuid.UUID
    b: uuid.UUID
    c: uuid.UUID


def roh_konten(sitzung: Session) -> RohKonten:
    haushalt_id = roh_haushalt(sitzung)
    return RohKonten(
        haushalt_id,
        roh_konto(sitzung, haushalt_id),
        roh_konto(sitzung, haushalt_id),
        roh_konto(sitzung, haushalt_id),
    )


@pytest.fixture
def k(session: Session) -> RohKonten:
    return roh_konten(session)


def committete_buchung(engine: Engine) -> tuple[RohKonten, uuid.UUID]:
    """Eine gültige Buchung in einer eigenen, abgeschlossenen Transaktion."""
    with Session(engine) as sitzung:
        konten = roh_konten(sitzung)
        buchung_id = roh_buchung(sitzung, konten.haushalt_id)
        roh_postings(sitzung, buchung_id, [(konten.a, "10.00"), (konten.b, "-10.00")])
        sitzung.commit()
    return konten, buchung_id


def erwarte(fehler: pytest.ExceptionInfo[BaseException], zustand: str, regel: str) -> None:
    assert (sqlstate(fehler.value), constraint_name(fehler.value)) == (zustand, regel)


# --- Zurückgestellte Prüfungen je Buchung -------------------------------------------------


def test_gueltige_buchung_aus_getrennten_anweisungen(session: Session, k: RohKonten) -> None:
    buchung_id = roh_buchung(session, k.haushalt_id)
    roh_postings(session, buchung_id, [(k.a, "7.5"), (k.b, "-2.5"), (k.c, "-5")])
    pruefe_aufgeschobene(session)


def test_buchung_ohne_postings(session: Session, k: RohKonten) -> None:
    roh_buchung(session, k.haushalt_id)
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "buchung_mindestens_zwei_postings")


def test_buchung_mit_einem_posting(session: Session, k: RohKonten) -> None:
    buchung_id = roh_buchung(session, k.haushalt_id)
    roh_postings(session, buchung_id, [(k.a, "10")])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "buchung_mindestens_zwei_postings")


def test_alle_postings_auf_einem_konto(session: Session, k: RohKonten) -> None:
    buchung_id = roh_buchung(session, k.haushalt_id)
    roh_postings(session, buchung_id, [(k.a, "5"), (k.a, "-5")])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "buchung_mindestens_zwei_konten")


def test_summe_ungleich_null(session: Session, k: RohKonten) -> None:
    buchung_id = roh_buchung(session, k.haushalt_id)
    roh_postings(session, buchung_id, [(k.a, "10.0001"), (k.b, "-10.0000")])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "buchung_summe_null")


def test_summe_wird_je_buchung_geprueft(session: Session, k: RohKonten) -> None:
    """Zwei unausgeglichene Buchungen gleichen sich zusammen aus; das genügt nicht."""
    erste = roh_buchung(session, k.haushalt_id)
    zweite = roh_buchung(session, k.haushalt_id)
    roh_postings(session, erste, [(k.a, "10"), (k.b, "-9")])
    roh_postings(session, zweite, [(k.a, "-1"), (k.c, "0.5"), (k.b, "0.5")])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "buchung_summe_null")


def test_konto_eines_anderen_haushalts(session: Session, k: RohKonten) -> None:
    fremd = roh_konten(session)
    buchung_id = roh_buchung(session, k.haushalt_id)
    roh_postings(session, buchung_id, [(k.a, "10"), (fremd.a, "-10")])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "buchung_ein_haushalt")


def test_alle_konten_in_einem_anderen_haushalt(session: Session, k: RohKonten) -> None:
    fremd = roh_konten(session)
    buchung_id = roh_buchung(session, k.haushalt_id)
    roh_postings(session, buchung_id, [(fremd.a, "10"), (fremd.b, "-10")])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "buchung_ein_haushalt")


def test_posting_ueber_null_scheitert_sofort(session: Session, k: RohKonten) -> None:
    buchung_id = roh_buchung(session, k.haushalt_id)
    with pytest.raises(IntegrityError) as fehler:
        roh_postings(session, buchung_id, [(k.a, "0")])
    erwarte(fehler, "23514", "ck_posting_betrag_ungleich_null")


def test_posting_nach_vorgezogener_pruefung(session: Session, k: RohKonten) -> None:
    """Jedes Posting stößt die Prüfung seiner Buchung erneut an, nicht nur deren INSERT."""
    buchung_id = roh_buchung(session, k.haushalt_id)
    roh_postings(session, buchung_id, [(k.a, "10"), (k.b, "-10")])
    pruefe_aufgeschobene(session)
    roh_postings(session, buchung_id, [(k.c, "5")])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "buchung_summe_null")


def test_fremdes_konto_nach_vorgezogener_pruefung(session: Session, k: RohKonten) -> None:
    fremd = roh_konten(session)
    buchung_id = roh_buchung(session, k.haushalt_id)
    roh_postings(session, buchung_id, [(k.a, "10"), (k.b, "-10")])
    pruefe_aufgeschobene(session)
    roh_postings(session, buchung_id, [(fremd.a, "5"), (k.a, "-5")])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "buchung_ein_haushalt")


def test_commit_einer_unausgeglichenen_buchung(app_engine: Engine) -> None:
    """Beim echten COMMIT scheitert die ganze Transaktion, auch die gültige Buchung darin."""
    with Session(app_engine) as sitzung:
        konten = roh_konten(sitzung)
        gueltig = roh_buchung(sitzung, konten.haushalt_id)
        roh_postings(sitzung, gueltig, [(konten.a, "1"), (konten.b, "-1")])
        ungueltig = roh_buchung(sitzung, konten.haushalt_id)
        roh_postings(sitzung, ungueltig, [(konten.a, "1"), (konten.b, "-2")])
        with pytest.raises(IntegrityError) as fehler:
            sitzung.commit()
    erwarte(fehler, "23514", "buchung_summe_null")
    with Session(app_engine) as sitzung:
        anzahl = sitzung.execute(
            text("SELECT count(*) FROM buchung WHERE id IN (:gueltig, :ungueltig)"),
            {"gueltig": gueltig, "ungueltig": ungueltig},
        ).scalar_one()
    assert anzahl == 0


# --- Postings nur in der Transaktion ihrer Buchung --------------------------------------
# Die Datenbank vergleicht buchung.erfasst_txid mit pg_current_xact_id() (Fachkonzept 4.4).


def test_postings_an_eine_abgeschlossene_buchung(app_engine: Engine) -> None:
    """Ein ausgeglichenes Paar ließe Summe und Anzahl unberührt und änderte doch die Buchung."""
    konten, buchung_id = committete_buchung(app_engine)
    with Session(app_engine) as sitzung, pytest.raises(IntegrityError) as fehler:
        roh_postings(sitzung, buchung_id, [(konten.c, "5"), (konten.a, "-5")])
    erwarte(fehler, "23001", "buchung_abgeschlossen")


def test_postings_an_ein_storniertes_original(app_engine: Engine) -> None:
    konten, original = committete_buchung(app_engine)
    with Session(app_engine) as sitzung:
        storno = roh_buchung(sitzung, konten.haushalt_id, art="kern.storno", storno_von=original)
        roh_postings(sitzung, storno, [(konten.a, "-10.00"), (konten.b, "10.00")])
        sitzung.commit()
    with Session(app_engine) as sitzung, pytest.raises(IntegrityError) as fehler:
        roh_postings(sitzung, original, [(konten.c, "700"), (konten.b, "-700")])
    erwarte(fehler, "23001", "buchung_abgeschlossen")


def test_mehrere_transaktionen_in_einer_nachricht(
    app_engine: Engine, testdatenbank: Sitzungsdatenbank
) -> None:
    """Fund der Code-Prüfung, nachgestellt: buchen, stornieren, Postings an das Original hängen.

    Alle drei Transaktionen stehen in einer Client-Nachricht und haben deshalb denselben
    now(). Die frühere Sperre (Liste per set_config und erfasst_am = now()) ließ die dritte
    durch, weil die Laufzeitrolle die Liste selbst setzen kann. Die Transaktionsnummer
    unterscheidet die drei Transaktionen.
    """
    with Session(app_engine) as sitzung:
        konten = roh_konten(sitzung)
        sitzung.commit()
    original, storno = uuid.uuid4(), uuid.uuid4()
    neue_buchung = sql.SQL(
        "INSERT INTO buchung (id, haushalt_id, art, wertstellung, storno_von)"
        " VALUES ({}, {}, {}, DATE '2024-01-15', {})"
    )
    paar = sql.SQL(
        "INSERT INTO posting (buchung_id, konto_id, betrag) VALUES ({}, {}, {}), ({}, {}, {})"
    )

    def postings(
        buchung_id: uuid.UUID, soll: uuid.UUID, haben: uuid.UUID, wert: int
    ) -> sql.Composed:
        return paar.format(*map(sql.Literal, (buchung_id, soll, wert, buchung_id, haben, -wert)))

    h = sql.Literal(konten.haushalt_id)
    nachricht = sql.SQL("; ").join(
        [
            sql.SQL("BEGIN"),
            neue_buchung.format(sql.Literal(original), h, sql.Literal("test.buchung"), sql.NULL),
            postings(original, konten.a, konten.b, 10),
            sql.SQL("COMMIT"),
            sql.SQL("BEGIN"),
            neue_buchung.format(
                sql.Literal(storno), h, sql.Literal("kern.storno"), sql.Literal(original)
            ),
            postings(storno, konten.b, konten.a, 10),
            sql.SQL("COMMIT"),
            sql.SQL("BEGIN"),
            sql.SQL("SELECT set_config('finanzmanager.neue_buchungen', {}, true)").format(
                sql.Literal(f",{original},")
            ),
            postings(original, konten.c, konten.b, 700),
            sql.SQL("COMMIT"),
        ]
    )
    with (
        psycopg_verbindung(testdatenbank.app_url, autocommit=True) as verbindung,
        pytest.raises(psycopg.IntegrityError) as fehler,
    ):
        verbindung.execute(nachricht)
    erwarte(fehler, "23001", "buchung_abgeschlossen")
    with Session(app_engine) as sitzung:
        anzahl = sitzung.execute(
            text("SELECT count(*) FROM posting WHERE buchung_id IN (:original, :storno)"),
            {"original": original, "storno": storno},
        ).scalar_one()
    assert anzahl == 4


def test_postings_an_die_offene_buchung_einer_anderen_transaktion(app_engine: Engine) -> None:
    """Fund der Code-Prüfung: Eine noch unsichtbare Buchung darf nicht durchrutschen.

    Vorher ließ der Trigger ein Posting durch, wenn er die Buchung nicht fand, und verließ
    sich auf den Fremdschlüssel. Der prüft nur, dass die Buchung am Ende der Anweisung
    existiert; committet die andere Transaktion rechtzeitig, hinge das Posting an ihr.
    """
    with Session(app_engine) as sitzung:
        konten = roh_konten(sitzung)
        sitzung.commit()
    with Session(app_engine) as erste, Session(app_engine) as zweite:
        buchung_id = roh_buchung(erste, konten.haushalt_id)
        roh_postings(erste, buchung_id, [(konten.a, "10"), (konten.b, "-10")])
        zweite.execute(text("SET LOCAL lock_timeout = '2s'"))
        with pytest.raises(IntegrityError) as fehler:
            roh_postings(zweite, buchung_id, [(konten.c, "5"), (konten.a, "-5")])
        erste.rollback()
    erwarte(fehler, "23001", "buchung_abgeschlossen")


def test_postings_nach_einem_savepoint(session: Session, k: RohKonten) -> None:
    """Savepoints (z. B. begin_nested) stören nicht; es zählt die Transaktion."""
    with session.begin_nested():
        buchung_id = roh_buchung(session, k.haushalt_id)
    with session.begin_nested():
        roh_postings(session, buchung_id, [(k.a, "3"), (k.b, "-3")])
    pruefe_aufgeschobene(session)


def test_postings_nach_savepoint_mit_roh_sql(session: Session, k: RohKonten) -> None:
    session.execute(text("SAVEPOINT erster"))
    buchung_id = roh_buchung(session, k.haushalt_id)
    session.execute(text("RELEASE SAVEPOINT erster"))
    session.execute(text("SAVEPOINT zweiter"))
    roh_postings(session, buchung_id, [(k.a, "3"), (k.b, "-3")])
    session.execute(text("RELEASE SAVEPOINT zweiter"))
    pruefe_aufgeschobene(session)


def test_postings_an_eine_zurueckgerollte_buchung(session: Session, k: RohKonten) -> None:
    session.execute(text("SAVEPOINT vorher"))
    buchung_id = roh_buchung(session, k.haushalt_id)
    session.execute(text("ROLLBACK TO SAVEPOINT vorher"))
    with pytest.raises(IntegrityError) as fehler:
        roh_postings(session, buchung_id, [(k.a, "3"), (k.b, "-3")])
    erwarte(fehler, "23001", "buchung_abgeschlossen")


def test_buchung_und_postings_in_einer_anweisung(session: Session, k: RohKonten) -> None:
    """Eine Anweisung gehört zu einer Transaktion; die Buchung entsteht vor ihren Postings."""
    buchung_id = (
        session.execute(
            text(
                "WITH b AS (INSERT INTO buchung (haushalt_id, art, wertstellung)"
                " VALUES (:h, 'test.buchung', DATE '2024-01-15') RETURNING id)"
                " INSERT INTO posting (buchung_id, konto_id, betrag)"
                " SELECT b.id, p.konto_id, p.betrag FROM b,"
                " (VALUES (CAST(:a AS uuid), 10), (CAST(:b AS uuid), -10)) AS p (konto_id, betrag)"
                " RETURNING buchung_id"
            ),
            {"h": k.haushalt_id, "a": k.a, "b": k.b},
        )
        .scalars()
        .first()
    )
    assert buchung_id is not None
    pruefe_aufgeschobene(session)


def test_postings_vor_ihrer_buchung_in_einer_anweisung(session: Session, k: RohKonten) -> None:
    """Das Posting findet seine Buchung noch nicht und wird abgelehnt."""
    with pytest.raises(IntegrityError) as fehler:
        session.execute(
            text(
                "WITH p AS (INSERT INTO posting (buchung_id, konto_id, betrag)"
                " VALUES (:id, :a, 10), (:id, :b, -10) RETURNING buchung_id)"
                " INSERT INTO buchung (id, haushalt_id, art, wertstellung)"
                " SELECT DISTINCT p.buchung_id, CAST(:h AS uuid), 'test.buchung',"
                " DATE '2024-01-15' FROM p"
            ),
            {"id": uuid.uuid4(), "h": k.haushalt_id, "a": k.a, "b": k.b},
        )
    erwarte(fehler, "23001", "buchung_abgeschlossen")


def test_erfasst_txid_vom_client_wird_ueberschrieben(session: Session, k: RohKonten) -> None:
    """Die Datenbank setzt die Transaktionsnummer selbst (Fachkonzept 4.4)."""
    eigene = session.execute(
        text(
            "INSERT INTO buchung (haushalt_id, art, wertstellung, erfasst_txid)"
            " VALUES (:h, 'test.buchung', DATE '2024-01-15', '1')"
            " RETURNING erfasst_txid = pg_current_xact_id()"
        ),
        {"h": k.haushalt_id},
    ).scalar_one()
    assert eigene is True


# --- Storno ----------------------------------------------------------------------------


def storno_szenario(sitzung: Session, k: RohKonten) -> uuid.UUID:
    original = roh_buchung(sitzung, k.haushalt_id)
    roh_postings(sitzung, original, [(k.a, "10"), (k.b, "-4"), (k.c, "-6")])
    return original


def test_gueltiges_storno(session: Session, k: RohKonten) -> None:
    original = storno_szenario(session, k)
    storno = roh_buchung(session, k.haushalt_id, art="kern.storno", storno_von=original)
    roh_postings(session, storno, [(k.c, "6"), (k.a, "-10"), (k.b, "4")])
    pruefe_aufgeschobene(session)


def test_zweites_storno(session: Session, k: RohKonten) -> None:
    original = storno_szenario(session, k)
    roh_buchung(session, k.haushalt_id, art="kern.storno", storno_von=original)
    with pytest.raises(IntegrityError) as fehler:
        roh_buchung(session, k.haushalt_id, art="kern.storno", storno_von=original)
    erwarte(fehler, "23505", "uq_buchung_storno_von")


def test_kein_storno_eines_stornos(session: Session, k: RohKonten) -> None:
    original = storno_szenario(session, k)
    storno = roh_buchung(session, k.haushalt_id, art="kern.storno", storno_von=original)
    with pytest.raises(IntegrityError) as fehler:
        roh_buchung(session, k.haushalt_id, art="kern.storno", storno_von=storno)
    erwarte(fehler, "23514", "storno_nicht_von_storno")


def test_storno_auf_sich_selbst(session: Session, k: RohKonten) -> None:
    eigene_id = uuid.uuid4()
    with pytest.raises(IntegrityError) as fehler:
        session.execute(
            text(
                "INSERT INTO buchung (id, haushalt_id, art, wertstellung, storno_von)"
                " VALUES (:id, :haushalt_id, 'kern.storno', '2024-01-15', :id)"
            ),
            {"id": eigene_id, "haushalt_id": k.haushalt_id},
        )
    erwarte(fehler, "23503", "storno_original")


def test_storno_einer_unbekannten_buchung(session: Session, k: RohKonten) -> None:
    with pytest.raises(IntegrityError) as fehler:
        roh_buchung(session, k.haushalt_id, art="kern.storno", storno_von=uuid.uuid4())
    erwarte(fehler, "23503", "storno_original")


def test_storno_in_einem_anderen_haushalt(session: Session, k: RohKonten) -> None:
    original = storno_szenario(session, k)
    fremd = roh_konten(session)
    with pytest.raises(IntegrityError) as fehler:
        roh_buchung(session, fremd.haushalt_id, art="kern.storno", storno_von=original)
    erwarte(fehler, "23514", "storno_gleicher_haushalt")


def test_storno_mit_anderer_wertstellung(session: Session, k: RohKonten) -> None:
    """E-18: Das Storno trägt die Wertstellung der Ursprungsbuchung."""
    original = storno_szenario(session, k)
    with pytest.raises(IntegrityError) as fehler:
        roh_buchung(
            session,
            k.haushalt_id,
            art="kern.storno",
            storno_von=original,
            wertstellung=date(2024, 2, 1),
        )
    erwarte(fehler, "23514", "storno_gleiche_wertstellung")


@pytest.mark.parametrize(
    "gegenbuchung",
    [
        [("a", "-10"), ("b", "5"), ("c", "5")],
        [("a", "-10"), ("b", "10")],
        [("a", "-10"), ("b", "4"), ("c", "6"), ("a", "1"), ("b", "-1")],
        [("a", "-5"), ("a", "-5"), ("b", "4"), ("c", "6")],
    ],
    ids=["andere-betraege", "anderes-konto", "zusaetzliches-paar", "aufgeteilt"],
)
def test_storno_muss_genau_spiegeln(
    session: Session, k: RohKonten, gegenbuchung: list[tuple[str, str]]
) -> None:
    """Ausgeglichen genügt nicht: Das Storno besteht genau aus den negierten Postings."""
    original = storno_szenario(session, k)
    storno = roh_buchung(session, k.haushalt_id, art="kern.storno", storno_von=original)
    konto = {"a": k.a, "b": k.b, "c": k.c}
    roh_postings(session, storno, [(konto[name], betrag) for name, betrag in gegenbuchung])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "storno_spiegelbildlich")


@pytest.mark.parametrize(
    ("original", "gegenbuchung"),
    [
        ([("a", "10"), ("b", "-10"), ("c", "5"), ("a", "-5")], [("a", "-10"), ("b", "10")]),
        ([("a", "5"), ("a", "5"), ("b", "-5"), ("b", "-5")], [("a", "-5"), ("b", "5")]),
    ],
    ids=["teilstorno", "doppelte-postings"],
)
def test_storno_negiert_alle_postings_des_originals(
    session: Session,
    k: RohKonten,
    original: list[tuple[str, str]],
    gegenbuchung: list[tuple[str, str]],
) -> None:
    """Auch die Gegenrichtung zählt: Jedes Posting des Originals braucht sein Gegenstück."""
    konto = {"a": k.a, "b": k.b, "c": k.c}
    original_id = roh_buchung(session, k.haushalt_id)
    roh_postings(session, original_id, [(konto[name], betrag) for name, betrag in original])
    storno = roh_buchung(session, k.haushalt_id, art="kern.storno", storno_von=original_id)
    roh_postings(session, storno, [(konto[name], betrag) for name, betrag in gegenbuchung])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "storno_spiegelbildlich")


def test_postings_am_original_nach_geprueftem_storno(session: Session, k: RohKonten) -> None:
    """Fund der Code-Prüfung: Auch neue Postings am Original prüfen die Spiegelung."""
    original = roh_buchung(session, k.haushalt_id)
    roh_postings(session, original, [(k.a, "10"), (k.b, "-10")])
    storno = roh_buchung(session, k.haushalt_id, art="kern.storno", storno_von=original)
    roh_postings(session, storno, [(k.a, "-10"), (k.b, "10")])
    pruefe_aufgeschobene(session)
    roh_postings(session, original, [(k.c, "990"), (k.b, "-990")])
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(session)
    erwarte(fehler, "23514", "storno_spiegelbildlich")


@pytest.mark.parametrize(
    ("art", "mit_original", "regel"),
    [
        ("kern.storno", False, "ck_buchung_storno_art"),
        ("test.buchung", True, "ck_buchung_storno_art"),
        *[
            (art, False, "ck_buchung_art_format")
            for art in [
                "zahlung",
                "Kern.zahlung",
                "kern.",
                ".x",
                "a.b.c",
                "kern.zahl-ung",
                "kern.x1",
                "kern.x\n",
                "x.ä",
            ]
        ],
    ],
)
def test_art_der_buchung(
    session: Session, k: RohKonten, art: str, mit_original: bool, regel: str
) -> None:
    original = storno_szenario(session, k) if mit_original else None
    with pytest.raises(IntegrityError) as fehler:
        roh_buchung(session, k.haushalt_id, art=art, storno_von=original)
    erwarte(fehler, "23514", regel)


# --- Unveränderlichkeit, geprüft als Eigentümerrolle --------------------------------------
# Die Laufzeitrolle scheitert schon an fehlenden Rechten (test_rechte.py). Die Trigger
# schützen auch gegen Code, der mit der Eigentümerrolle läuft, etwa in Migrationen.

VERBOTEN = [
    "UPDATE posting SET betrag = betrag WHERE buchung_id = :buchung_id",
    "UPDATE posting SET betrag = 1 WHERE false",
    "DELETE FROM posting WHERE buchung_id = :buchung_id",
    "TRUNCATE posting",
    "UPDATE buchung SET text = 'korrigiert' WHERE id = :buchung_id",
    "UPDATE buchung SET wertstellung = '2020-01-01' WHERE id = :buchung_id",
    "DELETE FROM buchung WHERE id = :buchung_id",
    "TRUNCATE buchung CASCADE",
    "TRUNCATE haushalt CASCADE",
    "INSERT INTO buchung (id, haushalt_id, art, wertstellung) "
    "SELECT id, haushalt_id, art, wertstellung FROM buchung WHERE id = :buchung_id "
    "ON CONFLICT (id) DO UPDATE SET text = 'x'",
]


@pytest.fixture
def owner_buchung(owner_session: Session) -> uuid.UUID:
    konten = roh_konten(owner_session)
    buchung_id = roh_buchung(owner_session, konten.haushalt_id)
    roh_postings(owner_session, buchung_id, [(konten.a, "10"), (konten.b, "-10")])
    pruefe_aufgeschobene(owner_session)
    return buchung_id


@pytest.mark.parametrize("anweisung", VERBOTEN)
def test_buchungen_und_postings_sind_unveraenderlich(
    owner_session: Session, owner_buchung: uuid.UUID, anweisung: str
) -> None:
    with pytest.raises(IntegrityError) as fehler:
        owner_session.execute(text(anweisung), {"buchung_id": owner_buchung})
    assert sqlstate(fehler.value) == "23001"
    assert constraint_name(fehler.value) in {"buchung_unveraenderlich", "posting_unveraenderlich"}


@pytest.mark.parametrize(
    "aenderung",
    [
        "haushalt_id = (SELECT id FROM haushalt WHERE id <> konto.haushalt_id LIMIT 1)",
        "kontoart = 'aktiv'",
        "rolle = 'test.anders'",
        "id = gen_random_uuid()",
    ],
)
def test_stammdaten_eines_kontos_sind_unveraenderlich(
    owner_session: Session, aenderung: str
) -> None:
    konten = roh_konten(owner_session)
    roh_konten(owner_session)
    with pytest.raises(IntegrityError) as fehler:
        owner_session.execute(
            text(f"UPDATE konto SET {aenderung} WHERE id = :id"),  # noqa: S608
            {"id": konten.a},
        )
    erwarte(fehler, "23001", "konto_stammdaten_unveraenderlich")


def test_bezeichnung_eines_kontos_ist_aenderbar(owner_session: Session) -> None:
    konten = roh_konten(owner_session)
    owner_session.execute(
        text("UPDATE konto SET bezeichnung = 'Neu' WHERE id = :id"), {"id": konten.a}
    )


def test_konto_mit_postings_laesst_sich_nicht_loeschen(
    owner_session: Session, owner_buchung: uuid.UUID
) -> None:
    with pytest.raises(IntegrityError) as fehler:
        owner_session.execute(
            text(
                "DELETE FROM konto WHERE id IN (SELECT konto_id FROM posting WHERE buchung_id = :b)"
            ),
            {"b": owner_buchung},
        )
    assert sqlstate(fehler.value) == "23503"


# --- Umgehungsversuche --------------------------------------------------------------------


def test_temporaere_tabelle_als_schatten(owner_session: Session) -> None:
    """Die Prüffunktionen lesen nur public.*, nie eine gleichnamige temporäre Tabelle."""
    konten = roh_konten(owner_session)
    buchung_id = roh_buchung(owner_session, konten.haushalt_id)
    owner_session.execute(
        text("CREATE TEMP TABLE posting (buchung_id uuid, konto_id uuid, betrag numeric)")
    )
    owner_session.execute(
        text("INSERT INTO pg_temp.posting VALUES (:b, :k, -10)"), {"b": buchung_id, "k": konten.b}
    )
    for konto_id, betrag in ((konten.a, "10"), (konten.c, "-1")):
        owner_session.execute(
            text("INSERT INTO public.posting (buchung_id, konto_id, betrag) VALUES (:b, :k, :x)"),
            {"b": buchung_id, "k": konto_id, "x": Decimal(betrag)},
        )
    with pytest.raises(IntegrityError) as fehler:
        pruefe_aufgeschobene(owner_session)
    erwarte(fehler, "23514", "buchung_summe_null")


def test_replikationsmodus_schaltet_die_trigger_nicht_ab(superuser_engine: Engine) -> None:
    """ENABLE ALWAYS: Selbst als Superuser im Modus replica feuern die Prüfungen."""
    with sitzung_mit_rollback(superuser_engine) as sitzung:
        sitzung.execute(text("SET LOCAL session_replication_role = replica"))
        konten = roh_konten(sitzung)
        buchung_id = roh_buchung(sitzung, konten.haushalt_id)
        roh_postings(sitzung, buchung_id, [(konten.a, "10"), (konten.b, "-9")])
        with pytest.raises(IntegrityError) as fehler:
            pruefe_aufgeschobene(sitzung)
    erwarte(fehler, "23514", "buchung_summe_null")


# --- Grenze von NUMERIC(19,4) -------------------------------------------------------------


def test_numeric_rundet_am_api_vorbei_still(session: Session, k: RohKonten) -> None:
    """Charakterisierung: Deshalb prüft die Anwendung vorher (kern/geld.speicherbar)."""
    buchung_id = roh_buchung(session, k.haushalt_id)
    roh_postings(session, buchung_id, [(k.a, "1.00004"), (k.b, "-1.00004")])
    pruefe_aufgeschobene(session)
    gespeichert = session.execute(
        text("SELECT betrag FROM posting WHERE buchung_id = :b AND konto_id = :k"),
        {"b": buchung_id, "k": k.a},
    ).scalar_one()
    assert gespeichert == Decimal("1.0000")


def test_numeric_lehnt_zu_grosse_betraege_ab(session: Session, k: RohKonten) -> None:
    buchung_id = roh_buchung(session, k.haushalt_id)
    with pytest.raises(DBAPIError) as fehler:
        roh_postings(session, buchung_id, [(k.a, "1000000000000000")])
    assert sqlstate(fehler.value) == "22003"


@pytest.mark.parametrize(("nullen", "zustand"), [(16383, None), (16384, "22003")])
def test_numeric_liest_hoechstens_16383_nachkommastellen(
    session: Session, nullen: int, zustand: str | None
) -> None:
    """Charakterisierung der Grenze, die kern/geld.speicherbar() übernimmt."""
    anweisung = text("SELECT CAST('1.' || repeat('0', :nullen) AS numeric) = 1")
    if zustand is None:
        assert session.execute(anweisung, {"nullen": nullen}).scalar_one() is True
        return
    with pytest.raises(DBAPIError) as fehler:
        session.execute(anweisung, {"nullen": nullen})
    assert sqlstate(fehler.value) == zustand


def test_wertstellung_bleibt_ein_datum(session: Session, k: RohKonten) -> None:
    buchung_id = roh_buchung(session, k.haushalt_id)
    wertstellung = session.execute(
        text("SELECT wertstellung FROM buchung WHERE id = :id"), {"id": buchung_id}
    ).scalar_one()
    assert wertstellung == WERTSTELLUNG
