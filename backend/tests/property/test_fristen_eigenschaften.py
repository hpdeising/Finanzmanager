# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eigenschaften der Fristberechnung (Fachkonzept Kap. 5.4), mit zufälligen Fristen.

Der Feiertagskalender ist ausgedacht: zufällige Tage in zufälligen Ländern.
"""

from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.kern.stammdaten import LAENDER, Feiertagskalender
from app.module.verbindlichkeiten.fristen import Dauer, Einheit, Fristart, fristende

ANFANG = date(2020, 1, 1)
ENDE = date(2075, 12, 31)  # deckt 36 Jahre ab dem letzten Ereignistag ab
TAGE = st.dates(min_value=ANFANG, max_value=date(2035, 12, 31))
DAUERN = st.builds(Dauer, st.integers(min_value=1, max_value=36), st.sampled_from(list(Einheit)))
LAND = st.sampled_from(sorted(LAENDER))


@st.composite
def _kalender(draw: st.DrawFn) -> Feiertagskalender:
    tage = sorted(
        draw(st.sets(st.dates(min_value=ANFANG, max_value=ENDE), min_size=1, max_size=40))
    )
    return Feiertagskalender.aus_daten(
        {
            "quelle": "Ausgedachter Testkalender",
            "geprueft_von": "Test",
            "gueltig_ab": ANFANG,
            "gueltig_bis": ENDE,
            "feiertage": [
                {
                    "datum": tag,
                    "name": "Testtag",
                    "laender": draw(st.lists(LAND, min_size=1, max_size=3, unique=True)),
                }
                for tag in tage
            ],
        }
    )


@given(TAGE, DAUERN)
def test_ende_liegt_nach_dem_ereignis(ereignistag: date, dauer: Dauer) -> None:
    """§ 187 Abs. 1 BGB: Der Tag des Ereignisses zählt nicht; das Ende liegt danach."""
    assert fristende(ereignistag, dauer, Fristart.INFORMATION) > ereignistag


@given(TAGE, st.integers(min_value=1, max_value=36))
def test_monatsfrist_endet_am_selben_tag_oder_monatsende(ereignistag: date, monate: int) -> None:
    """§ 188 Abs. 2 und 3 BGB."""
    ende = fristende(ereignistag, Dauer(monate, Einheit.MONATE), Fristart.INFORMATION)
    assert (ende.year - ereignistag.year) * 12 + ende.month - ereignistag.month == monate
    naechster = ende + timedelta(days=1)
    assert ende.day == ereignistag.day or (ende.day < ereignistag.day and naechster.day == 1)


@given(TAGE, DAUERN, _kalender(), LAND)
def test_prozessuale_frist_endet_an_einem_werktag(
    ereignistag: date, dauer: Dauer, kalender: Feiertagskalender, land: str
) -> None:
    """§ 222 Abs. 2 ZPO: nie an Samstag, Sonntag oder Feiertag, und nur bis zum nächsten
    Werktag nach dem Ende nach §§ 187, 188 BGB verschoben."""
    ohne = fristende(ereignistag, dauer, Fristart.INFORMATION)
    mit = fristende(ereignistag, dauer, Fristart.PROZESSUAL, kalender, land)
    assert mit >= ohne
    assert mit.weekday() < 5
    assert not kalender.ist_feiertag(mit, land)
    tag = ohne
    while tag < mit:
        assert tag.weekday() >= 5 or kalender.ist_feiertag(tag, land)
        tag += timedelta(days=1)
