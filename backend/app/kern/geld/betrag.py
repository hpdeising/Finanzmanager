# SPDX-License-Identifier: AGPL-3.0-or-later
"""Beträge einlesen, kaufmännisch runden und als Text ausgeben.

Grundlage: CLAUDE.md (Abschnitt Geld) und Fachkonzept Kapitel 5.1.

- Beträge sind ausschließlich ``decimal.Decimal``. Fließkommazahlen werden abgelehnt,
  weil sie Dezimalbeträge wie 0,10 € nicht exakt darstellen können.
- Gerundet wird nur hier, kaufmännisch auf Cent.
- In JSON stehen Beträge als Text in Festkommaschreibweise.
- Gespeichert wird als ``NUMERIC(19,4)``. Was diese Spalte nicht exakt aufnimmt, lehnt
  ``speicherbar()`` ab, statt es der Datenbank zum stillen Runden zu überlassen.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

# NUMERIC(19,4): vier Nachkommastellen, also höchstens 15 Stellen vor dem Komma.
SPEICHER_EINHEIT = Decimal("0.0001")
SPEICHER_GRENZE = Decimal("1E15")

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


def speicherbar(wert: object) -> Decimal:
    """Betrag, den eine Spalte ``NUMERIC(19,4)`` exakt aufnimmt; nichts wird gerundet.

    PostgreSQL rundet zusätzliche Nachkommastellen beim Speichern still, und kein Trigger
    sieht den ursprünglichen Wert. Deshalb prüft die Anwendung vorher. Geprüft wird
    wertbezogen: ``1.00000`` ist zulässig, ``1.00005`` nicht. Die Meldungen nennen den
    Betrag nicht, weil sie in Logs landen können.

    Raises:
        TypeError: wie ``betrag()``.
        ValueError: wie ``betrag()``; außerdem bei Beträgen ab 10^15 und bei mehr als vier
            Nachkommastellen.
    """
    ergebnis = betrag(wert)
    # Erst die Größe prüfen: Der Rest unten bleibt so im Rahmen der Decimal-Genauigkeit.
    if abs(ergebnis) >= SPEICHER_GRENZE:
        msg = "Betrag ist für NUMERIC(19,4) zu groß (höchstens 15 Stellen vor dem Komma)."
        raise ValueError(msg)
    if ergebnis % SPEICHER_EINHEIT != 0:
        msg = "Betrag hat mehr als vier Nachkommastellen; NUMERIC(19,4) würde ihn runden."
        raise ValueError(msg)
    return ergebnis


def _pruefe_endlich(wert: Decimal) -> None:
    if not wert.is_finite():
        msg = f"Betrag muss endlich sein, nicht {wert}."
        raise ValueError(msg)
