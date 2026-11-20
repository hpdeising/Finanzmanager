# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests der Tageszählung (Fachkonzept Kap. 5.1, E-22, E-31, E-34).

Die Fälle für ``30_360`` sind die Tabelle aus Kap. 5.1. Wo die Tabelle kein Jahr nennt,
steht hier 2027; diese Zeilen berühren keinen Februar, das Jahr ändert nichts.
"""

from datetime import date

import pytest

from app.module.verbindlichkeiten.domain import Tageszaehlung
from app.module.verbindlichkeiten.zinsen import tagesbasis, zinstage

T = date

# (von, bis, Vortag unverzinst, Vortag verzinst); None, wo die Tabelle „–“ zeigt.
TABELLE_30_360: list[tuple[date, date, int, int | None]] = [
    (T(2027, 1, 1), T(2027, 1, 30), 30, 30),
    (T(2027, 1, 1), T(2027, 1, 31), 30, 30),
    (T(2027, 1, 30), T(2027, 1, 31), 1, 1),
    (T(2027, 1, 31), T(2027, 1, 31), 1, 0),
    (T(2027, 1, 31), T(2027, 2, 28), 29, 28),
    (T(2027, 2, 1), T(2027, 2, 28), 28, 28),
    (T(2028, 2, 1), T(2028, 2, 29), 29, 29),
    (T(2027, 3, 1), T(2027, 3, 1), 1, 3),
    (T(2027, 3, 1), T(2027, 3, 31), 30, 32),
    # „01.03.–31.03.2027 nach einer Pause bis 28.02.2027“: Vortag unverzinst.
    (T(2027, 3, 1), T(2027, 3, 31), 30, None),
    (T(2027, 2, 1), T(2027, 3, 31), 60, 60),
    (T(2027, 2, 28), T(2027, 3, 31), 33, 33),
    (T(2027, 3, 31), T(2027, 4, 30), 31, 30),
    (T(2027, 1, 1), T(2027, 12, 31), 360, 360),
    (T(2027, 3, 1), T(2028, 2, 29), 359, 361),
    (T(2027, 1, 31), T(2028, 1, 30), 361, 360),
]


@pytest.mark.parametrize(("von", "bis", "unverzinst", "verzinst"), TABELLE_30_360)
def test_30_360_wie_tabelle_kap_5_1(
    von: date, bis: date, unverzinst: int, verzinst: int | None
) -> None:
    zaehlung = Tageszaehlung.DREISSIG_360
    assert zinstage(von, bis, zaehlung, vortag_verzinst=False) == unverzinst
    if verzinst is not None:
        assert zinstage(von, bis, zaehlung, vortag_verzinst=True) == verzinst


def test_30_360_geteilt_wie_ungeteilt() -> None:
    """Kap. 5.1: ungeteilt 01.02.–31.03.2027 sind 60 Tage, geteilt am 01.03. 28 + 32."""
    zaehlung = Tageszaehlung.DREISSIG_360
    assert zinstage(T(2027, 2, 1), T(2027, 2, 28), zaehlung, vortag_verzinst=False) == 28
    assert zinstage(T(2027, 3, 1), T(2027, 3, 31), zaehlung, vortag_verzinst=True) == 32


@pytest.mark.parametrize(
    "zaehlung", [Tageszaehlung.ACT_365, Tageszaehlung.ACT_360, Tageszaehlung.ACT_ACT]
)
@pytest.mark.parametrize("vortag_verzinst", [False, True])
def test_taggenaue_arten_zaehlen_ersten_und_letzten_tag(
    zaehlung: Tageszaehlung, vortag_verzinst: bool
) -> None:
    assert zinstage(T(2025, 3, 15), T(2025, 5, 20), zaehlung, vortag_verzinst) == 67
    assert zinstage(T(2025, 5, 21), T(2025, 5, 21), zaehlung, vortag_verzinst) == 1
    assert zinstage(T(2028, 2, 1), T(2028, 3, 1), zaehlung, vortag_verzinst) == 30


@pytest.mark.parametrize(
    ("zaehlung", "von", "erwartet"),
    [
        (Tageszaehlung.ACT_365, T(2027, 5, 1), 365),
        (Tageszaehlung.ACT_365, T(2028, 5, 1), 365),  # auch im Schaltjahr (E-22)
        (Tageszaehlung.ACT_360, T(2028, 5, 1), 360),
        (Tageszaehlung.ACT_ACT, T(2027, 5, 1), 365),
        (Tageszaehlung.ACT_ACT, T(2028, 5, 1), 366),  # Schaltjahr (E-31)
        (Tageszaehlung.DREISSIG_360, T(2028, 5, 1), 360),
    ],
)
def test_tagesbasis(zaehlung: Tageszaehlung, von: date, erwartet: int) -> None:
    assert tagesbasis(zaehlung, von) == erwartet


def test_zinstage_lehnt_ende_vor_beginn_ab() -> None:
    with pytest.raises(ValueError, match="Ende"):
        zinstage(T(2027, 2, 2), T(2027, 2, 1), Tageszaehlung.ACT_365, vortag_verzinst=False)


def test_act_act_lehnt_abschnitt_ueber_jahreswechsel_ab() -> None:
    """E-31: Bei act_act wird an jedem 01.01. geteilt; ein Abschnitt hat nur eine Tagesbasis."""
    with pytest.raises(ValueError, match="Jahreswechsel"):
        zinstage(T(2027, 12, 31), T(2028, 1, 1), Tageszaehlung.ACT_ACT, vortag_verzinst=False)
