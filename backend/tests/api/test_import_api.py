# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schnittstelle des Imports (Fachkonzept Kap. 8): CSV-Profile, Hochladen, Läufe, Abschluss.

Jeder Test läuft in einer äußeren Transaktion, die am Ende zurückgerollt wird. Alle Namen,
IBANs und Beträge sind erfunden.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api import erzeuge_app
from app.kern.web.importe import HOECHSTGROESSE
from tests.kern.import_.test_camt053 import auszug, eintrag

IMPORT = "/api/import"
OKTETT = {"content-type": "application/octet-stream"}

PROFIL: dict[str, Any] = {
    "name": "Beispielbank",
    "spalte_buchungstag": "Buchungstag",
    "spalte_valuta": "Valuta",
    "spalte_betrag": "Betrag",
    "spalte_gegen_name": "Empfänger",
    "spalte_gegen_iban": "IBAN",
    "spalten_verwendungszweck": ["Verwendungszweck"],
}

CSV = (
    "Buchungstag;Valuta;Empfänger;IBAN;Verwendungszweck;Betrag\n"
    "03.02.2025;04.02.2025;Muster Inkasso GmbH;DE02120300000000202051;AZ 4711 Rate 2;-150,00\n"
    "05.02.2025;05.02.2025;Arbeitgeber AG;DE02100500000054540402;Gehalt Februar;1.234,56\n"
    "03.02.2025;04.02.2025;Muster Inkasso GmbH;DE02120300000000202051;AZ 4711 Rate 2;-150,00\n"
).encode()


@pytest.fixture
def client(app_engine: Engine) -> Iterator[TestClient]:
    with app_engine.connect() as verbindung:
        transaktion = verbindung.begin()
        fabrik = sessionmaker(
            bind=verbindung, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            with TestClient(erzeuge_app(fabrik)) as testclient:
                antwort = testclient.post("/api/haushalt", json={"bundesland": "SH"})
                assert antwort.status_code == 201, antwort.text
                yield testclient
        finally:
            transaktion.rollback()


def profil_id(client: TestClient) -> str:
    antwort = client.post(f"{IMPORT}/csv-profile", json=PROFIL)
    assert antwort.status_code == 201, antwort.text
    return antwort.json()["id"]


def hochladen(client: TestClient, daten: bytes, **parameter: str) -> Any:
    return client.post(f"{IMPORT}/laeufe", content=daten, headers=OKTETT, params=parameter)


def test_csv_profile(client: TestClient) -> None:
    neu = profil_id(client)
    liste = client.get(f"{IMPORT}/csv-profile").json()
    assert liste == [
        {
            **PROFIL,
            "id": neu,
            "trennzeichen": ";",
            "kodierung": "utf-8",
            "datumsformat": "%d.%m.%Y",
            "dezimaltrennzeichen": ",",
            "tausendertrennzeichen": ".",
            "kopfzeilen_ueberspringen": 0,
        }
    ]
    assert client.post(f"{IMPORT}/csv-profile", json=PROFIL).status_code == 409
    assert client.delete(f"{IMPORT}/csv-profile/{neu}").status_code == 204
    assert client.delete(f"{IMPORT}/csv-profile/{neu}").status_code == 404
    assert client.get(f"{IMPORT}/csv-profile").json() == []


@pytest.mark.parametrize(
    "aenderung",
    [
        {"kodierung": "keine-kodierung"},
        {"trennzeichen": ";;"},
        {"dezimaltrennzeichen": ".", "tausendertrennzeichen": "."},
        {"spalten_verwendungszweck": []},
        {"kopfzeilen_ueberspringen": -1},
    ],
)
def test_ungueltiges_csv_profil(client: TestClient, aenderung: dict[str, Any]) -> None:
    assert client.post(f"{IMPORT}/csv-profile", json=PROFIL | aenderung).status_code == 422


def test_csv_hochladen(client: TestClient) -> None:
    antwort = hochladen(
        client, CSV, dateiformat="csv", profil_id=profil_id(client), wertstellung_aus="valuta"
    )
    assert antwort.status_code == 201, antwort.text
    lauf = antwort.json()
    assert lauf["format"] == "csv"
    assert lauf["profil_name"] == "Beispielbank"
    assert lauf["wertstellung_aus"] == "valuta"
    assert lauf["umsaetze_gelesen"] == 3
    assert lauf["abgeschlossen_am"] is None
    erste, zweite = lauf["zeilen"]
    assert erste | {"id": None} == {
        "id": None,
        "position": 1,
        "datum": "2025-02-04",
        "buchungstag": "2025-02-03",
        "valuta": "2025-02-04",
        "betrag": "150.00",
        "gegen_name": "Muster Inkasso GmbH",
        "gegen_iban": "DE02120300000000202051",
        "verwendungszweck": "AZ 4711 Rate 2",
        "status": "offen",
        "duplikat": False,
    }
    assert (zweite["position"], zweite["duplikat"]) == (2, True)
    assert client.get(f"{IMPORT}/laeufe/{lauf['id']}").json() == lauf
    assert [k["id"] for k in client.get(f"{IMPORT}/laeufe").json()] == [lauf["id"]]


def test_camt_hochladen(client: TestClient) -> None:
    daten = auszug(eintrag(), eintrag(ind="CRDT", gegen="Dbtr"))
    antwort = hochladen(client, daten, dateiformat="camt053", wertstellung_aus="buchungstag")
    assert antwort.status_code == 201, antwort.text
    lauf = antwort.json()
    assert (lauf["format"], lauf["profil_name"], lauf["umsaetze_gelesen"]) == ("camt053", None, 2)
    assert [(z["datum"], z["betrag"]) for z in lauf["zeilen"]] == [("2025-02-03", "150.00")]


def test_einstellung_zu_p16_ist_pflicht(client: TestClient) -> None:
    """Das Fachkonzept legt keine Voreinstellung fest (P-16)."""
    assert hochladen(client, auszug(eintrag()), dateiformat="camt053").status_code == 422


def test_fehlende_valuta(client: TestClient) -> None:
    antwort = hochladen(
        client, auszug(eintrag(valuta=None)), dateiformat="camt053", wertstellung_aus="valuta"
    )
    assert antwort.status_code == 422
    assert "Valuta" in antwort.json()["detail"]
    assert client.get(f"{IMPORT}/laeufe").json() == []


def test_profil_nur_bei_csv(client: TestClient) -> None:
    profil = profil_id(client)
    assert hochladen(client, CSV, dateiformat="csv", wertstellung_aus="valuta").status_code == 422
    antwort = hochladen(
        client,
        auszug(eintrag()),
        dateiformat="camt053",
        profil_id=profil,
        wertstellung_aus="valuta",
    )
    assert antwort.status_code == 422


def test_unbekanntes_profil(client: TestClient) -> None:
    antwort = hochladen(
        client,
        CSV,
        dateiformat="csv",
        profil_id="00000000-0000-0000-0000-000000000000",
        wertstellung_aus="valuta",
    )
    assert antwort.status_code == 404


def test_unlesbare_datei_nennt_keinen_wert(client: TestClient) -> None:
    kaputt = CSV.replace(b"-150,00", b"-15x,00", 1)
    antwort = hochladen(
        client, kaputt, dateiformat="csv", profil_id=profil_id(client), wertstellung_aus="valuta"
    )
    assert antwort.status_code == 422
    assert "15x" not in antwort.json()["detail"]


def test_zu_grosse_datei(client: TestClient) -> None:
    daten = b" " * (HOECHSTGROESSE + 1)
    antwort = hochladen(client, daten, dateiformat="camt053", wertstellung_aus="valuta")
    assert antwort.status_code == 413


def test_abschluss_verwirft_offene_zeilen(client: TestClient) -> None:
    lauf = hochladen(
        client, auszug(eintrag()), dateiformat="camt053", wertstellung_aus="valuta"
    ).json()
    antwort = client.post(f"{IMPORT}/laeufe/{lauf['id']}/abschluss")
    assert antwort.status_code == 200, antwort.text
    abgeschlossen = antwort.json()
    assert abgeschlossen["abgeschlossen_am"] is not None
    assert abgeschlossen["zeilen"] == []
    assert client.get(f"{IMPORT}/laeufe/{lauf['id']}").json() == abgeschlossen


def test_unbekannter_lauf(client: TestClient) -> None:
    unbekannt = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"{IMPORT}/laeufe/{unbekannt}").status_code == 404
    assert client.post(f"{IMPORT}/laeufe/{unbekannt}/abschluss").status_code == 404
