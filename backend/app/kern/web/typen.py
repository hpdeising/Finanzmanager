# SPDX-License-Identifier: AGPL-3.0-or-later
"""Typen für die JSON-Schnittstelle: Beträge und Dezimalzahlen nur als Text (CLAUDE.md, Geld).

Eine JSON-Zahl wird abgelehnt, auch eine ganze: Zwischen Client und Server soll kein
Fließkommawert entstehen können. ``Decimal`` gibt es nur aus der Anwendung selbst, etwa beim
Aufbau einer Antwort; JSON kennt den Typ nicht.

Ausgegeben werden Beträge als Festkomma-Text mit mindestens zwei Nachkommastellen
(``als_text``); überzählige Nullen aus ``NUMERIC(19,4)`` fallen weg (``ohne_nullen``).
Gerundet wird nichts.
"""

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema

from app.kern.geld import als_text, betrag, ohne_nullen


def _betrag(wert: Any) -> Decimal:
    if isinstance(wert, Decimal):  # aus der Anwendung selbst, nie aus JSON
        return wert
    if not isinstance(wert, str):
        msg = 'Beträge stehen als Text, z. B. "125.30".'
        raise ValueError(msg)
    try:
        return betrag(wert)
    except (TypeError, ValueError, InvalidOperation) as fehler:
        msg = 'Kein gültiger Betrag; erwartet wird Text wie "125.30".'
        raise ValueError(msg) from fehler


def _text(wert: Decimal) -> str:
    return als_text(ohne_nullen(wert))


def _dezimal_text(wert: Decimal) -> str:
    return format(ohne_nullen(wert), "f")


_SCHEMA = {"type": "string", "pattern": r"^-?\d+(\.\d+)?$", "examples": ["125.30"]}

Betragstext = Annotated[
    Decimal,
    BeforeValidator(_betrag),
    PlainSerializer(_text, return_type=str),
    WithJsonSchema(_SCHEMA),
]
"""Betrag in Euro als Text, z. B. ``"125.30"``."""

Dezimaltext = Annotated[
    Decimal,
    BeforeValidator(_betrag),
    PlainSerializer(_dezimal_text, return_type=str),
    WithJsonSchema(_SCHEMA),
]
"""Dezimalzahl als Text, z. B. ein Zinssatz ``"5.0"``; ausgegeben ohne Festkomma-Auffüllung."""
