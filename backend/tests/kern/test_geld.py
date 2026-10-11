# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests für kern/geld: Beträge einlesen, kaufmännisch runden, als Text ausgeben.

Grundlage: CLAUDE.md (Abschnitt Geld) und Fachkonzept Kapitel 5.1.
"""

from decimal import Decimal

import pytest

from app.kern.geld import als_text, betrag, runde_auf_cent, speicherbar

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


# --- speicherbar(): Beträge, die NUMERIC(19,4) exakt aufnimmt --------------------


@pytest.mark.parametrize(
    "eingabe",
    [
        "0.0001",
        "-0.0001",
        "999999999999999.9999",
        "-999999999999999.9999",
        "1.00000",
        Decimal("1E+2"),
        Decimal("-0"),
        Decimal("0E+20"),
        7,
    ],
)
def test_speicherbar_gibt_den_wert_unveraendert_zurueck(eingabe: object) -> None:
    """Wertbezogen: ``1.00000`` hat fünf Stellen, aber keine fünfte Nachkommastelle ≠ 0."""
    ergebnis = speicherbar(eingabe)
    assert isinstance(ergebnis, Decimal)
    assert ergebnis == betrag(eingabe)


@pytest.mark.parametrize(
    "eingabe",
    [
        "1.00005",
        "-1.00005",
        "0.00001",
        Decimal("1E-30"),
        "999999999999999.99995",
    ],
)
def test_speicherbar_lehnt_mehr_als_vier_nachkommastellen_ab(eingabe: object) -> None:
    """NUMERIC(19,4) würde still runden; ``1.00005`` würde zu ``1.0001``."""
    with pytest.raises(ValueError, match="Nachkommastellen"):
        speicherbar(eingabe)


@pytest.mark.parametrize(
    "eingabe",
    ["1000000000000000", "-1000000000000000", Decimal("1E+15"), Decimal("1E+30")],
)
def test_speicherbar_lehnt_zu_grosse_betraege_ab(eingabe: object) -> None:
    """Höchstens 15 Stellen vor dem Komma; ``1E+30`` ergibt ValueError, nicht InvalidOperation."""
    with pytest.raises(ValueError, match="zu groß"):
        speicherbar(eingabe)


@pytest.mark.parametrize("eingabe", [1.5, True, None])
def test_speicherbar_lehnt_andere_typen_ab(eingabe: object) -> None:
    with pytest.raises(TypeError, match="Betrag"):
        speicherbar(eingabe)


# Sehr große und sehr kleine Exponenten: abs() und % rechnen im Decimal-Kontext (28 Stellen,
# Emax 999999) und liefen über oder unter. speicherbar() muss exakt prüfen.
RIESIG = "1" + "0" * 1_000_000
WINZIG = "0." + "0" * 1_000_029 + "1"
FAST_FUENF = "5." + "0" * 1_000_029 + "1"


@pytest.mark.parametrize(
    "eingabe",
    [Decimal("1E+1000000"), Decimal("-1E+1000000"), RIESIG],
    ids=["exponent", "exponent-negativ", "festkomma"],
)
def test_speicherbar_lehnt_riesige_betraege_ohne_ueberlauf_ab(eingabe: object) -> None:
    """``decimal.Overflow`` ist kein ValueError und liefe an jeder Fehlerbehandlung vorbei."""
    with pytest.raises(ValueError, match="zu groß"):
        speicherbar(eingabe)


@pytest.mark.parametrize(
    "eingabe",
    [Decimal("1E-1000030"), WINZIG, FAST_FUENF, Decimal("999999999999999.99999999999999")],
    ids=["exponent", "festkomma", "fuenf-und-winzig", "knapp-unter-grenze"],
)
def test_speicherbar_lehnt_winzige_nachkommastellen_ohne_unterlauf_ab(eingabe: object) -> None:
    """Der Rest von ``%`` liefe auf null unter; ``abs()`` rundete auf 28 Stellen auf 10^15."""
    with pytest.raises(ValueError, match="Nachkommastellen"):
        speicherbar(eingabe)


@pytest.mark.parametrize(
    "eingabe",
    [Decimal("0E-1000030"), Decimal("1." + "0" * 40), Decimal("123.4500000000000000000000000000")],
    ids=["null-mit-kleinem-exponenten", "viele-nullen", "nullen-ueber-28-stellen"],
)
def test_speicherbar_wertet_abschliessende_nullen_nicht_als_nachkommastellen(
    eingabe: Decimal,
) -> None:
    assert speicherbar(eingabe) is eingabe


def meldungen(fehler: BaseException) -> str:
    """Alle Meldungen, die ein Traceback zeigen würde: der Fehler und seine Ursachen."""
    texte: list[str] = []
    aktuell: BaseException | None = fehler
    while aktuell is not None:
        texte.append(str(aktuell))
        aktuell = aktuell.__cause__ or (
            None if aktuell.__suppress_context__ else aktuell.__context__
        )
    return "\n".join(texte)


@pytest.mark.parametrize(
    "eingabe",
    ["4711.00005", "4711000000000000", "4711,08", "1.234,56", "4711.08 ", "+4711.08", "47.11\n"],
)
def test_speicherbar_nennt_den_betrag_nicht_in_der_meldung(eingabe: str) -> None:
    """Meldungen landen in Logs; Beträge mit Personenbezug gehören dort nicht hin (CLAUDE.md).

    Das gilt auch für nicht kanonischen Text und für verkettete Ausnahmen.
    """
    with pytest.raises(ValueError, match="Betrag") as fehler:
        speicherbar(eingabe)
    text = meldungen(fehler.value)
    assert "4711" not in text
    assert "234" not in text
    assert "47.11" not in text
