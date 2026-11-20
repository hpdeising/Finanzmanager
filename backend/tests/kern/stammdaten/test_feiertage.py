# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests des Feiertagskalenders (Fachkonzept Kap. 5.4 und 7).

Alle Kalender hier sind ausgedacht; sie zeigen nur das Format und die Prüfungen.
"""

from datetime import date
from pathlib import Path

import pytest

from app.kern.stammdaten import (
    LAENDER,
    Feiertagskalender,
    StammdatenFehlenError,
    StammdatenUngueltigError,
    lade_feiertagskalender,
)


def _daten(*feiertage: dict[str, object], **kopf: object) -> dict[str, object]:
    return {
        "quelle": "Ausgedachter Testkalender",
        "geprueft_von": "Test",
        "gueltig_ab": date(2030, 1, 1),
        "gueltig_bis": date(2030, 12, 31),
        "feiertage": list(feiertage),
        **kopf,
    }


KALENDER = Feiertagskalender.aus_daten(
    _daten(
        {"datum": date(2030, 1, 1), "name": "Testtag eins", "laender": ["alle"]},
        {"datum": date(2030, 6, 3), "name": "Testtag zwei", "laender": ["BY", "SH"]},
        regionale_feiertage=[
            {"datum": date(2030, 8, 8), "name": "Regionaler Testtag", "laender": ["BY"]}
        ],
    )
)


@pytest.mark.parametrize(
    ("tag", "land", "erwartet"),
    [
        (date(2030, 8, 8), "BY", "Regionaler Testtag"),
        (date(2030, 8, 8), "SH", None),
        (date(2030, 1, 1), "BY", None),
    ],
)
def test_regionaler_feiertag(tag: date, land: str, erwartet: str | None) -> None:
    """Feiertage nur in Teilen eines Landes sind keine Feiertage des Landes (Kap. 5.4)."""
    assert KALENDER.regionaler_feiertag(tag, land) == erwartet
    if erwartet is not None:
        assert not KALENDER.ist_feiertag(tag, land)


def test_laender_sind_die_sechzehn_kuerzel() -> None:
    assert len(LAENDER) == 16
    assert {"BY", "SH", "NW", "BE"} <= LAENDER


@pytest.mark.parametrize(
    ("tag", "land", "erwartet"),
    [
        (date(2030, 1, 1), "HH", True),
        (date(2030, 6, 3), "BY", True),
        (date(2030, 6, 3), "SH", True),
        (date(2030, 6, 3), "NW", False),
        (date(2030, 6, 4), "BY", False),
    ],
)
def test_ist_feiertag(tag: date, land: str, erwartet: bool) -> None:
    assert KALENDER.ist_feiertag(tag, land) is erwartet


@pytest.mark.parametrize("tag", [date(2029, 12, 31), date(2031, 1, 1)])
def test_ausserhalb_der_gueltigkeit_wird_nicht_geschaetzt(tag: date) -> None:
    with pytest.raises(StammdatenFehlenError):
        KALENDER.ist_feiertag(tag, "BY")


def test_unbekanntes_land() -> None:
    with pytest.raises(ValueError, match="Land"):
        KALENDER.ist_feiertag(date(2030, 1, 1), "XX")


def test_lade_feiertagskalender_liest_yaml(tmp_path: Path) -> None:
    datei = tmp_path / "feiertage.yaml"
    datei.write_text(
        "quelle: Test\n"
        'geprueft_von: "Test"\n'
        "gueltig_ab: 2030-01-01\n"
        "gueltig_bis: 2030-12-31\n"
        "feiertage:\n"
        "  - datum: 2030-10-03\n"
        "    name: Testtag\n"
        "    laender: [alle]\n",
        encoding="utf-8",
    )
    assert lade_feiertagskalender(datei).ist_feiertag(date(2030, 10, 3), "SN")


def test_fehlende_datei_ist_ein_fehler(tmp_path: Path) -> None:
    with pytest.raises(StammdatenUngueltigError):
        lade_feiertagskalender(tmp_path / "fehlt.yaml")


@pytest.mark.parametrize(
    "daten",
    [
        pytest.param(_daten(quelle=""), id="leere Quelle"),
        pytest.param(_daten(gueltig_bis=date(2029, 12, 31)), id="bis vor ab"),
        pytest.param(
            _daten({"datum": date(2031, 1, 1), "name": "x", "laender": ["alle"]}),
            id="außerhalb der Gültigkeit",
        ),
        pytest.param(
            _daten({"datum": date(2030, 1, 1), "name": "x", "laender": ["XX"]}),
            id="unbekanntes Land",
        ),
        pytest.param(
            _daten({"datum": date(2030, 1, 1), "name": "x", "laender": []}), id="keine Länder"
        ),
        pytest.param(
            _daten({"datum": date(2030, 1, 1), "name": "x", "laender": ["alle", "BY"]}),
            id="alle und einzelne",
        ),
        pytest.param(
            _daten(
                {"datum": date(2030, 1, 2), "name": "x", "laender": ["alle"]},
                {"datum": date(2030, 1, 1), "name": "y", "laender": ["alle"]},
            ),
            id="nicht aufsteigend",
        ),
        pytest.param(
            _daten(
                {"datum": date(2030, 1, 1), "name": "x", "laender": ["BY"]},
                {"datum": date(2030, 1, 1), "name": "y", "laender": ["SH"]},
            ),
            id="Datum doppelt",
        ),
        pytest.param(_daten({"datum": "2030-01-01", "name": "x", "laender": ["alle"]}), id="Text"),
        pytest.param(_daten({"datum": date(2030, 1, 1), "laender": ["alle"]}), id="ohne Name"),
        pytest.param(
            _daten(
                regionale_feiertage=[{"datum": date(2031, 8, 8), "name": "x", "laender": ["BY"]}]
            ),
            id="regional außerhalb der Gültigkeit",
        ),
    ],
)
def test_aus_daten_lehnt_ungueltige_kalender_ab(daten: object) -> None:
    with pytest.raises(StammdatenUngueltigError):
        Feiertagskalender.aus_daten(daten)
