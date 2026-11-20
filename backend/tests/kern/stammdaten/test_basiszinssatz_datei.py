# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prüfung der Datei ``stammdaten/basiszinssatz.yaml`` im Repository (Fachkonzept Kap. 7)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.kern.stammdaten import lade_basiszinsreihe

# Vom Maintainer am 20.11.2026 freigegebene Reihe (Bundesbank-Tabelle „Basiszinssatz nach
# § 247 BGB“, abgeglichen mit IWW); die Werte ab 2024 stammen aus GK-0001 und Kap. 7.
# Die Datei muss sie genauso enthalten.
_FREIGEGEBEN = {
    2002: ("2.57", "2.47"),
    2003: ("1.97", "1.22"),
    2004: ("1.14", "1.13"),
    2005: ("1.21", "1.17"),
    2006: ("1.37", "1.95"),
    2007: ("2.70", "3.19"),
    2008: ("3.32", "3.19"),
    2009: ("1.62", "0.12"),
    2010: ("0.12", "0.12"),
    2011: ("0.12", "0.37"),
    2012: ("0.12", "0.12"),
    2013: ("-0.13", "-0.38"),
    2014: ("-0.63", "-0.73"),
    2015: ("-0.83", "-0.83"),
    2016: ("-0.83", "-0.88"),
    **dict.fromkeys(range(2017, 2023), ("-0.88", "-0.88")),
    2023: ("1.62", "3.12"),
    2024: ("3.62", "3.37"),
    2025: ("2.27", "1.27"),
    2026: ("1.27", "1.52"),
}
BELEGTE_SAETZE = [
    (date(jahr, monat, 1), Decimal(satz))
    for jahr, saetze in _FREIGEGEBEN.items()
    for monat, satz in zip((1, 7), saetze, strict=True)
]


def test_reihe_beginnt_2002_und_ist_vollstaendig_belegt() -> None:
    reihe = lade_basiszinsreihe()
    assert reihe.eintraege[0].gueltig_ab == date(2002, 1, 1)
    assert len(BELEGTE_SAETZE) == 50
    assert [(e.gueltig_ab, e.satz) for e in reihe.eintraege[:50]] == BELEGTE_SAETZE


def test_beispiel_aus_kapitel_5_2_schritt_6() -> None:
    """Vom 01.07.2016 bis 31.12.2022 lag der Basiszinssatz bei -0,88 %."""
    reihe = lade_basiszinsreihe()
    assert reihe.satz_am(date(2016, 7, 1)) == Decimal("-0.88")
    assert reihe.satz_am(date(2022, 12, 31)) == Decimal("-0.88")
    assert reihe.satz_am(date(2016, 6, 30)) != Decimal("-0.88")
    assert reihe.satz_am(date(2023, 1, 1)) != Decimal("-0.88")


@pytest.mark.parametrize(("gueltig_ab", "satz"), BELEGTE_SAETZE)
def test_datei_enthaelt_die_belegten_saetze(gueltig_ab: date, satz: Decimal) -> None:
    assert lade_basiszinsreihe().satz_am(gueltig_ab) == satz


def test_datei_nennt_quelle_und_pruefer() -> None:
    reihe = lade_basiszinsreihe()
    assert "Bundesbank" in reihe.quelle
    assert reihe.geprueft_von


def _plus_monate(tag: date, monate: int) -> date:
    jahr, monat = divmod(tag.month - 1 + monate, 12)
    return date(tag.year + jahr, monat + 1, tag.day)


def test_juengster_eintrag_hoechstens_sechs_monate_alt() -> None:
    """CI-Prüfung aus Kap. 7: Liegt der jüngste Eintrag mehr als sechs Monate zurück,
    schlägt der Build fehl. Abhilfe: den neuen Satz der Bundesbank eintragen."""
    juengster = lade_basiszinsreihe().eintraege[-1].gueltig_ab
    heute = datetime.now(UTC).date()
    assert heute <= _plus_monate(juengster, 6), (
        f"Jüngster Basiszinssatz gilt ab {juengster.isoformat()}; "
        "stammdaten/basiszinssatz.yaml um den aktuellen Satz ergänzen."
    )
