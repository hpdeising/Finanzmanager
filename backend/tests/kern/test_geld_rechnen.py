# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests für die Rechenhilfen in kern/geld: genaue Division und Abschneiden.

Grundlage: CLAUDE.md (Abschnitt Geld), Fachkonzept 5.1 (ohne Zwischenrundung) und Kap. 12
(``zins_ungerundet``: abgeschnitten, nicht gerundet).
"""

from decimal import Decimal, localcontext

import pytest

from app.kern.geld import RECHENGENAUIGKEIT, schneide_ab, teile


def test_teile_rechnet_mit_mindestens_vierzig_stellen() -> None:
    ergebnis = teile(Decimal(1), Decimal(3))
    assert RECHENGENAUIGKEIT >= 40
    assert ergebnis == Decimal("0." + "3" * RECHENGENAUIGKEIT)


def test_teile_ist_exakt_bei_endlicher_dezimaldarstellung() -> None:
    # 2400 x 7,27 % x 73 Tage / 365: genau 34,896 (Rechenweg GK-0001, Zeile 5).
    assert teile(Decimal("2400.00") * Decimal("7.27") * 73, Decimal(100) * 365) == Decimal("34.896")


def test_teile_haengt_nicht_vom_aktuellen_kontext_ab() -> None:
    with localcontext(prec=5):
        ergebnis = teile(Decimal(2), Decimal(3))
    assert ergebnis == Decimal("0." + "6" * (RECHENGENAUIGKEIT - 1) + "7")


def test_teile_lehnt_division_durch_null_ab() -> None:
    with pytest.raises(ZeroDivisionError):
        teile(Decimal(1), Decimal(0))


@pytest.mark.parametrize(
    ("wert", "stellen", "erwartet"),
    [
        (Decimal("43.0763835616"), 6, Decimal("43.076383")),
        (Decimal("2.4999999999"), 2, Decimal("2.49")),
        (Decimal("34.896"), 6, Decimal("34.896000")),
        (Decimal("-1.999"), 2, Decimal("-1.99")),
        (Decimal(7), 2, Decimal("7.00")),
    ],
)
def test_schneide_ab_schneidet_richtung_null(
    wert: Decimal, stellen: int, erwartet: Decimal
) -> None:
    ergebnis = schneide_ab(wert, stellen)
    assert ergebnis == erwartet
    assert str(ergebnis) == str(erwartet)


def test_schneide_ab_lehnt_negative_stellenzahl_ab() -> None:
    with pytest.raises(ValueError, match="Stellen"):
        schneide_ab(Decimal(1), -1)
