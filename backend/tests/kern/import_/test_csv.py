# SPDX-License-Identifier: AGPL-3.0-or-later
"""CSV-Import mit Profilen je Bank (Fachkonzept Kap. 8). Alle Daten sind erfunden."""

from datetime import date
from decimal import Decimal

import pytest

from app.kern.import_ import (
    CsvProfil,
    ImportUngueltigError,
    Richtung,
    Umsatz,
    lies_csv,
)

PROFIL = CsvProfil(
    name="Beispielbank",
    spalte_buchungstag="Buchungstag",
    spalte_valuta="Valuta",
    spalte_betrag="Betrag",
    spalte_gegen_name="Empfänger",
    spalte_gegen_iban="IBAN",
    spalten_verwendungszweck=("Verwendungszweck",),
)

CSV = (
    "Buchungstag;Valuta;Empfänger;IBAN;Verwendungszweck;Betrag\n"
    "03.02.2025;04.02.2025;Muster Inkasso GmbH;DE02120300000000202051;AZ 4711 Rate 2;-150,00\n"
    "05.02.2025;05.02.2025;Arbeitgeber AG;DE02100500000054540402;Gehalt Februar;1.234,56\n"
)


def test_liest_belastungen_und_gutschriften() -> None:
    belastung, gutschrift = lies_csv(CSV.encode(), PROFIL)
    assert belastung == Umsatz(
        buchungstag=date(2025, 2, 3),
        valuta=date(2025, 2, 4),
        betrag=Decimal("150.00"),
        richtung=Richtung.BELASTUNG,
        gegen_name="Muster Inkasso GmbH",
        gegen_iban="DE02120300000000202051",
        verwendungszweck="AZ 4711 Rate 2",
    )
    assert (gutschrift.betrag, gutschrift.richtung) == (Decimal("1234.56"), Richtung.GUTSCHRIFT)
    assert belastung.ist_kandidat
    assert not gutschrift.ist_kandidat


def test_kodierung_kopfzeilen_und_mehrere_verwendungszweckspalten() -> None:
    profil = CsvProfil(
        name="Altbank",
        trennzeichen=",",
        kodierung="cp1252",
        datumsformat="%Y-%m-%d",
        dezimaltrennzeichen=".",
        tausendertrennzeichen=None,
        kopfzeilen_ueberspringen=2,
        spalte_buchungstag="Datum",
        spalte_betrag="Betrag",
        spalten_verwendungszweck=("Zweck 1", "Zweck 2"),
    )
    daten = (
        "Kontoauszug Beispiel\n"
        "Zeitraum: Februar\n"
        "Datum,Betrag,Zweck 1,Zweck 2\n"
        "2025-02-03,-12.5,Gebühr,Mahnstufe ä\n"
    ).encode("cp1252")
    (umsatz,) = lies_csv(daten, profil)
    assert umsatz.verwendungszweck == "Gebühr Mahnstufe ä"
    assert (umsatz.betrag, umsatz.valuta, umsatz.gegen_iban) == (Decimal("12.5"), None, None)


def test_byte_order_mark_und_leere_zeilen() -> None:
    daten = "﻿" + CSV + "\n;;;;;\n"
    assert len(lies_csv(daten.encode(), PROFIL)) == 2


def test_iban_ohne_leerzeichen_in_grossbuchstaben() -> None:
    daten = CSV.replace("DE02120300000000202051", "de02 1203 0000 0000 2020 51")
    assert lies_csv(daten.encode(), PROFIL)[0].gegen_iban == "DE02120300000000202051"


@pytest.mark.parametrize(
    ("ersetzen", "durch", "meldung"),
    [
        ("03.02.2025", "2025-02-03", "Zeile 2: Buchungstag"),
        ("-150,00", "-150,0,0", "Zeile 2: Betrag"),
        ("-150,00", "0,00", "Zeile 2: Betrag"),
        ("Betrag\n", "Summe\n", "Spalte fehlt: Betrag"),
    ],
)
def test_fehler_nennen_zeile_und_spalte_aber_keine_werte(
    ersetzen: str, durch: str, meldung: str
) -> None:
    """Logs und Meldungen enthalten keine personenbezogenen Daten (CLAUDE.md)."""
    with pytest.raises(ImportUngueltigError, match=meldung) as fehler:
        lies_csv(CSV.replace(ersetzen, durch, 1).encode(), PROFIL)
    assert durch not in str(fehler.value)
    assert "Muster" not in str(fehler.value)


def test_falsche_kodierung() -> None:
    with pytest.raises(ImportUngueltigError, match="Kodierung"):
        lies_csv("Empfänger".encode("cp1252"), PROFIL)


def test_profil_braucht_verwendungszweck() -> None:
    with pytest.raises(ValueError, match="Verwendungszweck"):
        CsvProfil(name="x", spalte_buchungstag="a", spalte_betrag="b", spalten_verwendungszweck=())
