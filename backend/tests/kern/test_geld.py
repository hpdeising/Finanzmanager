# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests für kern/geld: Beträge einlesen, kaufmännisch runden, als Text ausgeben.

Grundlage: CLAUDE.md (Abschnitt Geld) und Fachkonzept Kapitel 5.1.
"""

from decimal import Decimal

import pytest

from app.kern.geld import als_text, betrag, runde_auf_cent

# --- betrag(): Beträge nur aus Text, ganzen Zahlen oder Decimal ----------------


@pytest.mark.parametrize(
    ("eingabe", "erwartet"),
    [
        ("125.30", Decimal("125.30")),
        ("-0.01", Decimal("-0.01")),
        ("0", Decimal(0)),
        ("1234567.8912", Decimal("1234567.8912")),
        (5, Decimal(5)),
        (-7, Decimal(-7)),
        (Decimal("19.99"), Decimal("19.99")),
    ],
)
def test_betrag_akzeptiert_text_ganzzahl_und_decimal(eingabe: object, erwartet: Decimal) -> None:
    ergebnis = betrag(eingabe)
    assert isinstance(ergebnis, Decimal)
    assert ergebnis == erwartet


@pytest.mark.parametrize("eingabe", [1.5, 0.1, True, None, [1], b"1.5"])
def test_betrag_lehnt_andere_typen_ab(eingabe: object) -> None:
    """Insbesondere float: 0.1 ist als Fließkommazahl nicht exakt darstellbar."""
    with pytest.raises(TypeError, match="Betrag"):
        betrag(eingabe)


@pytest.mark.parametrize(
    "eingabe",
    ["", " 1.50", "1.50 ", "1,50", "1.", ".5", "+1.50", "1e5", "1_000", "NaN", "Infinity", "abc"],
)
def test_betrag_lehnt_nicht_kanonischen_text_ab(eingabe: str) -> None:
    """Kanonisch ist nur ``-?Ziffern(.Ziffern)?``.

    Die deutsche Schreibweise mit Komma übersetzt die Oberfläche, nicht der Kern.
    """
    with pytest.raises(ValueError, match="Betrag"):
        betrag(eingabe)


@pytest.mark.parametrize("eingabe", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_betrag_lehnt_nicht_endliche_decimal_ab(eingabe: Decimal) -> None:
    with pytest.raises(ValueError, match="Betrag"):
        betrag(eingabe)


# --- runde_auf_cent(): kaufmännisch, symmetrisch um null -----------------------


@pytest.mark.parametrize(
    ("eingabe", "erwartet"),
    [
        ("0.005", "0.01"),
        ("0.004", "0.00"),
        ("0.0049999", "0.00"),
        ("1.005", "1.01"),
        ("2.675", "2.68"),
        ("-0.005", "-0.01"),
        ("-0.004", "0.00"),
        ("-2.675", "-2.68"),
        ("10", "10.00"),
        ("19.999", "20.00"),
        ("1234567.8950", "1234567.90"),
    ],
)
def test_runde_auf_cent_kaufmaennisch(eingabe: str, erwartet: str) -> None:
    """Ab der halben Einheit wird betragsmäßig aufgerundet (ROUND_HALF_UP).

    ``2.675`` ergibt ``2.68``; mit float käme ``2.67`` heraus.
    """
    ergebnis = runde_auf_cent(Decimal(eingabe))
    assert ergebnis == Decimal(erwartet)
    assert ergebnis.as_tuple().exponent == -2


def test_negative_null_wird_zu_null() -> None:
    """``-0.004`` gerundet darf nicht als ``-0.00`` erscheinen."""
    assert not runde_auf_cent(Decimal("-0.004")).is_signed()


# --- als_text(): Festkomma für JSON ---------------------------------------------


@pytest.mark.parametrize(
    ("eingabe", "erwartet"),
    [
        (Decimal("125.3"), "125.30"),
        (Decimal("125.30"), "125.30"),
        (Decimal(5), "5.00"),
        (Decimal("1E+2"), "100.00"),
        (Decimal("-0.01"), "-0.01"),
        (Decimal("0.0125"), "0.0125"),
        (Decimal("1.2000"), "1.2000"),
    ],
)
def test_als_text_festkomma_mit_mindestens_zwei_nachkommastellen(
    eingabe: Decimal, erwartet: str
) -> None:
    """Nie Exponentschreibweise; mindestens zwei Nachkommastellen; nichts wird gerundet."""
    assert als_text(eingabe) == erwartet


def test_als_text_lehnt_nicht_endliche_werte_ab() -> None:
    with pytest.raises(ValueError, match="Betrag"):
        als_text(Decimal("NaN"))
