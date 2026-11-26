# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wertstellung (P-16) und Erkennung von Duplikaten (Fachkonzept Kap. 8)."""

from datetime import date
from decimal import Decimal

import pytest

from app.kern.import_ import (
    ImportUngueltigError,
    Richtung,
    Umsatz,
    WertstellungAus,
    duplikat_schluessel,
    wertstellung,
)

UMSATZ = Umsatz(
    buchungstag=date(2025, 2, 3),
    valuta=date(2025, 2, 4),
    betrag=Decimal("150.00"),
    richtung=Richtung.BELASTUNG,
    gegen_name="Muster Inkasso GmbH",
    gegen_iban="DE02120300000000202051",
    verwendungszweck="AZ 4711 Rate 2",
)


def test_p16_ist_eine_einstellung_ohne_voreinstellung() -> None:
    """P-16 ist offen: Die Wahl ist Pflicht, das Programm entscheidet nichts."""
    assert wertstellung(UMSATZ, WertstellungAus.BUCHUNGSTAG) == date(2025, 2, 3)
    assert wertstellung(UMSATZ, WertstellungAus.VALUTA) == date(2025, 2, 4)


def test_valuta_gewaehlt_aber_nicht_vorhanden() -> None:
    """Fehlt die Valuta, wird nicht geschätzt (CLAUDE.md)."""
    ohne = Umsatz(
        buchungstag=UMSATZ.buchungstag,
        valuta=None,
        betrag=UMSATZ.betrag,
        richtung=UMSATZ.richtung,
        gegen_name=None,
        gegen_iban=None,
        verwendungszweck="x",
    )
    with pytest.raises(ImportUngueltigError, match="Valuta"):
        wertstellung(ohne, WertstellungAus.VALUTA)


def test_duplikat_aus_datum_betrag_iban_und_zweck() -> None:
    schluessel = duplikat_schluessel(UMSATZ, date(2025, 2, 3))
    assert len(schluessel) == 64
    assert schluessel == duplikat_schluessel(UMSATZ, date(2025, 2, 3))
    assert schluessel != duplikat_schluessel(UMSATZ, date(2025, 2, 4))
    anderer_betrag = Umsatz(
        buchungstag=UMSATZ.buchungstag,
        valuta=UMSATZ.valuta,
        betrag=Decimal("150.01"),
        richtung=UMSATZ.richtung,
        gegen_name=UMSATZ.gegen_name,
        gegen_iban=UMSATZ.gegen_iban,
        verwendungszweck=UMSATZ.verwendungszweck,
    )
    assert schluessel != duplikat_schluessel(anderer_betrag, date(2025, 2, 3))


def test_duplikat_unabhaengig_von_schreibweise_und_namen() -> None:
    """Gleicher Betrag in anderer Schreibweise (150.0) und anderer Name: dieselbe Zahlung."""
    andere = Umsatz(
        buchungstag=UMSATZ.buchungstag,
        valuta=UMSATZ.valuta,
        betrag=Decimal("150.0"),
        richtung=UMSATZ.richtung,
        gegen_name="MUSTER INKASSO",
        gegen_iban=UMSATZ.gegen_iban,
        verwendungszweck="  AZ 4711   Rate 2 ",
    )
    tag = date(2025, 2, 3)
    assert duplikat_schluessel(andere, tag) == duplikat_schluessel(UMSATZ, tag)


def test_betrag_ist_positiv() -> None:
    with pytest.raises(ValueError, match="positiv"):
        Umsatz(
            buchungstag=date(2025, 2, 3),
            valuta=None,
            betrag=Decimal("-1.00"),
            richtung=Richtung.BELASTUNG,
            gegen_name=None,
            gegen_iban=None,
            verwendungszweck="",
        )
