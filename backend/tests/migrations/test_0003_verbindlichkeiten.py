# SPDX-License-Identifier: AGPL-3.0-or-later
"""Migration 0003: Tabellen des Moduls Verbindlichkeiten (Fachkonzept 4.2, 4.3, 4.5).

Geprüft werden Rechte der Laufzeitrolle, die Werte der Aufzählungen gegen die Domain, die
Regeln zu Zahlung und Buchung, die individuelle Anrechnung und der Rückweg auf 0002.
"""

import re
import uuid
from enum import StrEnum
from typing import Any

import pytest
from alembic import command
from sqlalchemy import URL, Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.kern.db import erzeuge_engine
from app.kern.db.bootstrap import APP_ROLE
from app.kern.stammdaten import LAENDER
from app.module.verbindlichkeiten.domain import (
    Anrechnungsregel,
    Bestandteilart,
    Tageszaehlung,
    Teilung,
    Zahltag,
    Zinsbeginn,
    Zinsregeltyp,
)
from tests.datenbank import (
    HEAD,
    alembic_config,
    constraint_name,
    migriere,
    neue_testdatenbank,
    roh_buchung,
    roh_haushalt,
    sqlstate,
)

ALLE = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
RECHTE = {
    "glaeubiger": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "akte": {"SELECT", "INSERT", "UPDATE"},
    "akte_konto": {"SELECT", "INSERT"},
    "akte_teilungstag": {"SELECT", "INSERT", "DELETE"},
    "bestandteil": {"SELECT", "INSERT", "UPDATE"},  # UPDATE nur auf drei Spalten, s. u.
    "zinsregel": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "ereignis": {"SELECT", "INSERT", "UPDATE", "DELETE"},
}
AUFZAEHLUNGEN: list[tuple[str, type[StrEnum]]] = [
    ("ck_akte_anrechnung", Anrechnungsregel),
    ("ck_akte_tageszaehlung", Tageszaehlung),
    ("ck_akte_zinsbeginn", Zinsbeginn),
    ("ck_akte_zahltag", Zahltag),
    ("ck_akte_teilung", Teilung),
    ("ck_bestandteil_art", Bestandteilart),
    ("ck_zinsregel_typ", Zinsregeltyp),
]


def katalog(engine: Engine, sql: str, **parameter: object) -> list[Any]:
    with engine.connect() as verbindung:
        return list(verbindung.execute(text(sql), parameter).all())


def werte_im_check(engine: Engine, name: str) -> set[str]:
    (definition,) = katalog(
        engine, "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n", n=name
    )[0]
    return set(re.findall(r"'([^']*)'::text", definition))


def glaeubiger(sitzung: Session, haushalt_id: uuid.UUID) -> uuid.UUID:
    return sitzung.execute(
        text("INSERT INTO glaeubiger (haushalt_id, name) VALUES (:h, 'Muster GmbH') RETURNING id"),
        {"h": haushalt_id},
    ).scalar_one()


def akte(sitzung: Session, **spalten: object) -> tuple[uuid.UUID, uuid.UUID]:
    haushalt_id = roh_haushalt(sitzung)
    werte: dict[str, object] = {
        "haushalt_id": haushalt_id,
        "glaeubiger_id": glaeubiger(sitzung, haushalt_id),
    }
    werte.update(spalten)
    namen = ", ".join(werte)
    platzhalter = ", ".join(f":{name}" for name in werte)
    akte_id = sitzung.execute(
        text(f"INSERT INTO akte ({namen}) VALUES ({platzhalter}) RETURNING id"),  # noqa: S608
        werte,
    ).scalar_one()
    return haushalt_id, akte_id


def ereignis(
    sitzung: Session, akte_id: uuid.UUID, typ: str, buchung_id: uuid.UUID | None = None
) -> uuid.UUID:
    return sitzung.execute(
        text(
            "INSERT INTO ereignis (akte_id, typ, datum, buchung_id)"
            " VALUES (:a, :t, DATE '2026-03-02', :b) RETURNING id"
        ),
        {"a": akte_id, "t": typ, "b": buchung_id},
    ).scalar_one()


# --- Rechte (E-19) -------------------------------------------------------------------------------


@pytest.mark.parametrize("tabelle", sorted(RECHTE))
@pytest.mark.parametrize("recht", ALLE)
def test_rechte_der_laufzeitrolle(owner_engine: Engine, tabelle: str, recht: str) -> None:
    sql = (
        "SELECT has_any_column_privilege(:rolle, :tabelle, :recht)"
        if recht in {"SELECT", "INSERT", "UPDATE", "REFERENCES"}
        else "SELECT has_table_privilege(:rolle, :tabelle, :recht)"
    )
    zeilen = katalog(owner_engine, sql, rolle=APP_ROLE, tabelle=f"public.{tabelle}", recht=recht)
    assert zeilen == [(recht in RECHTE[tabelle],)]


@pytest.mark.parametrize(
    ("spalte", "erwartet"),
    [
        ("entstanden_am", True),
        ("faellig_am", True),
        ("kenntnis_am", True),
        ("ursprungsbetrag", False),
        ("art", False),
        ("konto_id", False),
        ("kennung", False),
        ("akte_id", False),
    ],
)
def test_bestandteil_nur_daten_aenderbar(owner_engine: Engine, spalte: str, erwartet: bool) -> None:
    """Betrag, Art und Konto hängen am Ledger (Kap. 4.2, 4.3)."""
    zeilen = katalog(
        owner_engine,
        "SELECT has_column_privilege(:rolle, 'public.bestandteil', :spalte, 'UPDATE')",
        rolle=APP_ROLE,
        spalte=spalte,
    )
    assert zeilen == [(erwartet,)]


def test_haushalt_bleibt_ohne_update(owner_engine: Engine) -> None:
    zeilen = katalog(
        owner_engine,
        "SELECT has_any_column_privilege(:rolle, 'public.haushalt', 'UPDATE')",
        rolle=APP_ROLE,
    )
    assert zeilen == [(False,)]


# --- Aufzählungen -------------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "aufzaehlung"), AUFZAEHLUNGEN, ids=[n for n, _ in AUFZAEHLUNGEN])
def test_aufzaehlungen_wie_in_der_domain(
    owner_engine: Engine, name: str, aufzaehlung: type[StrEnum]
) -> None:
    assert werte_im_check(owner_engine, name) == {w.value for w in aufzaehlung}


def test_bundeslaender_wie_in_den_stammdaten(owner_engine: Engine) -> None:
    assert werte_im_check(owner_engine, "ck_haushalt_bundesland") == set(LAENDER)


def test_voreinstellungen_der_akte_wie_in_kapitel_5_1(session: Session) -> None:
    _, akte_id = akte(session)
    zeile = session.execute(
        text(
            "SELECT richtung, verbraucherdarlehen, anrechnung, reihenfolge, tageszaehlung,"
            " zinsbeginn, zahltag, teilung FROM akte WHERE id = :id"
        ),
        {"id": akte_id},
    ).one()
    assert tuple(zeile) == (
        "verbindlichkeit",
        False,
        "bgb_367",
        None,
        "act_365",
        "genannter_tag",
        "alter_betrag",
        "kalender",
    )


# --- Regeln ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("anrechnung", "reihenfolge", "constraint"),
    [
        ("individuell", None, "ck_akte_reihenfolge_individuell"),
        ("bgb_367", ["kosten", "zinsen", "hauptforderung"], "ck_akte_reihenfolge_individuell"),
        ("individuell", ["kosten", "zinsen"], "ck_akte_reihenfolge_gruppen"),
        ("individuell", ["kosten", "kosten", "zinsen"], "ck_akte_reihenfolge_gruppen"),
    ],
)
def test_reihenfolge_nur_bei_individueller_anrechnung(
    session: Session, anrechnung: str, reihenfolge: list[str] | None, constraint: str
) -> None:
    with pytest.raises(DBAPIError) as fehler:
        akte(session, anrechnung=anrechnung, reihenfolge=reihenfolge)
    assert constraint_name(fehler.value) == constraint


def test_individuelle_reihenfolge(session: Session) -> None:
    akte(session, anrechnung="individuell", reihenfolge=["hauptforderung", "zinsen", "kosten"])


def test_zahlung_braucht_eine_buchung(session: Session) -> None:
    _, akte_id = akte(session)
    with pytest.raises(DBAPIError) as fehler:
        ereignis(session, akte_id, "zahlung")
    assert constraint_name(fehler.value) == "ck_ereignis_buchung_bei_zahlung"


def test_buchung_nur_bei_zahlung(session: Session) -> None:
    haushalt_id, akte_id = akte(session)
    buchung_id = roh_buchung(session, haushalt_id, art="verbindlichkeiten.zahlung")
    with pytest.raises(DBAPIError) as fehler:
        ereignis(session, akte_id, "anerkenntnis", buchung_id)
    assert constraint_name(fehler.value) == "ck_ereignis_buchung_bei_zahlung"


@pytest.mark.parametrize(
    "anweisung",
    [
        "UPDATE ereignis SET datum = DATE '2026-03-03' WHERE id = :id",
        "UPDATE ereignis SET details = '{\"zurueckgegeben\": true}' WHERE id = :id",
        "DELETE FROM ereignis WHERE id = :id",
    ],
)
def test_ereignis_mit_buchung_unveraenderlich(session: Session, anweisung: str) -> None:
    """Eine falsch erfasste Zahlung wird storniert, nicht geändert (Kap. 4.1, E-26)."""
    haushalt_id, akte_id = akte(session)
    buchung_id = roh_buchung(session, haushalt_id, art="verbindlichkeiten.zahlung")
    ereignis_id = ereignis(session, akte_id, "zahlung", buchung_id)
    with pytest.raises(DBAPIError) as fehler:
        session.execute(text(anweisung), {"id": ereignis_id})
    assert constraint_name(fehler.value) == "ereignis_mit_buchung_unveraenderlich"
    assert sqlstate(fehler.value) == "23000"


def test_ereignis_ohne_buchung_aenderbar(session: Session) -> None:
    """Ändert sich ein Ereignis, ändern sich die Fristen (Kap. 5.4)."""
    _, akte_id = akte(session)
    ereignis_id = ereignis(session, akte_id, "zustellung_mahnbescheid")
    session.execute(
        text("UPDATE ereignis SET datum = DATE '2026-03-03' WHERE id = :id"), {"id": ereignis_id}
    )
    session.execute(text("DELETE FROM ereignis WHERE id = :id"), {"id": ereignis_id})


def test_details_sind_ein_objekt(session: Session) -> None:
    _, akte_id = akte(session)
    with pytest.raises(DBAPIError) as fehler:
        session.execute(
            text("INSERT INTO ereignis (akte_id, typ, details) VALUES (:a, 'rechtskraft', '[]')"),
            {"a": akte_id},
        )
    assert constraint_name(fehler.value) == "ck_ereignis_details_objekt"


@pytest.mark.parametrize(
    ("spalten", "constraint"),
    [
        ("typ, ab", "ck_zinsregel_konto_nur_verzinslich"),  # verzinslich ohne Konto
        ("typ, aufschlag", "ck_zinsregel_aufschlag"),
        ("typ, satz", "ck_zinsregel_satz"),
    ],
)
def test_zinsregel_regeln(session: Session, spalten: str, constraint: str) -> None:
    haushalt_id, akte_id = akte(session)
    konto_id = session.execute(
        text(
            "INSERT INTO konto (haushalt_id, kontoart, rolle, bezeichnung)"
            " VALUES (:h, 'passiv', 'verbindlichkeiten.hauptforderung', 'HF') RETURNING id"
        ),
        {"h": haushalt_id},
    ).scalar_one()
    bestandteil_id = session.execute(
        text(
            "INSERT INTO bestandteil (akte_id, kennung, art, konto_id, ursprungsbetrag)"
            " VALUES (:a, 'hauptforderung', 'hauptforderung', :k, 100) RETURNING id"
        ),
        {"a": akte_id, "k": konto_id},
    ).scalar_one()
    werte = {
        "typ, ab": "'gesetzlich_288_1', DATE '2024-01-01'",
        "typ, aufschlag": "'keine', 5",
        "typ, satz": "'keine', 5",
    }[spalten]
    with pytest.raises(DBAPIError) as fehler:
        session.execute(
            text(
                f"INSERT INTO zinsregel (bestandteil_id, {spalten}) VALUES (:b, {werte})"  # noqa: S608
            ),
            {"b": bestandteil_id},
        )
    assert constraint_name(fehler.value) == constraint


def test_funktion_mit_festem_suchpfad(owner_engine: Engine) -> None:
    zeilen = katalog(
        owner_engine,
        "SELECT proconfig FROM pg_proc WHERE proname = 'verbindlichkeiten_ereignis_mit_buchung'",
    )
    assert zeilen == [(["search_path=pg_catalog, pg_temp"],)]


# --- Rückweg -------------------------------------------------------------------------------


def test_rueckweg_auf_0002_und_erneuter_aufbau(admin_url: URL) -> None:
    with neue_testdatenbank(admin_url) as datenbank:
        owner = erzeuge_engine(datenbank.owner_url)
        try:
            with owner.begin() as verbindung:
                command.downgrade(alembic_config(verbindung), "0002")
            tabellen = katalog(
                owner,
                "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace"
                " AND relkind = 'r'",
            )
            assert {name for (name,) in tabellen} == {
                "alembic_version",
                "haushalt",
                "konto",
                "buchung",
                "posting",
                "konto_sperre",
            }
            spalten = katalog(
                owner,
                "SELECT attname FROM pg_attribute WHERE attrelid = 'public.haushalt'::regclass"
                " AND attnum > 0 AND NOT attisdropped",
            )
            assert {name for (name,) in spalten} == {"id", "betriebsart"}
            migriere(datenbank.owner_url)
            assert katalog(owner, "SELECT version_num FROM alembic_version") == [(HEAD,)]
        finally:
            owner.dispose()
