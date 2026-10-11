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
SPEICHER_NACHKOMMASTELLEN = 4
SPEICHER_GRENZE = Decimal("1E15")
# PostgreSQL liest für numeric höchstens 16383 Stellen nach dem Komma, auch wenn es nur Nullen
# sind (PostgreSQL-Doku, Kapitel 8.1, Tabelle 8.2); darüber hinaus 22003.
NUMERIC_STELLEN_NACH_KOMMA = 16383

# Kanonische Textform: optionales Minus, Ziffern, optional Punkt und Ziffern. Nur ASCII-Ziffern;
# \d passte auch auf andere Schriften, und Decimal() läse sie.
_KANONISCH = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")


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
    wertbezogen: ``1.00000`` ist zulässig, ``1.00005`` nicht.

    Geprüft wird ohne Decimal-Kontext: ``copy_abs()``, Vergleiche und ``as_tuple()`` sind
    exakt, ``abs()`` und ``%`` dagegen runden auf die Genauigkeit des Kontexts und laufen bei
    extremen Exponenten über oder unter.

    Die Meldungen nennen den Betrag nicht, auch nicht in einer verketteten Ausnahme, weil
    sie in Logs landen können.

    Raises:
        TypeError: wie ``betrag()``.
        ValueError: bei ungültigem Text oder nicht endlichen Werten, bei Beträgen ab 10^15,
            bei mehr als vier Nachkommastellen und bei mehr als 16383 Stellen nach dem Komma,
            auch wenn es Nullen sind.
    """
    try:
        ergebnis = betrag(wert)
    except ValueError:
        msg = "Betrag muss eine endliche Zahl in der Form '-123.45' sein."
        raise ValueError(msg) from None
    if ergebnis.copy_abs() >= SPEICHER_GRENZE:
        msg = "Betrag ist für NUMERIC(19,4) zu groß (höchstens 15 Stellen vor dem Komma)."
        raise ValueError(msg)
    # Danach hat der Wert höchstens 15 + 16383 Ziffern; das begrenzt auch die Prüfung unten.
    exponent = ergebnis.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -NUMERIC_STELLEN_NACH_KOMMA:
        msg = "Betrag hat mehr Nachkommastellen, als PostgreSQL liest (16383, auch Nullen)."
        raise ValueError(msg)
    if _nachkommastellen(ergebnis) > SPEICHER_NACHKOMMASTELLEN:
        msg = "Betrag hat mehr als vier Nachkommastellen; NUMERIC(19,4) würde ihn runden."
        raise ValueError(msg)
    return ergebnis


def _nachkommastellen(wert: Decimal) -> int:
    """Zahl der Nachkommastellen ohne abschließende Nullen: ``1.2300`` hat zwei, ``0E-9`` keine."""
    _, ziffern, exponent = wert.as_tuple()
    if not isinstance(exponent, int):  # nur bei nicht endlichen Werten, die betrag() ablehnt
        msg = "Betrag muss endlich sein."
        raise ValueError(msg)
    signifikant = len(ziffern)
    while signifikant and ziffern[signifikant - 1] == 0:
        signifikant -= 1
    if not signifikant:
        return 0
    return max(0, -(exponent + len(ziffern) - signifikant))


def _pruefe_endlich(wert: Decimal) -> None:
    if not wert.is_finite():
        msg = f"Betrag muss endlich sein, nicht {wert}."
        raise ValueError(msg)
