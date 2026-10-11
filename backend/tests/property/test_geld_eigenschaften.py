# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eigenschaften von kern/geld, geprüft mit zufällig erzeugten Beträgen (hypothesis)."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.kern.geld import als_text, betrag, runde_auf_cent

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
