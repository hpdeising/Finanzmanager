# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vorabprüfung von Buchungen und Konten, ohne Datenbank.

Die Datenbank erzwingt dieselben Regeln (Fachkonzept 4.4); die Vorabprüfung liefert
verständliche Fehler, bevor etwas geschrieben wird.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.kern.ledger import (
    BuchungUngueltigError,
    Kontoart,
    KontoUngueltigError,
    PostingEingabe,
    pruefe_buchungsentwurf,
    pruefe_konto,
)

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
TAG = date(2024, 1, 15)


def postings(*paare: tuple[uuid.UUID, str]) -> list[PostingEingabe]:
    return [PostingEingabe(konto_id=konto, betrag=Decimal(betrag)) for konto, betrag in paare]


def test_gueltiger_entwurf() -> None:
    pruefe_buchungsentwurf("test.buchung", TAG, postings((A, "1000.00"), (B, "-1000.00")))


def test_mehrere_postings_auf_einem_konto_neben_anderen_konten_sind_erlaubt() -> None:
    pruefe_buchungsentwurf("test.buchung", TAG, postings((A, "5"), (A, "5"), (B, "-10")))


@pytest.mark.parametrize(
    "entwurf",
    [
        [],
        postings((A, "10.00")),
    ],
)
def test_mindestens_zwei_postings(entwurf: list[PostingEingabe]) -> None:
    with pytest.raises(BuchungUngueltigError, match="zwei Postings"):
        pruefe_buchungsentwurf("test.buchung", TAG, entwurf)


def test_mindestens_zwei_verschiedene_konten() -> None:
    """Eine Buchung ohne Bewegung zwischen Konten ist kein Geschäftsvorfall (Kap. 3)."""
    with pytest.raises(BuchungUngueltigError, match="zwei verschiedene Konten"):
        pruefe_buchungsentwurf("test.buchung", TAG, postings((A, "5"), (A, "-5")))


@pytest.mark.parametrize("null", ["0", "0.0000", "-0"])
def test_kein_posting_ueber_null(null: str) -> None:
    with pytest.raises(BuchungUngueltigError, match="Betrag null"):
        pruefe_buchungsentwurf("test.buchung", TAG, postings((A, null), (B, "0")))


def test_summe_muss_null_sein() -> None:
    with pytest.raises(BuchungUngueltigError, match="Summe"):
        pruefe_buchungsentwurf("test.buchung", TAG, postings((A, "10.0001"), (B, "-10.0000")))


@pytest.mark.parametrize(
    "entwurf",
    [
        postings((A, "1.00005"), (B, "-1.00005")),
        postings(
            (A, "999999999999999.9999"),
            (B, "999999999999999.9999"),
            (C, "-1999999999999999.9998"),
        ),
    ],
)
def test_betraege_muessen_speicherbar_sein(entwurf: list[PostingEingabe]) -> None:
    with pytest.raises(BuchungUngueltigError, match="Betrag"):
        pruefe_buchungsentwurf("test.buchung", TAG, entwurf)


@pytest.mark.parametrize(("soll", "haben"), [(1.5, -1.5), ("1.00", "-1.00"), (1, -1)])
def test_betraege_sind_decimal(soll: object, haben: object) -> None:
    """Beträge ausschließlich als Decimal (CLAUDE.md, Geld); Text und int übersetzt der Aufrufer."""
    entwurf = [PostingEingabe(A, soll), PostingEingabe(B, haben)]  # pyright: ignore[reportArgumentType]
    with pytest.raises(TypeError, match="Decimal"):
        pruefe_buchungsentwurf("test.buchung", TAG, entwurf)


@pytest.mark.parametrize("wertstellung", [datetime(2024, 1, 15, 12, 0), "2024-01-15"])  # noqa: DTZ001
def test_wertstellung_ist_ein_datum(wertstellung: object) -> None:
    """Fachliche Daten sind ``date``; ``datetime`` ist zwar eine Unterklasse, aber kein Datum."""
    with pytest.raises(TypeError, match="Wertstellung"):
        pruefe_buchungsentwurf(
            "test.buchung",
            wertstellung,  # pyright: ignore[reportArgumentType]
            postings((A, "1"), (B, "-1")),
        )


@pytest.mark.parametrize(
    "art", ["zahlung", "Kern.storno", "kern.", ".x", "a.b.c", "kern.zahl-ung", "kern.x\n", "x.ä"]
)
def test_art_folgt_dem_schema_modul_punkt_name(art: str) -> None:
    with pytest.raises(BuchungUngueltigError, match="Art"):
        pruefe_buchungsentwurf(art, TAG, postings((A, "1"), (B, "-1")))


def test_storno_nur_ueber_storniere() -> None:
    with pytest.raises(BuchungUngueltigError, match="storniere"):
        pruefe_buchungsentwurf("kern.storno", TAG, postings((A, "1"), (B, "-1")))


@pytest.mark.parametrize("art", ["kern.zahlung", "kern.externe_mittel"])
def test_kern_kennt_nur_die_art_storno(art: str) -> None:
    """E-17: Der Kern kennt nur ``kern.storno``; alle anderen Arten meldet ein Modul an."""
    with pytest.raises(BuchungUngueltigError, match="kern"):
        pruefe_buchungsentwurf(art, TAG, postings((A, "1"), (B, "-1")))


@pytest.mark.parametrize(
    ("entwurf", "verboten"),
    [
        (postings((A, "4711.0815"), (B, "-4711.08")), ["4711", "0.0015", "15"]),
        (postings((A, "4711.00005"), (B, "-4711.00005")), ["4711", "00005"]),
        (postings((A, "4711000000000000"), (B, "-4711000000000000")), ["4711"]),
        (postings((A, "0"), (B, "4711")), ["4711"]),
    ],
    ids=["summe", "nachkommastellen", "zu-gross", "null"],
)
def test_meldungen_nennen_keine_betraege(
    entwurf: list[PostingEingabe], verboten: list[str]
) -> None:
    """Fehlermeldungen können in Logs landen (CLAUDE.md, Sicherheit); auch keine Summen."""
    with pytest.raises(BuchungUngueltigError) as fehler:
        pruefe_buchungsentwurf("test.buchung", TAG, entwurf)
    for teil in verboten:
        assert teil not in str(fehler.value)
        assert teil not in str(fehler.value.__cause__ or "")


@pytest.mark.parametrize(
    ("kontoart", "rolle"),
    [
        ("passiv", "verbindlichkeiten.hauptforderung"),
        ("aufwand", "verbindlichkeiten.zinsaufwand"),
        ("passiv", "test.konto"),
        ("eigenkapital", "kern.externe_mittel"),
    ],
)
def test_gueltige_rollen(kontoart: Kontoart, rolle: str) -> None:
    pruefe_konto(kontoart, rolle)


@pytest.mark.parametrize("kontoart", ["aktiv", "passiv", "aufwand", "ertrag"])
def test_externe_mittel_sind_eigenkapital(kontoart: Kontoart) -> None:
    """Kap. 4.2: Das Konto „Externe Mittel“ hat die Kontoart Eigenkapital."""
    with pytest.raises(KontoUngueltigError, match="Eigenkapital"):
        pruefe_konto(kontoart, "kern.externe_mittel")


@pytest.mark.parametrize("rolle", ["kern.bankkonto", "kern.storno"])
def test_kern_kennt_nur_die_rolle_externe_mittel(rolle: str) -> None:
    """E-17: Von den Rollen kennt der Kern nur ``kern.externe_mittel``."""
    with pytest.raises(KontoUngueltigError, match="kern"):
        pruefe_konto("eigenkapital", rolle)


@pytest.mark.parametrize(
    "rolle",
    ["hauptforderung", "Kern.x", "kern.", ".x", "a.b.c", "kern.externe-mittel", "kern.gläubiger"],
)
def test_ungueltige_rollen(rolle: str) -> None:
    with pytest.raises(KontoUngueltigError, match="Rolle"):
        pruefe_konto("passiv", rolle)


@pytest.mark.parametrize("kontoart", ["Passiv", "bank", ""])
def test_kontoart_ist_eine_der_fuenf_grundarten(kontoart: str) -> None:
    with pytest.raises(KontoUngueltigError, match="Kontoart"):
        pruefe_konto(kontoart, "test.konto")  # pyright: ignore[reportArgumentType]
