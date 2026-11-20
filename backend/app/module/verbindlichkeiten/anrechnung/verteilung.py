# SPDX-License-Identifier: AGPL-3.0-or-later
"""Anrechnung einer Zahlung auf die offenen Posten (Fachkonzept Kap. 5.3)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.module.verbindlichkeiten.domain import Gruppe, Zahlung


@dataclass(slots=True)
class Posten:
    """Offener Betrag einer Gruppe eines Bestandteils, etwa die Zinsen eines Abschnitts.

    ``alter`` ordnet die Posten einer Gruppe: der kleinste zuerst (älteste Position zuerst,
    Kap. 5.3). ``offen`` sinkt mit jeder Anrechnung.
    """

    kennung: str
    gruppe: Gruppe
    alter: tuple[date, int]
    offen: Decimal


@dataclass(frozen=True, slots=True)
class Anrechnungszeile:
    """Was eine Zahlung auf eine Gruppe eines Bestandteils anrechnet (Kap. 12, Anrechnung).

    ``gruppe`` und ``bestandteil`` sind leer bei einer Überzahlung, ebenso ``offen_danach``.
    """

    zahlung: Zahlung
    bestandteil: str | None
    gruppe: Gruppe | None
    angerechnet: Decimal
    offen_danach: Decimal | None


def verteile(
    zahlung: Zahlung, gruppenfolge: Sequence[Gruppe], posten: Sequence[Posten]
) -> tuple[list[Anrechnungszeile], Decimal]:
    """Zahlung auf die Posten anrechnen; liefert die Zeilen und die Überzahlung.

    Die Gruppen kommen in der Folge der Anrechnungsregel (§ 367 Abs. 1 BGB, § 497 Abs. 3 BGB
    oder individuell), innerhalb einer Gruppe die älteste Position zuerst (Kap. 5.3, Voreinstellung
    zu Prüfpunkt P-07). Die Zahlung wird genau verteilt; was nach allen Posten übrig bleibt, ist
    Überzahlung. Ändert ``offen`` der Posten.
    """
    rest = zahlung.betrag
    angerechnet: dict[tuple[str, Gruppe], Decimal] = {}
    for gruppe in gruppenfolge:
        for p in sorted((p for p in posten if p.gruppe is gruppe), key=lambda p: p.alter):
            teil = min(rest, p.offen)
            if teil <= 0:
                continue
            p.offen -= teil
            rest -= teil
            schluessel = (p.kennung, gruppe)
            angerechnet[schluessel] = angerechnet.get(schluessel, Decimal(0)) + teil
    zeilen = [
        Anrechnungszeile(
            zahlung,
            kennung,
            gruppe,
            betrag,
            sum(
                (p.offen for p in posten if p.kennung == kennung and p.gruppe is gruppe),
                Decimal(0),
            ),
        )
        for (kennung, gruppe), betrag in angerechnet.items()
    ]
    if rest > 0:
        zeilen.append(Anrechnungszeile(zahlung, None, None, rest, None))
    return zeilen, rest
