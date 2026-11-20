# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prüfung der Datei ``stammdaten/basiszinssatz.yaml`` im Repository (Fachkonzept Kap. 7)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.kern.stammdaten import lade_basiszinsreihe

# Werte, die der Maintainer mit GK-0001 aus der Übersicht der Bundesbank angegeben hat,
# ergänzt um die Beispieleinträge aus Fachkonzept Kap. 7. Die Datei muss sie genauso enthalten.
BELEGTE_SAETZE = [
    (date(2024, 1, 1), Decimal("3.62")),
    (date(2024, 7, 1), Decimal("3.37")),
    (date(2025, 1, 1), Decimal("2.27")),
    (date(2025, 7, 1), Decimal("1.27")),
    (date(2026, 1, 1), Decimal("1.27")),
    (date(2026, 7, 1), Decimal("1.52")),
]


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
