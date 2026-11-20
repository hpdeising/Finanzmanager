# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests für das Laden und Abfragen des Basiszinssatzes (Fachkonzept Kap. 7).

Die Tests hier arbeiten mit ausgedachten Reihen. Die Datei im Repository prüft
``test_basiszinssatz_datei.py``.
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.kern.stammdaten import (
    Basiszinsreihe,
    StammdatenFehlenError,
    StammdatenUngueltigError,
    lade_basiszinsreihe,
)


def _daten(*eintraege: tuple[object, object]) -> dict[str, object]:
    return {
        "quelle": "Ausgedachte Testreihe",
        "geprueft_von": "Test",
        "eintraege": [{"gueltig_ab": ab, "satz": satz} for ab, satz in eintraege],
    }


REIHE = Basiszinsreihe.aus_daten(
    _daten(
        (date(2016, 7, 1), "-0.88"),
        (date(2017, 1, 1), "-0.88"),
        (date(2017, 7, 1), "1.50"),
    )
)


@pytest.mark.parametrize(
    ("tag", "erwartet"),
    [
        (date(2016, 7, 1), Decimal("-0.88")),
        (date(2016, 12, 31), Decimal("-0.88")),
        (date(2017, 1, 1), Decimal("-0.88")),
        (date(2017, 6, 30), Decimal("-0.88")),
        (date(2017, 7, 1), Decimal("1.50")),
        (date(2017, 12, 31), Decimal("1.50")),
    ],
)
def test_satz_am_liefert_den_satz_des_halbjahrs(tag: date, erwartet: Decimal) -> None:
    assert REIHE.satz_am(tag) == erwartet


@pytest.mark.parametrize("tag", [date(2016, 6, 30), date(2018, 1, 1), date(2030, 5, 5)])
def test_satz_am_wirft_ausserhalb_der_reihe(tag: date) -> None:
    """Fehlt ein gültiger Eintrag, wird nicht geschätzt (CLAUDE.md, Stammdaten)."""
    with pytest.raises(StammdatenFehlenError):
        REIHE.satz_am(tag)


def test_lade_basiszinsreihe_liest_yaml(tmp_path: Path) -> None:
    datei = tmp_path / "basiszinssatz.yaml"
    datei.write_text(
        "quelle: Testquelle\n"
        'geprueft_von: "Test"\n'
        "hinweis: nur ein Test\n"
        "eintraege:\n"
        "  - gueltig_ab: 2025-07-01\n"
        '    satz: "1.27"\n'
        "  - gueltig_ab: 2026-01-01\n"
        '    satz: "1.27"\n',
        encoding="utf-8",
    )
    reihe = lade_basiszinsreihe(datei)
    assert reihe.quelle == "Testquelle"
    assert reihe.geprueft_von == "Test"
    assert [(e.gueltig_ab, e.satz) for e in reihe.eintraege] == [
        (date(2025, 7, 1), Decimal("1.27")),
        (date(2026, 1, 1), Decimal("1.27")),
    ]


def test_lade_basiszinsreihe_meldet_fehlende_datei(tmp_path: Path) -> None:
    with pytest.raises(StammdatenUngueltigError):
        lade_basiszinsreihe(tmp_path / "fehlt.yaml")


def test_lade_basiszinsreihe_meldet_kaputtes_yaml(tmp_path: Path) -> None:
    datei = tmp_path / "basiszinssatz.yaml"
    datei.write_text("eintraege: [\n", encoding="utf-8")
    with pytest.raises(StammdatenUngueltigError):
        lade_basiszinsreihe(datei)


@pytest.mark.parametrize(
    "daten",
    [
        pytest.param([], id="keine Zuordnung"),
        pytest.param({**_daten((date(2025, 7, 1), "1.27")), "quelle": ""}, id="leere Quelle"),
        pytest.param(
            {k: v for k, v in _daten((date(2025, 7, 1), "1.27")).items() if k != "geprueft_von"},
            id="ohne Prüfer",
        ),
        pytest.param({**_daten((date(2025, 7, 1), "1.27")), "extra": 1}, id="unbekanntes Feld"),
        pytest.param(_daten(), id="keine Einträge"),
        pytest.param(_daten((date(2025, 7, 1), Decimal("1.27"))), id="Satz nicht als Text"),
        pytest.param(_daten((date(2025, 7, 1), 1)), id="Satz als Zahl"),
        pytest.param(_daten((date(2025, 7, 1), "1,27")), id="Satz mit Komma"),
        pytest.param(_daten(("2025-07-01", "1.27")), id="Datum als Text"),
        pytest.param(_daten((datetime(2025, 7, 1), "1.27")), id="Datum mit Uhrzeit"),  # noqa: DTZ001
        pytest.param(_daten((date(2025, 7, 2), "1.27")), id="nicht am Halbjahresbeginn"),
        pytest.param(_daten((date(2025, 4, 1), "1.27")), id="kein Halbjahresbeginn"),
        pytest.param(
            _daten((date(2026, 1, 1), "1.27"), (date(2025, 7, 1), "1.27")), id="absteigend"
        ),
        pytest.param(_daten((date(2025, 7, 1), "1.27"), (date(2025, 7, 1), "1.27")), id="doppelt"),
        pytest.param(_daten((date(2025, 1, 1), "2.27"), (date(2026, 1, 1), "1.27")), id="Lücke"),
    ],
)
def test_aus_daten_lehnt_ungueltige_reihen_ab(daten: object) -> None:
    with pytest.raises(StammdatenUngueltigError):
        Basiszinsreihe.aus_daten(daten)


def test_meldung_nennt_keinen_satz() -> None:
    with pytest.raises(StammdatenUngueltigError) as fehler:
        Basiszinsreihe.aus_daten(_daten((date(2025, 7, 1), "9,99")))
    assert "9,99" not in str(fehler.value)
