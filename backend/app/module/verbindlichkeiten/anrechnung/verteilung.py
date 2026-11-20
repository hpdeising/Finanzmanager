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
    E-35). ``entstanden_am`` ist der Entstehungstag des Bestandteils; ohne ihn gilt der Posten
    als von Anfang an vorhanden. ``offen`` sinkt mit jeder Anrechnung.
    """

    kennung: str
    gruppe: Gruppe
    alter: tuple[date, int]
    offen: Decimal
    entstanden_am: date | None = None

    def besteht_am(self, tag: date) -> bool:
        return self.entstanden_am is None or self.entstanden_am <= tag


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
    oder individuell), innerhalb einer Gruppe die älteste Position zuerst (E-35). Angerechnet
    wird nur auf Posten von Bestandteilen, die spätestens am Tag der Wertstellung entstanden
    sind (Kap. 5.3). Die Zahlung wird genau verteilt; was übrig bleibt, ist Überzahlung und bleibt
    es, auch wenn später Bestandteile entstehen (Prüfpunkt P-20 offen). Ändert ``offen`` der
    Posten.
    """
    rest = zahlung.betrag
    angerechnet: dict[tuple[str, Gruppe], Decimal] = {}
    for gruppe in gruppenfolge:
        anrechenbar = (p for p in posten if p.gruppe is gruppe and p.besteht_am(zahlung.datum))
        for p in sorted(anrechenbar, key=lambda p: p.alter):
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
