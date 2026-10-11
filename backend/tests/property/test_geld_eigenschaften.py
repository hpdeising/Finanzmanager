# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eigenschaften von kern/geld, geprüft mit zufällig erzeugten Beträgen (hypothesis)."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.kern.geld import als_text, betrag, runde_auf_cent, speicherbar

# Beträge im Wertebereich von NUMERIC(19,4): bis 15 Stellen vor, 4 nach dem Komma.
BETRAEGE = st.decimals(
    min_value=Decimal("-999999999999999.9999"),
    max_value=Decimal("999999999999999.9999"),
    places=4,
    allow_nan=False,
    allow_infinity=False,
)
HALBER_CENT = Decimal("0.005")


@given(BETRAEGE)
def test_runden_ist_idempotent(wert: Decimal) -> None:
    einmal = runde_auf_cent(wert)
    assert runde_auf_cent(einmal) == einmal


@given(BETRAEGE)
def test_rundung_weicht_hoechstens_einen_halben_cent_ab(wert: Decimal) -> None:
    assert abs(runde_auf_cent(wert) - wert) <= HALBER_CENT


@given(BETRAEGE)
def test_rundung_ist_symmetrisch_um_null(wert: Decimal) -> None:
    assert runde_auf_cent(-wert) == -runde_auf_cent(wert)


@given(BETRAEGE)
def test_text_und_zurueck_ergibt_denselben_betrag(wert: Decimal) -> None:
    assert betrag(als_text(wert)) == wert


GRENZE = 10**15


@given(BETRAEGE)
def test_speicherbar_laesst_jeden_numeric_19_4_betrag_unveraendert(wert: Decimal) -> None:
    assert speicherbar(wert) == wert


@given(
    st.integers(min_value=5, max_value=12),
    st.integers(min_value=-(10**18), max_value=10**18),
    st.integers(min_value=1, max_value=9),
)
def test_speicherbar_lehnt_jede_fuenfte_nachkommastelle_ab(
    stellen: int, vorne: int, letzte_ziffer: int
) -> None:
    """Konstruktiv: Die letzte Ziffer ist nie 0, also gibt es mehr als vier Nachkommastellen.

    Mit höchstens 19 Ziffern und mindestens fünf Nachkommastellen bleibt der Wert unter 10^15.
    """
    ziffern = vorne * 10 + (letzte_ziffer if vorne >= 0 else -letzte_ziffer)
    wert = Decimal(ziffern).scaleb(-stellen)
    with pytest.raises(ValueError, match="Nachkommastellen"):
        speicherbar(wert)


@given(st.integers(min_value=GRENZE, max_value=10**40), st.booleans())
def test_speicherbar_lehnt_jeden_betrag_ab_10_hoch_15_ab(betrag_ganz: int, negativ: bool) -> None:
    wert = Decimal(-betrag_ganz if negativ else betrag_ganz)
    with pytest.raises(ValueError, match="zu groß"):
        speicherbar(wert)
