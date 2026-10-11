# SPDX-License-Identifier: AGPL-3.0-or-later
"""Beträge einlesen, kaufmännisch runden und als Text ausgeben.

Grundlage: CLAUDE.md (Abschnitt Geld) und Fachkonzept Kapitel 5.1.

- Beträge sind ausschließlich ``decimal.Decimal``. Fließkommazahlen werden abgelehnt,
  weil sie Dezimalbeträge wie 0,10 € nicht exakt darstellen können.
- Gerundet wird nur hier, kaufmännisch auf Cent.
- In JSON stehen Beträge als Text in Festkommaschreibweise.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

# Kanonische Textform: optionales Minus, Ziffern, optional Punkt und Ziffern.
_KANONISCH = re.compile(r"-?\d+(?:\.\d+)?")


def betrag(wert: object) -> Decimal:
    """Betrag aus Text, ganzer Zahl oder ``Decimal`` erzeugen.

    Text muss kanonisch sein (``"125.30"``, ``"-0.01"``). Deutsche Schreibweise mit
    Komma übersetzt die Oberfläche, nicht der Kern.

    Raises:
        TypeError: bei jedem anderen Typ, insbesondere Fließkommazahlen und ``bool``.
        ValueError: bei nicht kanonischem Text oder nicht endlichen Werten.
    """
    if isinstance(wert, Decimal):
        ergebnis = wert
    elif isinstance(wert, int) and not isinstance(wert, bool):
        ergebnis = Decimal(wert)
    elif isinstance(wert, str):
        if not _KANONISCH.fullmatch(wert):
            msg = f"Betrag muss die Form '-123.45' haben, nicht {wert!r}."
            raise ValueError(msg)
        ergebnis = Decimal(wert)
    else:
        msg = f"Betrag nur aus str, int oder Decimal, nicht aus {type(wert).__name__}."
        raise TypeError(msg)
    _pruefe_endlich(ergebnis)
    return ergebnis


def runde_auf_cent(wert: Decimal) -> Decimal:
    """Kaufmännisch auf Cent runden (Fachkonzept 5.1).

    Ab einem halben Cent wird betragsmäßig aufgerundet, symmetrisch um null:
    ``0.005`` → ``0.01``, ``-0.005`` → ``-0.01``. Ein gerundetes ``-0.00``
    wird als ``0.00`` zurückgegeben.
    """
    _pruefe_endlich(wert)
    gerundet = wert.quantize(CENT, rounding=ROUND_HALF_UP)
    return gerundet.copy_abs() if gerundet.is_zero() else gerundet


def als_text(wert: Decimal) -> str:
    """Betrag als Text für JSON: Festkomma, mindestens zwei Nachkommastellen.

    Es wird nicht gerundet; mehr als zwei Nachkommastellen bleiben erhalten.
    """
    _pruefe_endlich(wert)
    exponent = wert.as_tuple().exponent
    if isinstance(exponent, int) and exponent > -2:
        # Nur Nullen anhängen; Quantisieren auf mehr Stellen rundet nie.
        wert = wert.quantize(CENT)
    return format(wert, "f")


def _pruefe_endlich(wert: Decimal) -> None:
    if not wert.is_finite():
        msg = f"Betrag muss endlich sein, nicht {wert}."
        raise ValueError(msg)
