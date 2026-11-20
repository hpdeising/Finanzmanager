# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests des Jahressatzes je Zinsregel (Fachkonzept Kap. 5.2, Tabelle und Schritt 6)."""

from datetime import date
from decimal import Decimal

import pytest

from app.kern.stammdaten import Basiszinsreihe, StammdatenFehlenError
from app.module.verbindlichkeiten.domain import Zinsregel, Zinsregeltyp
from app.module.verbindlichkeiten.zinsen import jahressatz

# Ausgedachte Reihe; den Satz -0,88 % nennt Kap. 5.2 Schritt 6 für 01.07.2016 bis 31.12.2022.
REIHE = Basiszinsreihe.aus_daten(
    {
        "quelle": "Ausgedachte Testreihe",
        "geprueft_von": "Test",
        "eintraege": [
            {"gueltig_ab": date(2022, 7, 1), "satz": "-0.88"},
            {"gueltig_ab": date(2023, 1, 1), "satz": "1.62"},
        ],
    }
)
AB = date(2022, 1, 1)


@pytest.mark.parametrize(
    ("regel", "tag", "basiszins", "satz"),
    [
        # Kap. 5.2 Schritt 6: Basiszinssatz -0,88 %, Verzugszins § 288 Abs. 1 BGB 4,12 %.
        (Zinsregel(Zinsregeltyp.GESETZLICH_288_1, ab=AB), date(2022, 12, 31), "-0.88", "4.12"),
        (Zinsregel(Zinsregeltyp.GESETZLICH_288_1, ab=AB), date(2023, 1, 1), "1.62", "6.62"),
        (Zinsregel(Zinsregeltyp.GESETZLICH_288_2, ab=AB), date(2022, 12, 31), "-0.88", "8.12"),
        (Zinsregel(Zinsregeltyp.KOSTENFESTSETZUNG, ab=AB), date(2023, 1, 1), "1.62", "6.62"),
        (
            Zinsregel(Zinsregeltyp.BASISZINS_PLUS, ab=AB, aufschlag=Decimal("2.5")),
            date(2022, 12, 31),
            "-0.88",
            "1.62",
        ),
    ],
)
def test_basiszinsabhaengige_saetze(regel: Zinsregel, tag: date, basiszins: str, satz: str) -> None:
    ergebnis = jahressatz(regel, tag, REIHE)
    assert ergebnis.basiszins == Decimal(basiszins)
    assert ergebnis.satz == Decimal(satz)


def test_fester_satz_braucht_keinen_basiszins() -> None:
    regel = Zinsregel(Zinsregeltyp.FEST, ab=AB, satz=Decimal(5))
    # Außerhalb der Reihe: ein fester Satz fragt die Stammdaten nicht ab.
    ergebnis = jahressatz(regel, date(2030, 1, 1), REIHE)
    assert ergebnis.basiszins is None
    assert ergebnis.satz == Decimal(5)


def test_fehlender_basiszins_wirft() -> None:
    regel = Zinsregel(Zinsregeltyp.GESETZLICH_288_1, ab=AB)
    with pytest.raises(StammdatenFehlenError):
        jahressatz(regel, date(2022, 6, 30), REIHE)


def test_zinsregel_keine_hat_keinen_satz() -> None:
    with pytest.raises(ValueError, match="keine"):
        jahressatz(Zinsregel(Zinsregeltyp.KEINE), date(2023, 1, 1), REIHE)


@pytest.mark.parametrize(
    ("typ", "abhaengig"),
    [
        (Zinsregeltyp.GESETZLICH_288_1, True),
        (Zinsregeltyp.GESETZLICH_288_2, True),
        (Zinsregeltyp.KOSTENFESTSETZUNG, True),
        (Zinsregeltyp.BASISZINS_PLUS, True),
        (Zinsregeltyp.FEST, False),
        (Zinsregeltyp.KEINE, False),
    ],
)
def test_basiszinsabhaengig(typ: Zinsregeltyp, abhaengig: bool) -> None:
    assert typ.basiszinsabhaengig is abhaengig
