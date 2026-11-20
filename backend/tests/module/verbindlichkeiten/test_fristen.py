# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests der Fristberechnung und des Fristenkatalogs (Fachkonzept Kap. 5.4).

Der Feiertagskalender ist ausgedacht (ein Testtag am Montag, 24.03.2025, nur in SH).
"""

from datetime import date

import pytest

from app.kern.stammdaten import Feiertagskalender, StammdatenFehlenError
from app.module.verbindlichkeiten.domain import Ereignis, Ereignistyp
from app.module.verbindlichkeiten.fristen import (
    Dauer,
    Einheit,
    Fristart,
    fristen_aus_ereignissen,
    fristende,
    warnstufen,
)

T = date
KALENDER = Feiertagskalender.aus_daten(
    {
        "quelle": "Ausgedachter Testkalender",
        "geprueft_von": "Test",
        "gueltig_ab": T(2025, 1, 1),
        "gueltig_bis": T(2028, 12, 31),
        "feiertage": [{"datum": T(2025, 3, 24), "name": "Testtag", "laender": ["SH"]}],
    }
)


# --- §§ 187, 188 BGB -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ereignis", "dauer", "ende"),
    [
        # § 187 Abs. 1, § 188 Abs. 1: Der Tag des Ereignisses zählt nicht mit.
        (T(2025, 3, 5), Dauer(10, Einheit.TAGE), T(2025, 3, 15)),
        # § 188 Abs. 2: Wochenfrist endet am gleichnamigen Wochentag (Mittwoch).
        (T(2025, 3, 5), Dauer(2, Einheit.WOCHEN), T(2025, 3, 19)),
        # § 188 Abs. 2: Monatsfrist endet am Tag mit derselben Zahl.
        (T(2025, 3, 15), Dauer(1, Einheit.MONATE), T(2025, 4, 15)),
        # § 188 Abs. 3: Fehlt dieser Tag, endet sie am letzten Tag des Monats.
        (T(2025, 1, 31), Dauer(1, Einheit.MONATE), T(2025, 2, 28)),
        (T(2024, 1, 30), Dauer(1, Einheit.MONATE), T(2024, 2, 29)),
        (T(2025, 6, 10), Dauer(3, Einheit.JAHRE), T(2028, 6, 10)),
        (T(2024, 2, 29), Dauer(3, Einheit.JAHRE), T(2027, 2, 28)),
    ],
)
def test_fristende_nach_187_188_bgb(ereignis: date, dauer: Dauer, ende: date) -> None:
    assert fristende(ereignis, dauer, Fristart.INFORMATION) == ende


# --- § 222 Abs. 2 ZPO --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("land", "ende"),
    [
        ("BY", T(2025, 3, 24)),  # Sa 22.03. -> Mo 24.03.
        ("SH", T(2025, 3, 25)),  # Mo 24.03. ist dort Feiertag -> Di 25.03.
    ],
)
def test_prozessuale_frist_endet_am_naechsten_werktag(land: str, ende: date) -> None:
    """Endet die Frist an einem Samstag, Sonntag oder Feiertag, endet sie mit Ablauf des
    nächsten Werktags; Feiertage nach dem Land (Kap. 5.4)."""
    assert (
        fristende(T(2025, 3, 8), Dauer(2, Einheit.WOCHEN), Fristart.PROZESSUAL, KALENDER, land)
        == ende
    )


def test_prozessuale_frist_an_einem_werktag_bleibt() -> None:
    assert fristende(
        T(2025, 3, 5), Dauer(2, Einheit.WOCHEN), Fristart.PROZESSUAL, KALENDER, "BY"
    ) == T(2025, 3, 19)


@pytest.mark.parametrize("art", [Fristart.NOTFRIST, Fristart.INFORMATION, Fristart.MATERIELL])
def test_222_zpo_nur_fuer_prozessuale_fristen_wie_im_fachkonzept(art: Fristart) -> None:
    """Kap. 5.4 nennt § 222 Abs. 2 ZPO für prozessuale Fristen (offene Frage zu Notfristen)."""
    assert fristende(T(2025, 3, 8), Dauer(2, Einheit.WOCHEN), art) == T(2025, 3, 22)


def test_prozessuale_frist_braucht_kalender_und_land() -> None:
    with pytest.raises(ValueError, match="Feiertagskalender"):
        fristende(T(2025, 3, 5), Dauer(2, Einheit.WOCHEN), Fristart.PROZESSUAL)


def test_feiertage_ausserhalb_des_kalenders_werden_nicht_geschaetzt() -> None:
    with pytest.raises(StammdatenFehlenError):
        fristende(T(2028, 12, 20), Dauer(2, Einheit.WOCHEN), Fristart.PROZESSUAL, KALENDER, "BY")


# --- Warnstufen ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("art", "erwartet"),
    [
        (Fristart.NOTFRIST, (T(2025, 3, 12), T(2025, 3, 16), T(2025, 3, 18))),
        (Fristart.PROZESSUAL, (T(2025, 3, 12), T(2025, 3, 16))),
        (Fristart.INFORMATION, (T(2025, 2, 17),)),
        (Fristart.MATERIELL, ()),
    ],
)
def test_warnstufen(art: Fristart, erwartet: tuple[date, ...]) -> None:
    """Notfristen 7, 3 und 1 Tag vor Ablauf, prozessuale 7 und 3, Informationen 30 (Kap. 5.4)."""
    assert warnstufen(T(2025, 3, 19), art) == erwartet


# --- Fristenkatalog ------------------------------------------------------------------------------


def _fristen(
    *ereignisse: Ereignis, land: str = "BY"
) -> list[tuple[str, date | None, Fristart, str]]:
    fristen, _ = fristen_aus_ereignissen(ereignisse, KALENDER, land)
    return [(f.name, f.ende, f.art, f.norm) for f in fristen]


def test_widerspruch_gegen_mahnbescheid() -> None:
    fristen, warnungen = fristen_aus_ereignissen(
        [Ereignis(Ereignistyp.ZUSTELLUNG_MAHNBESCHEID, T(2025, 3, 5))], KALENDER, "BY"
    )
    (frist,) = fristen
    assert (frist.name, frist.ende, frist.art, frist.norm) == (
        "Widerspruch gegen Mahnbescheid",
        T(2025, 3, 19),
        Fristart.PROZESSUAL,
        "§ 692 Abs. 1 Nr. 3, § 694 Abs. 1 ZPO",
    )
    assert frist.hinweis is not None
    assert "Vollstreckungsbescheid" in frist.hinweis
    assert frist.warnstufen == (T(2025, 3, 12), T(2025, 3, 16))
    assert warnungen == []


def test_einspruch_gegen_vollstreckungsbescheid() -> None:
    assert _fristen(Ereignis(Ereignistyp.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID, T(2025, 3, 5))) == [
        (
            "Einspruch gegen Vollstreckungsbescheid",
            T(2025, 3, 19),
            Fristart.NOTFRIST,
            "§ 700 Abs. 1, § 339 Abs. 1 ZPO",
        )
    ]


def test_einspruch_gegen_versaeumnisurteil() -> None:
    ereignis = Ereignis(Ereignistyp.ZUSTELLUNG_URTEIL, T(2025, 3, 5), versaeumnisurteil=True)
    assert _fristen(ereignis) == [
        ("Einspruch gegen Versäumnisurteil", T(2025, 3, 19), Fristart.NOTFRIST, "§ 339 Abs. 1 ZPO")
    ]


def test_berufung_mit_hinweis_auf_die_voraussetzungen() -> None:
    fristen, _ = fristen_aus_ereignissen(
        [Ereignis(Ereignistyp.ZUSTELLUNG_URTEIL, T(2025, 3, 5))], KALENDER, "BY"
    )
    (frist,) = fristen
    assert (frist.name, frist.ende, frist.art, frist.norm) == (
        "Berufung",
        T(2025, 4, 5),
        Fristart.NOTFRIST,
        "§§ 511, 517 ZPO",
    )
    assert frist.hinweis is not None
    assert "600" in frist.hinweis


def test_eintragungsanordnung_mit_bekanntgabe() -> None:
    ereignis = Ereignis(
        Ereignistyp.EINTRAGUNGSANORDNUNG, T(2025, 3, 5), bekanntgabe_am=T(2025, 3, 10)
    )
    assert _fristen(ereignis) == [
        (
            "Widerspruch gegen Eintragungsanordnung",
            T(2025, 3, 24),
            Fristart.PROZESSUAL,
            "§ 882d Abs. 1 ZPO",
        ),
        (
            "Löschung im Schuldnerverzeichnis",
            T(2028, 3, 5),
            Fristart.INFORMATION,
            "§ 882e Abs. 1 ZPO",
        ),
    ]


def test_eintragungsanordnung_ohne_bekanntgabe_warnt() -> None:
    fristen, warnungen = fristen_aus_ereignissen(
        [Ereignis(Ereignistyp.EINTRAGUNGSANORDNUNG, T(2025, 3, 5))], KALENDER, "BY"
    )
    assert [f.name for f in fristen] == ["Löschung im Schuldnerverzeichnis"]
    (warnung,) = warnungen
    assert "Bekanntgabe" in warnung.text


@pytest.mark.parametrize(
    "typ",
    [
        Ereignistyp.ZUSTELLUNG_MAHNBESCHEID,
        Ereignistyp.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID,
        Ereignistyp.ZUSTELLUNG_URTEIL,
    ],
)
def test_zustellung_ohne_datum_warnt_sofort(typ: Ereignistyp) -> None:
    """Kap. 5.4: Ohne Zustellungsdatum gibt es keine Frist; das System warnt sofort."""
    fristen, warnungen = fristen_aus_ereignissen([Ereignis(typ, None)], KALENDER, "BY")
    assert fristen == []
    (warnung,) = warnungen
    assert "Zustellungsdatum" in warnung.text


def test_andere_ereignisse_haben_keine_frist_aus_kapitel_5_4() -> None:
    assert _fristen(Ereignis(Ereignistyp.ANERKENNTNIS, T(2025, 3, 5))) == []


def test_fristen_werden_aus_allen_ereignissen_abgeleitet() -> None:
    namen = [
        f[0]
        for f in _fristen(
            Ereignis(Ereignistyp.ZUSTELLUNG_MAHNBESCHEID, T(2025, 1, 6)),
            Ereignis(Ereignistyp.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID, T(2025, 2, 10)),
        )
    ]
    assert namen == ["Widerspruch gegen Mahnbescheid", "Einspruch gegen Vollstreckungsbescheid"]
