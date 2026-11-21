# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eigenschaften der Verjährung (Fachkonzept Kap. 5.5, E-36), mit zufälligen Fällen.

- Ein weiteres Ereignis mit Neubeginn verkürzt die Verjährung nie.
- Eine Hemmung verkürzt sie nie.
- § 193 BGB verschiebt das Ende nur nach hinten, auf einen Werktag.
"""

from datetime import date, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.kern.stammdaten import lade_feiertagskalender
from app.module.verbindlichkeiten.domain import (
    Bestandteil,
    Bestandteilart,
    Ereignis,
    Ereignistyp,
)
from app.module.verbindlichkeiten.verjaehrung import (
    Verjaehrungseinstellungen,
    verjaehrung_berechnen,
)

KALENDER = lade_feiertagskalender()
STICHTAG = date(2034, 12, 31)
TAGE = st.dates(min_value=date(2005, 1, 1), max_value=date(2030, 12, 31))
NEUBEGINN = st.sampled_from(
    [
        Ereignistyp.ZAHLUNG,
        Ereignistyp.ANERKENNTNIS,
        Ereignistyp.VOLLSTRECKUNGSANTRAG,
        Ereignistyp.VOLLSTRECKUNGSHANDLUNG,
    ]
)


def _ende(faellig: date, ereignisse: list[Ereignis], p01: bool = True) -> date | None:
    bestandteil = Bestandteil(
        "hauptforderung", Bestandteilart.HAUPTFORDERUNG, Decimal(100), faellig_am=faellig
    )
    ergebnis = verjaehrung_berechnen(
        [bestandteil],
        ereignisse,
        STICHTAG,
        KALENDER,
        "BY",
        einstellungen=Verjaehrungseinstellungen(p01_193_bgb=p01),
    )
    return ergebnis.eintraege[0].ende


@given(TAGE, st.lists(st.tuples(NEUBEGINN, TAGE), max_size=4), NEUBEGINN, TAGE)
def test_weiterer_neubeginn_verkuerzt_nie(
    faellig: date,
    vorhanden: list[tuple[Ereignistyp, date]],
    typ: Ereignistyp,
    tag: date,
) -> None:
    ereignisse = [Ereignis(t, d) for t, d in vorhanden]
    vorher = _ende(faellig, ereignisse)
    nachher = _ende(faellig, [*ereignisse, Ereignis(typ, tag)])
    assert vorher is not None
    assert nachher is not None
    assert nachher >= vorher


@given(TAGE, TAGE, st.integers(min_value=0, max_value=400))
def test_hemmung_verkuerzt_nie(faellig: date, zustellung: date, tage_bis_ende: int) -> None:
    ohne = _ende(faellig, [])
    beendet = zustellung + timedelta(days=tage_bis_ende)
    mit = _ende(
        faellig,
        [
            Ereignis(Ereignistyp.ZUSTELLUNG_MAHNBESCHEID, zustellung),
            Ereignis(Ereignistyp.MAHNVERFAHREN_OHNE_TITEL_BEENDET, beendet),
        ],
    )
    assert ohne is not None
    assert mit is not None
    assert mit >= ohne


@given(TAGE, st.lists(st.tuples(NEUBEGINN, TAGE), max_size=3))
def test_193_bgb_verschiebt_nur_nach_hinten(
    faellig: date, vorhanden: list[tuple[Ereignistyp, date]]
) -> None:
    ereignisse = [Ereignis(t, d) for t, d in vorhanden]
    ohne = _ende(faellig, ereignisse, p01=False)
    mit = _ende(faellig, ereignisse, p01=True)
    assert ohne is not None
    assert mit is not None
    assert mit >= ohne
    assert mit.weekday() < 5
