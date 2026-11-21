# SPDX-License-Identifier: AGPL-3.0-or-later
"""Die JSON-Schnittstelle gegen PostgreSQL (M5): Kern und Modul Verbindlichkeiten.

Jeder Test läuft in einer äußeren Transaktion, die am Ende zurückgerollt wird; die Commits
der Anwendung werden zu Savepoints. Alle Namen sind erfunden.
"""

from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api import erzeuge_app
from app.kern.haushalt import lege_haushalt_an
from app.kern.web.router import QUELLCODE_STANDARD, QUELLCODE_VARIABLE

V = "/api/verbindlichkeiten"


@pytest.fixture
def client(app_engine: Engine) -> Iterator[TestClient]:
    with app_engine.connect() as verbindung:
        transaktion = verbindung.begin()
        fabrik = sessionmaker(
            bind=verbindung, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            with TestClient(erzeuge_app(fabrik)) as testclient:
                yield testclient
        finally:
            transaktion.rollback()


@pytest.fixture
def eingerichtet(client: TestClient) -> TestClient:
    antwort = client.post("/api/haushalt", json={"bundesland": "SH"})
    assert antwort.status_code == 201, antwort.text
    return client


def akte_mit_hauptforderung(client: TestClient) -> str:
    glaeubiger = client.post(f"{V}/glaeubiger", json={"name": "Muster Inkasso"}).json()["id"]
    akte = client.post(
        f"{V}/akten", json={"glaeubiger_id": glaeubiger, "aktenzeichen_glaeubiger": "AZ-7"}
    )
    assert akte.status_code == 201, akte.text
    akte_id = akte.json()["id"]
    bestandteil = client.post(
        f"{V}/akten/{akte_id}/bestandteile",
        json={
            "kennung": "hauptforderung",
            "art": "hauptforderung",
            "betrag": "1000.00",
            "entstanden_am": "2024-01-15",
            "faellig_am": "2024-01-31",
            "zinsregeln": [{"typ": "gesetzlich_288_1", "ab": "2024-02-01"}],
        },
    )
    assert bestandteil.status_code == 201, bestandteil.text
    return akte_id


def detail(client: TestClient, akte_id: str, stichtag: str = "2025-06-30") -> dict[str, Any]:
    antwort = client.get(f"{V}/akten/{akte_id}", params={"stichtag": stichtag})
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


# --- Kern ---------------------------------------------------------------------------------------


def test_info_mit_link_auf_den_quellcode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AGPL-3.0 § 13: Die Oberfläche verlinkt auf den Quellcode der laufenden Version."""
    monkeypatch.delenv(QUELLCODE_VARIABLE, raising=False)
    info = client.get("/api/info").json()
    assert info["lizenz"] == "AGPL-3.0-or-later"
    assert info["quellcode"] == QUELLCODE_STANDARD
    monkeypatch.setenv(QUELLCODE_VARIABLE, "https://example.org/finanzmanager")
    assert client.get("/api/info").json()["quellcode"] == "https://example.org/finanzmanager"


def test_ohne_haushalt_keine_akten(client: TestClient) -> None:
    assert client.get("/api/haushalt").status_code == 404
    assert client.get(f"{V}/akten").status_code == 409


def test_haushalt_nur_einmal(eingerichtet: TestClient) -> None:
    assert eingerichtet.get("/api/haushalt").json() == {"betriebsart": "einzel", "bundesland": "SH"}
    assert eingerichtet.post("/api/haushalt", json={"bundesland": "HH"}).status_code == 409


def test_unbekanntes_bundesland(client: TestClient) -> None:
    assert client.post("/api/haushalt", json={"bundesland": "XY"}).status_code == 422


# --- Akten --------------------------------------------------------------------------------------


def test_akte_mit_berechnung_fristen_verjaehrung_und_status(eingerichtet: TestClient) -> None:
    akte_id = akte_mit_hauptforderung(eingerichtet)
    zahlung = eingerichtet.post(
        f"{V}/akten/{akte_id}/zahlungen", json={"datum": "2025-02-03", "betrag": "150.00"}
    )
    assert zahlung.status_code == 201, zahlung.text
    mahnbescheid = eingerichtet.post(
        f"{V}/akten/{akte_id}/ereignisse",
        json={"typ": "zustellung_mahnbescheid", "datum": "2025-03-03"},
    )
    assert mahnbescheid.status_code == 201, mahnbescheid.text

    akte = detail(eingerichtet, akte_id)

    assert akte["glaeubiger_name"] == "Muster Inkasso"
    assert akte["aktenzeichen_glaeubiger"] == "AZ-7"
    assert akte["parameter"]["anrechnung"] == "bgb_367"
    assert akte["bestandteile"][0]["betrag"] == "1000.00"
    berechnung = akte["berechnung"]
    for feld in ("hauptforderung", "zinsen", "kosten", "restschuld", "ueberzahlung"):
        assert isinstance(berechnung[feld], str), feld
    assert berechnung["abschnitte"]
    assert [f["name"] for f in akte["fristen"]] == ["Widerspruch gegen Mahnbescheid"]
    assert akte["fristen"][0]["ende"] == "2025-03-17"
    assert akte["verjaehrung"]
    assert akte["verjaehrung_pflichthinweis"].startswith("Verjährung tritt nicht von selbst ein")
    assert akte["status"]["status"] == "mahnverfahren"
    typen = [(e["typ"], e["betrag"]) for e in akte["ereignisse"]]
    assert typen == [("zahlung", "150.00"), ("zustellung_mahnbescheid", None)]


def test_aktenliste_mit_status_und_restschuld(eingerichtet: TestClient) -> None:
    akte_id = akte_mit_hauptforderung(eingerichtet)
    eingerichtet.post(
        f"{V}/akten/{akte_id}/zahlungen", json={"datum": "2024-01-20", "betrag": "1000.00"}
    )
    (zeile,) = eingerichtet.get(f"{V}/akten", params={"stichtag": "2024-01-31"}).json()
    assert zeile["id"] == akte_id
    assert zeile["glaeubiger_name"] == "Muster Inkasso"
    assert zeile["restschuld"] == "0.00"
    assert zeile["status"] == "nachwirkung"


def test_storno_einer_zahlung(eingerichtet: TestClient) -> None:
    akte_id = akte_mit_hauptforderung(eingerichtet)
    zahlung_id = eingerichtet.post(
        f"{V}/akten/{akte_id}/zahlungen", json={"datum": "2024-01-20", "betrag": "1000.00"}
    ).json()["id"]
    pfad = f"{V}/akten/{akte_id}/zahlungen/{zahlung_id}/storno"
    assert eingerichtet.post(pfad).status_code == 204
    assert eingerichtet.post(pfad).status_code == 409
    akte = detail(eingerichtet, akte_id, "2024-01-31")
    assert akte["ereignisse"][0]["storniert"] is True
    assert akte["status"]["status"] == "offen"


def test_ereignis_loeschen_aber_keine_zahlung(eingerichtet: TestClient) -> None:
    akte_id = akte_mit_hauptforderung(eingerichtet)
    ereignis_id = eingerichtet.post(
        f"{V}/akten/{akte_id}/ereignisse", json={"typ": "anerkenntnis", "datum": "2025-01-02"}
    ).json()["id"]
    zahlung_id = eingerichtet.post(
        f"{V}/akten/{akte_id}/zahlungen", json={"datum": "2025-02-03", "betrag": "10.00"}
    ).json()["id"]
    assert eingerichtet.delete(f"{V}/akten/{akte_id}/ereignisse/{ereignis_id}").status_code == 204
    assert eingerichtet.delete(f"{V}/akten/{akte_id}/ereignisse/{zahlung_id}").status_code == 422


def test_zahlung_nicht_ueber_ereignisse(eingerichtet: TestClient) -> None:
    akte_id = akte_mit_hauptforderung(eingerichtet)
    antwort = eingerichtet.post(
        f"{V}/akten/{akte_id}/ereignisse", json={"typ": "zahlung", "datum": "2025-02-03"}
    )
    assert antwort.status_code == 422


@pytest.mark.parametrize("betrag", [150, 150.5, "15O.00", "1e3x"])
def test_betraege_nur_als_text(eingerichtet: TestClient, betrag: object) -> None:
    """CLAUDE.md, Geld: Beträge in JSON als String, nie als Zahl."""
    akte_id = akte_mit_hauptforderung(eingerichtet)
    antwort = eingerichtet.post(
        f"{V}/akten/{akte_id}/zahlungen", json={"datum": "2025-02-03", "betrag": betrag}
    )
    assert antwort.status_code == 422


def test_unbekannte_akte(eingerichtet: TestClient) -> None:
    pfad = f"{V}/akten/00000000-0000-0000-0000-000000000000"
    assert eingerichtet.get(pfad).status_code == 404
    antwort = eingerichtet.post(f"{pfad}/zahlungen", json={"datum": "2025-02-03", "betrag": "1.00"})
    assert antwort.status_code == 404


def test_doppelte_kennung(eingerichtet: TestClient) -> None:
    akte_id = akte_mit_hauptforderung(eingerichtet)
    antwort = eingerichtet.post(
        f"{V}/akten/{akte_id}/bestandteile",
        json={
            "kennung": "hauptforderung",
            "art": "hauptforderung",
            "betrag": "1.00",
            "entstanden_am": "2024-01-15",
        },
    )
    assert antwort.status_code == 422


def test_unbekannte_felder_werden_abgelehnt(eingerichtet: TestClient) -> None:
    antwort = eingerichtet.post(f"{V}/glaeubiger", json={"name": "Beispiel AG", "status": "x"})
    assert antwort.status_code == 422


def test_ohne_bundesland_keine_fristen(client: TestClient) -> None:
    """Ohne Bundesland keine Feiertage: Fristen und Verjährung fehlen mit Hinweis."""
    app = cast(FastAPI, client.app)
    fabrik = cast("sessionmaker[Session]", app.state.sitzungen)
    with fabrik() as session:
        lege_haushalt_an(session, betriebsart="einzel")
        session.commit()
    akte_id = akte_mit_hauptforderung(client)
    akte = detail(client, akte_id)
    assert akte["fristen"] is None
    assert akte["verjaehrung"] is None
    assert any("Bundesland" in h for h in akte["hinweise"])
    assert akte["berechnung"] is not None


# --- OpenAPI ------------------------------------------------------------------------------------


def test_openapi_beschreibt_betraege_als_text(client: TestClient) -> None:
    """Die Oberfläche erzeugt ihre Typen aus der OpenAPI-Beschreibung (CLAUDE.md, Stack)."""
    schema = client.get("/openapi.json").json()
    zahlung = schema["components"]["schemas"]["ZahlungEingabe"]["properties"]["betrag"]
    assert zahlung["type"] == "string"
    berechnung = schema["components"]["schemas"]["Berechnung"]["properties"]
    assert all(berechnung[f]["type"] == "string" for f in ("restschuld", "zinsen"))
