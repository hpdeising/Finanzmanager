# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests des Statusmodells (Fachkonzept Kap. 6, Entscheidungen des Maintainers vom 20.11.2026).

Der Status wird aus Ereignissen und der Restschuld berechnet und nie gespeichert. Die Restschuld
kommt aus ``berechne``; die Bestandteile sind unverzinst, damit die Beträge glatt bleiben.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest

from app.kern.stammdaten import lade_basiszinsreihe
from app.module.verbindlichkeiten.berechnung import berechne
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Bestandteil,
    Bestandteilart,
    Ereignis,
    Ereignistyp,
    Zahlung,
)
from app.module.verbindlichkeiten.status import (
    HINWEIS_VOLLSTRECKUNG_TROTZ_ERFUELLUNG,
    Aufgabe,
    Aufgabentyp,
    Merkmal,
    Status,
    Statusergebnis,
    status_berechnen,
)

T = date
D = Decimal
E = Ereignistyp
REIHE = lade_basiszinsreihe()
STICHTAG = T(2026, 6, 30)
HF = Bestandteil("hauptforderung", Bestandteilart.HAUPTFORDERUNG, D("1000.00"))
AUSGLEICH = T(2026, 3, 2)  # Montag


def status(
    ereignisse: Sequence[Ereignis] = (),
    *,
    zahlungen: Sequence[Zahlung] = (),
    bestandteile: Sequence[Bestandteil] = (HF,),
    stichtag: date = STICHTAG,
) -> Statusergebnis:
    ergebnis = berechne(Aktenparameter(), bestandteile, zahlungen, stichtag, REIHE)
    return status_berechnen(ereignisse, stichtag, ergebnis)


def ausgeglichen(
    ereignisse: Sequence[Ereignis] = (), *, stichtag: date = STICHTAG
) -> Statusergebnis:
    return status(ereignisse, zahlungen=[Zahlung(AUSGLEICH, D("1000.00"))], stichtag=stichtag)


def aufgabe(ergebnis: Statusergebnis, typ: Aufgabentyp) -> Aufgabe:
    return next(a for a in ergebnis.aufgaben if a.typ is typ)


def alle_erledigt(tag: date) -> list[Ereignis]:
    return [
        Ereignis(E.QUITTUNG_ERHALTEN, tag),
        Ereignis(E.ERLEDIGT_GEMELDET_AUSKUNFTEI, tag),
    ]


# --- Lebenszyklus ---------------------------------------------------------------------------


def test_reihenfolge_der_status() -> None:
    assert list(Status) == [
        Status.OFFEN,
        Status.MAHNVERFAHREN,
        Status.TITULIERT,
        Status.NACHWIRKUNG,
        Status.AUSGEGLICHEN,
        Status.GESCHLOSSEN,
    ]


def test_ohne_ereignis_offen() -> None:
    ergebnis = status()
    assert ergebnis.status is Status.OFFEN
    assert ergebnis.merkmale == frozenset()
    assert ergebnis.aufgaben == ()
    assert ergebnis.ausgeglichen_am is None


def test_mahnbescheid_fuehrt_ins_mahnverfahren() -> None:
    ergebnis = status([Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2025, 1, 10))])
    assert ergebnis.status is Status.MAHNVERFAHREN


def test_vollstreckungsbescheid_nach_mahnverfahren_tituliert() -> None:
    ergebnis = status(
        [
            Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2025, 1, 10)),
            Ereignis(E.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID, T(2025, 3, 3)),
        ]
    )
    assert ergebnis.status is Status.TITULIERT


@pytest.mark.parametrize(
    "typ",
    [
        E.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID,
        E.ZUSTELLUNG_URTEIL,
        E.ERRICHTUNG_TITEL,
        E.ZUSTELLUNG_KOSTENFESTSETZUNGSBESCHLUSS,
    ],
)
def test_titel_ereignis_fuehrt_von_offen_nach_tituliert(typ: Ereignistyp) -> None:
    assert status([Ereignis(typ, T(2025, 3, 3))]).status is Status.TITULIERT


def test_mahnverfahren_ohne_titel_beendet_fuehrt_zurueck_nach_offen() -> None:
    """Entscheidung vom 21.11.2026."""
    ergebnis = status(
        [
            Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2025, 1, 10)),
            Ereignis(E.MAHNVERFAHREN_OHNE_TITEL_BEENDET, T(2025, 4, 1)),
        ]
    )
    assert ergebnis.status is Status.OFFEN


def test_neuer_mahnbescheid_nach_beendetem_mahnverfahren() -> None:
    ergebnis = status(
        [
            Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2025, 1, 10)),
            Ereignis(E.MAHNVERFAHREN_OHNE_TITEL_BEENDET, T(2025, 4, 1)),
            Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2025, 6, 2)),
        ]
    )
    assert ergebnis.status is Status.MAHNVERFAHREN


def test_beendetes_mahnverfahren_aendert_einen_titel_nicht() -> None:
    ergebnis = status(
        [
            Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2025, 1, 10)),
            Ereignis(E.MAHNVERFAHREN_OHNE_TITEL_BEENDET, T(2025, 4, 1)),
            Ereignis(E.ZUSTELLUNG_URTEIL, T(2025, 9, 1)),
        ]
    )
    assert ergebnis.status is Status.TITULIERT


def test_mahnbescheid_nach_titel_aendert_nichts() -> None:
    ergebnis = status(
        [
            Ereignis(E.ZUSTELLUNG_URTEIL, T(2025, 3, 3)),
            Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2025, 4, 1)),
        ]
    )
    assert ergebnis.status is Status.TITULIERT


def test_ereignisse_nach_dem_stichtag_und_ohne_datum_zaehlen_nicht() -> None:
    ergebnis = status(
        [
            Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, None),
            Ereignis(E.ZUSTELLUNG_URTEIL, T(2026, 7, 1)),
        ]
    )
    assert ergebnis.status is Status.OFFEN


# --- Ausgleich und Nachwirkung -----------------------------------------------------------------


def test_ausgleich_fuehrt_in_die_nachwirkung() -> None:
    ergebnis = ausgeglichen()
    assert ergebnis.status is Status.NACHWIRKUNG
    assert ergebnis.ausgeglichen_am == AUSGLEICH
    assert [a.typ for a in ergebnis.aufgaben] == [
        Aufgabentyp.QUITTUNG_ANFORDERN,
        Aufgabentyp.AUSKUNFTEI_PRUEFEN,
        Aufgabentyp.AUSKUNFTEI_LOESCHDATUM_UEBERWACHEN,
    ]


def test_aufgaben_mit_norm_und_faelligkeit() -> None:
    ergebnis = ausgeglichen()
    quittung = aufgabe(ergebnis, Aufgabentyp.QUITTUNG_ANFORDERN)
    assert quittung.norm == "§ 368 BGB"
    assert quittung.faellig_ab == AUSGLEICH
    assert quittung.erledigt_am is None
    assert not quittung.information
    auskunftei = aufgabe(ergebnis, Aufgabentyp.AUSKUNFTEI_PRUEFEN)
    assert auskunftei.norm == "Art. 15 DSGVO"
    assert auskunftei.faellig_ab == T(2026, 3, 30)  # vier Wochen nach dem Ausgleich
    ueberwachen = aufgabe(ergebnis, Aufgabentyp.AUSKUNFTEI_LOESCHDATUM_UEBERWACHEN)
    assert ueberwachen.information
    assert ueberwachen.faellig_ab is None  # Löschfristen der Auskunfteien zurückgestellt


def test_titel_herausverlangen_nur_bei_titel() -> None:
    ergebnis = ausgeglichen([Ereignis(E.ZUSTELLUNG_URTEIL, T(2025, 3, 3))])
    titel = aufgabe(ergebnis, Aufgabentyp.TITEL_HERAUSVERLANGEN)
    assert titel.norm == "§ 371 BGB analog; § 757 Abs. 1 ZPO"
    assert ergebnis.status is Status.NACHWIRKUNG


def test_vorzeitige_loeschung_nur_bei_eintragung() -> None:
    ergebnis = ausgeglichen([Ereignis(E.EINTRAGUNGSANORDNUNG, T(2025, 5, 5))])
    loeschung = aufgabe(ergebnis, Aufgabentyp.VORZEITIGE_LOESCHUNG)
    assert loeschung.norm == "§ 882e Abs. 3 Nr. 1 ZPO"
    assert Merkmal.SCHULDNERVERZEICHNIS_EINGETRAGEN in ergebnis.merkmale


def test_erledigung_durch_ereignisse_nach_dem_ausgleich() -> None:
    ergebnis = ausgeglichen(
        [
            Ereignis(E.QUITTUNG_ERHALTEN, T(2026, 1, 15)),  # vor dem Ausgleich: zählt nicht
            Ereignis(E.ERLEDIGT_GEMELDET_AUSKUNFTEI, T(2026, 4, 20)),
        ]
    )
    assert aufgabe(ergebnis, Aufgabentyp.QUITTUNG_ANFORDERN).erledigt_am is None
    assert aufgabe(ergebnis, Aufgabentyp.AUSKUNFTEI_PRUEFEN).erledigt_am == T(2026, 4, 20)


def test_restschuld_null_ohne_zahlung_ist_kein_ausgleich() -> None:
    ergebnis = status(bestandteile=())
    assert ergebnis.status is Status.OFFEN
    assert ergebnis.aufgaben == ()


def test_ueberzahlung_ist_ausgleich() -> None:
    ergebnis = status(zahlungen=[Zahlung(AUSGLEICH, D("1200.00"))])
    assert ergebnis.status is Status.NACHWIRKUNG
    assert ergebnis.ausgeglichen_am == AUSGLEICH


def test_ausgleichstag_ist_die_letzte_angerechnete_zahlung() -> None:
    ergebnis = status(
        zahlungen=[Zahlung(T(2026, 1, 5), D("400.00")), Zahlung(AUSGLEICH, D("600.00"))]
    )
    assert ergebnis.ausgeglichen_am == AUSGLEICH


# --- Schließen ------------------------------------------------------------------------------------


def test_geschlossen_setzt_der_nutzer() -> None:
    ergebnis = ausgeglichen(
        [*alle_erledigt(T(2026, 4, 1)), Ereignis(E.AKTE_GESCHLOSSEN, T(2026, 4, 2))]
    )
    assert ergebnis.status is Status.GESCHLOSSEN
    assert ergebnis.warnungen == ()


def test_alle_aufgaben_erledigt_ausgeglichen() -> None:
    """Entscheidung vom 21.11.2026: ausgeglichen heißt bereit zum Schließen."""
    ergebnis = ausgeglichen(alle_erledigt(T(2026, 4, 1)))
    assert ergebnis.status is Status.AUSGEGLICHEN


def test_vor_der_erledigung_nachwirkung() -> None:
    ergebnis = ausgeglichen(alle_erledigt(T(2026, 4, 1)), stichtag=T(2026, 3, 31))
    assert ergebnis.status is Status.NACHWIRKUNG


def test_informationen_bleiben_nach_dem_schliessen_sichtbar() -> None:
    ergebnis = ausgeglichen(
        [*alle_erledigt(T(2026, 4, 1)), Ereignis(E.AKTE_GESCHLOSSEN, T(2026, 4, 2))]
    )
    ueberwachen = aufgabe(ergebnis, Aufgabentyp.AUSKUNFTEI_LOESCHDATUM_UEBERWACHEN)
    assert ueberwachen.erledigt_am is None


def test_schliessen_mit_offener_aufgabe_wirkt_nicht() -> None:
    ergebnis = ausgeglichen(
        [Ereignis(E.QUITTUNG_ERHALTEN, T(2026, 4, 1)), Ereignis(E.AKTE_GESCHLOSSEN, T(2026, 4, 2))]
    )
    assert ergebnis.status is Status.NACHWIRKUNG
    assert any("offen" in w for w in ergebnis.warnungen)


def test_schliessen_vor_erledigung_wirkt_nicht() -> None:
    ergebnis = ausgeglichen(
        [*alle_erledigt(T(2026, 4, 3)), Ereignis(E.AKTE_GESCHLOSSEN, T(2026, 4, 2))]
    )
    assert ergebnis.status is Status.AUSGEGLICHEN  # heute erledigt, aber nicht am 02.04.
    assert any("offen" in w for w in ergebnis.warnungen)


def test_schliessen_mit_restschuld_wirkt_nicht() -> None:
    ergebnis = status([Ereignis(E.AKTE_GESCHLOSSEN, T(2026, 4, 2))])
    assert ergebnis.status is Status.OFFEN
    assert any("Restschuld" in w for w in ergebnis.warnungen)


# --- Rückweg (E-37) -------------------------------------------------------------------------


def test_rueckweg_bei_restschuld_ueber_null() -> None:
    kosten = Bestandteil(
        "kosten", Bestandteilart.KOSTEN_VOLLSTRECKUNG, D("50.00"), entstanden_am=T(2026, 5, 4)
    )
    ergebnis = status(
        [Ereignis(E.ZUSTELLUNG_URTEIL, T(2025, 3, 3))],
        zahlungen=[Zahlung(AUSGLEICH, D("1000.00"))],
        bestandteile=(HF, kosten),
    )
    assert ergebnis.status is Status.TITULIERT
    assert ergebnis.ausgeglichen_am is None
    assert ergebnis.aufgaben == ()


def test_rueckweg_auch_aus_geschlossen() -> None:
    kosten = Bestandteil(
        "kosten", Bestandteilart.KOSTEN_VOLLSTRECKUNG, D("50.00"), entstanden_am=T(2026, 5, 4)
    )
    ergebnis = status(
        [*alle_erledigt(T(2026, 4, 1)), Ereignis(E.AKTE_GESCHLOSSEN, T(2026, 4, 2))],
        zahlungen=[Zahlung(AUSGLEICH, D("1000.00"))],
        bestandteile=(HF, kosten),
    )
    assert ergebnis.status is Status.OFFEN
    assert any("geschlossen" in w for w in ergebnis.warnungen)


def test_nach_erneutem_ausgleich_neue_aufgaben() -> None:
    kosten = Bestandteil(
        "kosten", Bestandteilart.KOSTEN_VOLLSTRECKUNG, D("50.00"), entstanden_am=T(2026, 5, 4)
    )
    ergebnis = status(
        [*alle_erledigt(T(2026, 4, 1)), Ereignis(E.AKTE_GESCHLOSSEN, T(2026, 4, 2))],
        zahlungen=[Zahlung(AUSGLEICH, D("1000.00")), Zahlung(T(2026, 6, 1), D("50.00"))],
        bestandteile=(HF, kosten),
    )
    assert ergebnis.status is Status.NACHWIRKUNG
    assert ergebnis.ausgeglichen_am == T(2026, 6, 1)
    assert aufgabe(ergebnis, Aufgabentyp.QUITTUNG_ANFORDERN).erledigt_am is None


# --- Merkmale ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ereignisse", "aktiv"),
    [
        ([E.RATENPLAN_VEREINBART], True),
        ([E.RATENPLAN_VEREINBART, E.RATENPLAN_BEENDET], False),
        ([E.RATENPLAN_VEREINBART, E.RATENPLAN_BEENDET, E.RATENPLAN_VEREINBART], True),
    ],
)
def test_ratenplan(ereignisse: list[Ereignistyp], aktiv: bool) -> None:
    folge = [Ereignis(typ, T(2025, 1, 1 + i)) for i, typ in enumerate(ereignisse)]
    assert (Merkmal.RATENPLAN_AKTIV in status(folge).merkmale) is aktiv


@pytest.mark.parametrize(
    ("ereignisse", "aktiv"),
    [
        ([E.VOLLSTRECKUNGSMASSNAHME_BEGONNEN], True),
        ([E.VOLLSTRECKUNGSMASSNAHME_BEGONNEN, E.VOLLSTRECKUNGSMASSNAHME_AUFGEHOBEN], False),
        (
            [
                E.VOLLSTRECKUNGSMASSNAHME_BEGONNEN,
                E.VOLLSTRECKUNGSMASSNAHME_BEGONNEN,
                E.VOLLSTRECKUNGSMASSNAHME_AUFGEHOBEN,
            ],
            True,  # zwei Maßnahmen, eine aufgehoben
        ),
        ([E.VOLLSTRECKUNGSHANDLUNG], False),
    ],
)
def test_vollstreckung(ereignisse: list[Ereignistyp], aktiv: bool) -> None:
    folge = [Ereignis(typ, T(2025, 1, 1 + i)) for i, typ in enumerate(ereignisse)]
    assert (Merkmal.VOLLSTRECKUNG_AKTIV in status(folge).merkmale) is aktiv


@pytest.mark.parametrize(
    ("ereignisse", "aktiv"),
    [
        ([E.FORDERUNG_BESTRITTEN], True),
        ([E.FORDERUNG_BESTRITTEN, E.BESTREITEN_BEENDET], False),
    ],
)
def test_bestritten(ereignisse: list[Ereignistyp], aktiv: bool) -> None:
    folge = [Ereignis(typ, T(2025, 1, 1 + i)) for i, typ in enumerate(ereignisse)]
    assert (Merkmal.BESTRITTEN in status(folge).merkmale) is aktiv


def test_verjaehrung_eingewandt() -> None:
    ergebnis = status([Ereignis(E.VERJAEHRUNG_EINGEWANDT, T(2025, 1, 1))])
    assert ergebnis.merkmale == frozenset({Merkmal.VERJAEHRUNG_EINGEWANDT})


def test_schuldnerverzeichnis_bis_zur_loeschung() -> None:
    eintragung = Ereignis(E.EINTRAGUNGSANORDNUNG, T(2025, 5, 5))
    assert Merkmal.SCHULDNERVERZEICHNIS_EINGETRAGEN in status([eintragung]).merkmale
    geloescht = status([eintragung, Ereignis(E.LOESCHUNG_SCHULDNERVERZEICHNIS, T(2026, 1, 1))])
    assert Merkmal.SCHULDNERVERZEICHNIS_EINGETRAGEN not in geloescht.merkmale


def test_schuldnerverzeichnis_nach_drei_jahren_geloescht() -> None:
    """§ 882e Abs. 1 ZPO: Löschung von Amts wegen nach Ablauf von drei Jahren."""
    eintragung = Ereignis(E.EINTRAGUNGSANORDNUNG, T(2023, 5, 5))
    am_letzten_tag = status([eintragung], stichtag=T(2026, 5, 5))
    danach = status([eintragung], stichtag=T(2026, 5, 6))
    assert Merkmal.SCHULDNERVERZEICHNIS_EINGETRAGEN in am_letzten_tag.merkmale
    assert Merkmal.SCHULDNERVERZEICHNIS_EINGETRAGEN not in danach.merkmale


def test_vorzeitige_loeschung_erledigt_durch_loeschung() -> None:
    ergebnis = ausgeglichen(
        [
            Ereignis(E.EINTRAGUNGSANORDNUNG, T(2025, 5, 5)),
            Ereignis(E.LOESCHUNG_SCHULDNERVERZEICHNIS, T(2026, 4, 10)),
        ]
    )
    assert aufgabe(ergebnis, Aufgabentyp.VORZEITIGE_LOESCHUNG).erledigt_am == T(2026, 4, 10)
    assert Merkmal.SCHULDNERVERZEICHNIS_EINGETRAGEN not in ergebnis.merkmale


# --- Eskalation ---------------------------------------------------------------------------------


def test_hinweis_bei_vollstreckung_trotz_erfuellung() -> None:
    ergebnis = ausgeglichen([Ereignis(E.VOLLSTRECKUNGSHANDLUNG, T(2026, 4, 1))])
    assert HINWEIS_VOLLSTRECKUNG_TROTZ_ERFUELLUNG in ergebnis.hinweise
    assert "§ 767 ZPO" in HINWEIS_VOLLSTRECKUNG_TROTZ_ERFUELLUNG
    assert "§ 769 ZPO" in HINWEIS_VOLLSTRECKUNG_TROTZ_ERFUELLUNG


def test_hinweis_bei_laufender_massnahme_nach_ausgleich() -> None:
    ergebnis = ausgeglichen([Ereignis(E.VOLLSTRECKUNGSMASSNAHME_BEGONNEN, T(2025, 9, 1))])
    assert HINWEIS_VOLLSTRECKUNG_TROTZ_ERFUELLUNG in ergebnis.hinweise


def test_kein_hinweis_bei_vollstreckung_vor_dem_ausgleich() -> None:
    ergebnis = ausgeglichen([Ereignis(E.VOLLSTRECKUNGSHANDLUNG, T(2025, 9, 1))])
    assert ergebnis.hinweise == ()
