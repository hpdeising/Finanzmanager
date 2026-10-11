# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eigenschaften des Buchungskerns gegen echtes PostgreSQL (Fachkonzept Kap. 12).

Jedes Beispiel läuft in einer eigenen Transaktion, die am Ende zurückgerollt wird. Vor jeder
Prüfung werden die zurückgestellten Constraint-Trigger ausgelöst. Die Beispielzahl steuert
das Profil aus ``FINANZMANAGER_HYPOTHESIS_DB_PROFIL`` (tests/datenbank.py).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.kern.haushalt import lege_haushalt_an
from app.kern.ledger import Posting, PostingEingabe, buche, lege_konto_an, saldo, storniere
from tests.datenbank import (
    DB_EINSTELLUNGEN,
    constraint_name,
    pruefe_aufgeschobene,
    roh_buchung,
    roh_postings,
    sitzung_mit_rollback,
    sqlstate,
)

ANZAHL_KONTEN = 4
ANFANG, ENDE = date(2024, 1, 1), date(2024, 3, 31)


def _mit_vorzeichen(betrag: Decimal, negativ: bool) -> Decimal:
    return -betrag if negativ else betrag


# Nie null, ohne filter: Betrag ab 0.0001, Vorzeichen getrennt gezogen.
BETRAG = st.builds(
    _mit_vorzeichen,
    st.decimals(min_value=Decimal("0.0001"), max_value=Decimal(1_000_000), places=4),
    st.booleans(),
)
WERTSTELLUNG = st.dates(ANFANG, ENDE)
STICHTAG = st.dates(ANFANG - timedelta(days=2), ENDE + timedelta(days=2))


@st.composite
def umbuchung(draw: st.DrawFn) -> list[tuple[int, Decimal]]:
    """Ein bis drei Bewegungen von Konto i nach Konto j ≠ i; konstruktiv ausgeglichen."""
    postings: list[tuple[int, Decimal]] = []
    for _ in range(draw(st.integers(1, 3))):
        von = draw(st.integers(0, ANZAHL_KONTEN - 1))
        nach = (von + draw(st.integers(1, ANZAHL_KONTEN - 1))) % ANZAHL_KONTEN
        betrag = draw(BETRAG)
        postings += [(von, betrag), (nach, -betrag)]
    return postings


@dataclass(frozen=True)
class Entwurf:
    wertstellung: date
    postings: list[tuple[int, Decimal]]


ENTWURF = st.builds(Entwurf, WERTSTELLUNG, umbuchung())
ENTWUERFE = st.lists(ENTWURF, min_size=1, max_size=5)


@dataclass
class Haushalt:
    id: uuid.UUID
    konten: list[uuid.UUID]


def lege_an(sitzung: Session) -> Haushalt:
    haushalt = lege_haushalt_an(sitzung, betriebsart="einzel")
    konten = [
        lege_konto_an(
            sitzung,
            haushalt_id=haushalt.id,
            kontoart="passiv",
            rolle="test.konto",
            bezeichnung=f"Konto {nummer}",
        ).id
        for nummer in range(ANZAHL_KONTEN)
    ]
    return Haushalt(haushalt.id, konten)


def buche_entwurf(sitzung: Session, haushalt: Haushalt, entwurf: Entwurf) -> uuid.UUID:
    return buche(
        sitzung,
        haushalt_id=haushalt.id,
        art="test.buchung",
        wertstellung=entwurf.wertstellung,
        postings=[PostingEingabe(haushalt.konten[i], betrag) for i, betrag in entwurf.postings],
    ).id


def modellsaldo(entwuerfe: Sequence[Entwurf], konto: int, stichtag: date) -> Decimal:
    """Referenzmodell ohne Datenbank: Summe der Postings bis einschließlich Stichtag."""
    return sum(
        (
            betrag
            for entwurf in entwuerfe
            if entwurf.wertstellung <= stichtag
            for i, betrag in entwurf.postings
            if i == konto
        ),
        Decimal(0),
    )


def salden(sitzung: Session, haushalt: Haushalt, stichtag: date) -> list[Decimal]:
    return [saldo(sitzung, konto_id=k, stichtag=stichtag) for k in haushalt.konten]


@DB_EINSTELLUNGEN
@given(entwuerfe=ENTWUERFE)
def test_summe_der_postings_je_buchung_ist_null(
    app_engine: Engine, entwuerfe: list[Entwurf]
) -> None:
    with sitzung_mit_rollback(app_engine) as sitzung:
        haushalt = lege_an(sitzung)
        for entwurf in entwuerfe:
            buche_entwurf(sitzung, haushalt, entwurf)
        pruefe_aufgeschobene(sitzung)
        abweichend = sitzung.execute(
            text(
                "SELECT p.buchung_id FROM posting AS p JOIN buchung AS b ON b.id = p.buchung_id"
                " WHERE b.haushalt_id = :h GROUP BY p.buchung_id HAVING sum(p.betrag) <> 0"
            ),
            {"h": haushalt.id},
        ).all()
        assert abweichend == []


@DB_EINSTELLUNGEN
@given(
    entwurf=umbuchung(),
    stoerung=BETRAG,
    konto=st.integers(0, ANZAHL_KONTEN - 1),
)
def test_unausgeglichene_buchungen_lehnt_die_datenbank_ab(
    app_engine: Engine, entwurf: list[tuple[int, Decimal]], stoerung: Decimal, konto: int
) -> None:
    """Am API vorbei: Schon die kleinste Abweichung (0.0001) scheitert in PostgreSQL."""
    with sitzung_mit_rollback(app_engine) as sitzung:
        haushalt = lege_an(sitzung)
        buchung_id = roh_buchung(sitzung, haushalt.id)
        postings = [*entwurf, (konto, stoerung)]
        roh_postings(sitzung, buchung_id, [(haushalt.konten[i], str(b)) for i, b in postings])
        with pytest.raises(IntegrityError) as fehler:
            pruefe_aufgeschobene(sitzung)
        assert (sqlstate(fehler.value), constraint_name(fehler.value)) == (
            "23514",
            "buchung_summe_null",
        )


@DB_EINSTELLUNGEN
@given(entwuerfe=ENTWUERFE, stichtag=STICHTAG)
def test_salden_folgen_dem_referenzmodell_und_ergeben_null(
    app_engine: Engine, entwuerfe: list[Entwurf], stichtag: date
) -> None:
    with sitzung_mit_rollback(app_engine) as sitzung:
        haushalt = lege_an(sitzung)
        for entwurf in entwuerfe:
            buche_entwurf(sitzung, haushalt, entwurf)
        pruefe_aufgeschobene(sitzung)
        ist = salden(sitzung, haushalt, stichtag)
        assert ist == [modellsaldo(entwuerfe, i, stichtag) for i in range(ANZAHL_KONTEN)]
        assert sum(ist) == 0


@DB_EINSTELLUNGEN
@given(bestand=st.lists(ENTWURF, max_size=3), falsch=ENTWURF, stichtag=STICHTAG)
def test_storno_stellt_den_saldo_zu_jedem_stichtag_wieder_her(
    app_engine: Engine, bestand: list[Entwurf], falsch: Entwurf, stichtag: date
) -> None:
    """E-18: Das Storno trägt die Wertstellung des Originals, also gilt das für jeden Tag."""
    with sitzung_mit_rollback(app_engine) as sitzung:
        haushalt = lege_an(sitzung)
        for entwurf in bestand:
            buche_entwurf(sitzung, haushalt, entwurf)
        storniere(sitzung, buchung_id=buche_entwurf(sitzung, haushalt, falsch))
        pruefe_aufgeschobene(sitzung)
        assert salden(sitzung, haushalt, stichtag) == [
            modellsaldo(bestand, i, stichtag) for i in range(ANZAHL_KONTEN)
        ]


@DB_EINSTELLUNGEN
@given(bestand=st.lists(ENTWURF, max_size=3), falsch=ENTWURF, richtig=ENTWURF, stichtag=STICHTAG)
def test_storno_plus_neubuchung_wie_die_korrigierte_buchung(
    app_engine: Engine, bestand: list[Entwurf], falsch: Entwurf, richtig: Entwurf, stichtag: date
) -> None:
    """Fachkonzept Kap. 12, für jeden Stichtag."""
    with sitzung_mit_rollback(app_engine) as sitzung:
        haushalt = lege_an(sitzung)
        for entwurf in bestand:
            buche_entwurf(sitzung, haushalt, entwurf)
        storniere(sitzung, buchung_id=buche_entwurf(sitzung, haushalt, falsch))
        buche_entwurf(sitzung, haushalt, richtig)
        pruefe_aufgeschobene(sitzung)
        assert salden(sitzung, haushalt, stichtag) == [
            modellsaldo([*bestand, richtig], i, stichtag) for i in range(ANZAHL_KONTEN)
        ]


SPEICHERBAR = st.decimals(
    min_value=Decimal("-999999999999999.9999"),
    max_value=Decimal("999999999999999.9999"),
    places=4,
    allow_nan=False,
    allow_infinity=False,
).filter(lambda wert: wert != 0)


@DB_EINSTELLUNGEN
@given(wert=SPEICHERBAR)
def test_betraege_kommen_exakt_zurueck(app_engine: Engine, wert: Decimal) -> None:
    with sitzung_mit_rollback(app_engine) as sitzung:
        haushalt = lege_an(sitzung)
        buchung_id = buche_entwurf(sitzung, haushalt, Entwurf(ANFANG, [(0, wert), (1, -wert)]))
        pruefe_aufgeschobene(sitzung)
        sitzung.expire_all()
        gelesen = sitzung.execute(
            select(Posting.betrag).where(
                Posting.buchung_id == buchung_id, Posting.konto_id == haushalt.konten[0]
            )
        ).scalar_one()
        assert gelesen == wert
