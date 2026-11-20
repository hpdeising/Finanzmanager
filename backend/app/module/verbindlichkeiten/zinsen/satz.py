# SPDX-License-Identifier: AGPL-3.0-or-later
"""Jahressatz einer Zinsregel an einem Tag (Fachkonzept Kap. 5.2, Tabelle und Schritt 6)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.kern.stammdaten import Basiszinsreihe
from app.module.verbindlichkeiten.domain import Zinsregel, Zinsregeltyp

# Aufschläge in Prozentpunkten laut Kap. 5.2, Tabelle. Rechtsregeln, keine Stammdaten.
AUFSCHLAG_288_1 = Decimal(5)  # § 288 Abs. 1 S. 2 BGB
AUFSCHLAG_288_2 = Decimal(9)  # § 288 Abs. 2 BGB
AUFSCHLAG_KOSTENFESTSETZUNG = Decimal(5)  # § 104 Abs. 1 S. 2 ZPO


@dataclass(frozen=True, slots=True)
class Jahressatz:
    """Jahressatz in Prozent; ``basiszins`` ist leer bei festem Satz (Kap. 12, Rechenweg)."""

    basiszins: Decimal | None
    satz: Decimal


def jahressatz(regel: Zinsregel, tag: date, reihe: Basiszinsreihe) -> Jahressatz:
    """Jahressatz der Zinsregel am ``tag``.

    - ``gesetzlich_288_1``: Basiszinssatz + 5 Prozentpunkte (§ 288 Abs. 1 S. 2 BGB)
    - ``gesetzlich_288_2``: Basiszinssatz + 9 Prozentpunkte (§ 288 Abs. 2 BGB)
    - ``kostenfestsetzung``: Basiszinssatz + 5 Prozentpunkte (§ 104 Abs. 1 S. 2 ZPO)
    - ``basiszins_plus``: Basiszinssatz + Aufschlag laut Titel oder Vertrag
    - ``fest``: fester Satz laut Titel oder Vertrag

    Der Basiszinssatz kommt aus den Stammdaten (§ 247 BGB). Der Satz ist Basiszinssatz plus
    Aufschlag, auch bei negativem Basiszinssatz (Kap. 5.2 Schritt 6).

    Raises:
        StammdatenFehlenError: wenn für ``tag`` kein Basiszinssatz vorliegt.
        ValueError: bei der Zinsregel ``keine``.
    """
    if regel.typ is Zinsregeltyp.KEINE:
        msg = "Die Zinsregel keine hat keinen Satz."
        raise ValueError(msg)
    if regel.typ is Zinsregeltyp.FEST:
        if regel.satz is None:  # durch Zinsregel ausgeschlossen
            msg = "Zinsregel fest ohne Satz."
            raise ValueError(msg)
        return Jahressatz(None, regel.satz)
    basiszins = reihe.satz_am(tag)
    return Jahressatz(basiszins, basiszins + _aufschlag(regel))


def _aufschlag(regel: Zinsregel) -> Decimal:
    if regel.typ is Zinsregeltyp.GESETZLICH_288_1:
        return AUFSCHLAG_288_1
    if regel.typ is Zinsregeltyp.GESETZLICH_288_2:
        return AUFSCHLAG_288_2
    if regel.typ is Zinsregeltyp.KOSTENFESTSETZUNG:
        return AUFSCHLAG_KOSTENFESTSETZUNG
    if regel.aufschlag is None:  # durch Zinsregel ausgeschlossen
        msg = "Zinsregel basiszins_plus ohne Aufschlag."
        raise ValueError(msg)
    return regel.aufschlag
