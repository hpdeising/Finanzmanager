# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests von Zinsberechnung und Anrechnung (Fachkonzept Kap. 5.1 bis 5.3).

Die Beträge sind so gewählt, dass sich jeder Erwartungswert ohne Rechner prüfen lässt:
3650,00 € zu 10 % bei act_365 sind genau 1,00 € je Tag, 3600,00 € zu 10 % bei act_360 und
30_360 ebenso, 3660,00 € zu 10 % bei act_act im Schaltjahr auch. Die Optionen, die GK-0001
nicht berührt, sind hier abgedeckt; GK-0001 selbst prüft ``tests/golden``.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.kern.stammdaten import StammdatenFehlenError, lade_basiszinsreihe
from app.module.verbindlichkeiten.berechnung import Ergebnis, berechne
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Anrechnungsregel,
    Bestandteil,
    Bestandteilart,
    EingabeUngueltigError,
    Gruppe,
    Tageszaehlung,
    Teilung,
    Zahltag,
    Zahlung,
    Zinsbeginn,
    Zinsregel,
    Zinsregeltyp,
)

T = date
D = Decimal
REIHE = lade_basiszinsreihe()


def fest(ab: date, satz: str = "10", bis: date | None = None) -> Zinsregel:
    return Zinsregel(Zinsregeltyp.FEST, ab=ab, bis=bis, satz=D(satz))


def gesetzlich(ab: date) -> Zinsregel:
    return Zinsregel(Zinsregeltyp.GESETZLICH_288_1, ab=ab)


def keine(ab: date | None = None) -> Zinsregel:
    return Zinsregel(Zinsregeltyp.KEINE, ab=ab)


def hf(betrag: str, *regeln: Zinsregel, entstanden_am: date | None = None) -> Bestandteil:
    return Bestandteil(
        "hauptforderung", Bestandteilart.HAUPTFORDERUNG, D(betrag), regeln, entstanden_am
    )


def kosten(
    kennung: str, betrag: str, *regeln: Zinsregel, entstanden_am: date | None = None
) -> Bestandteil:
    art = Bestandteilart(kennung.rstrip("_0123456789"))
    return Bestandteil(kennung, art, D(betrag), regeln or (keine(),), entstanden_am)


def rechne(
    *bestandteile: Bestandteil,
    zahlungen: tuple[tuple[date, str], ...] = (),
    stichtag: date,
    **parameter: Any,
) -> Ergebnis:
    """``parameter`` sind die Felder von ``Aktenparameter``."""
    return berechne(
        Aktenparameter(**parameter),
        list(bestandteile),
        [Zahlung(tag, D(betrag)) for tag, betrag in zahlungen],
        stichtag,
        REIHE,
    )


def abschnitte(ergebnis: Ergebnis) -> list[tuple[str, str, str, str, int, int, str, str]]:
    """Bestandteil, von, bis, grund, tage, tagesbasis, basis, zins_gerundet."""
    return [
        (
            a.bestandteil,
            a.von.isoformat(),
            a.bis.isoformat(),
            "+".join(g.value for g in a.gruende),
            a.tage,
            a.tagesbasis,
            format(a.basis, "f"),
            format(a.zins, "f"),
        )
        for a in ergebnis.abschnitte
    ]


def anrechnungen(ergebnis: Ergebnis) -> list[tuple[str, str, str, str, str]]:
    """Zahlung, bestandteil, gruppe, angerechnet, offen_danach."""
    return [
        (
            z.zahlung.datum.isoformat(),
            z.bestandteil or "",
            z.gruppe.value if z.gruppe else "ueberzahlung",
            format(z.angerechnet, "f"),
            "" if z.offen_danach is None else format(z.offen_danach, "f"),
        )
        for z in ergebnis.anrechnungen
    ]


# --- Formatbeispiel aus Kap. 12 -------------------------------------------------------------


def test_formatbeispiel_aus_kapitel_12() -> None:
    """Hauptforderung 1000,00 €, 5 % fest ab 15.03.2025, act_365, alter_betrag, bgb_367,
    Zahlung 200,00 € am 20.05.2025, Stichtag 30.06.2025 (Kap. 12, Formatbeispiel)."""
    ergebnis = rechne(
        hf("1000.00", fest(T(2025, 3, 15), "5")),
        zahlungen=((T(2025, 5, 20), "200.00"),),
        stichtag=T(2025, 6, 30),
    )
    a, b = ergebnis.abschnitte
    assert (a.von, a.bis, a.tage, a.tagesbasis, a.basis, a.basiszins, a.satz) == (
        T(2025, 3, 15),
        T(2025, 5, 20),
        67,
        365,
        D("1000.00"),
        None,
        D(5),
    )
    assert [g.value for g in a.gruende] == ["zinsbeginn"]
    assert str(a.zins_exakt).startswith("9.178082")
    assert a.zins == D("9.18")
    assert (b.von, b.bis, b.tage, b.basis, b.zins) == (
        T(2025, 5, 21),
        T(2025, 6, 30),
        41,
        D("809.18"),
        D("4.54"),
    )
    assert [g.value for g in b.gruende] == ["zahlung"]
    assert str(b.zins_exakt).startswith("4.544709")
    assert anrechnungen(ergebnis) == [
        ("2025-05-20", "hauptforderung", "zinsen", "9.18", "0.00"),
        ("2025-05-20", "hauptforderung", "hauptforderung", "190.82", "809.18"),
    ]
    assert (ergebnis.hauptforderung, ergebnis.zinsen) == (D("809.18"), D("4.54"))


# --- Zinsbeginn, Pause, Regelwechsel (Kap. 5.2 Schritt 1, E-24) ------------------------------


@pytest.mark.parametrize(
    ("zinsbeginn", "von", "tage"),
    [(Zinsbeginn.GENANNTER_TAG, "2025-01-01", 10), (Zinsbeginn.FOLGETAG, "2025-01-02", 9)],
)
def test_zinsbeginn(zinsbeginn: Zinsbeginn, von: str, tage: int) -> None:
    ergebnis = rechne(
        hf("3650.00", fest(T(2025, 1, 1))), stichtag=T(2025, 1, 10), zinsbeginn=zinsbeginn
    )
    assert abschnitte(ergebnis) == [
        ("hauptforderung", von, "2025-01-10", "zinsbeginn", tage, 365, "3650.00", f"{tage}.00")
    ]


@pytest.mark.parametrize(
    "regeln",
    [
        pytest.param(
            (fest(T(2025, 1, 1), bis=T(2025, 1, 10)), keine(T(2025, 1, 11)), fest(T(2025, 1, 21))),
            id="Pause durch Zinsregel keine",
        ),
        pytest.param(
            (fest(T(2025, 1, 1), bis=T(2025, 1, 10)), fest(T(2025, 1, 21))),
            id="Pause durch Ende einer Zinsregel",
        ),
    ],
)
@pytest.mark.parametrize(
    ("zinsbeginn", "erwartet"),
    [
        (
            Zinsbeginn.GENANNTER_TAG,
            [("2025-01-01", "2025-01-10", 10), ("2025-01-21", "2025-01-31", 11)],
        ),
        (Zinsbeginn.FOLGETAG, [("2025-01-02", "2025-01-10", 9), ("2025-01-22", "2025-01-31", 10)]),
    ],
)
def test_nach_einer_pause_beginnt_ein_neuer_zinslauf(
    regeln: tuple[Zinsregel, ...], zinsbeginn: Zinsbeginn, erwartet: list[tuple[str, str, int]]
) -> None:
    """E-24: zinsbeginn gilt für den ersten Zinstag jedes Zinslaufs, auch nach einer Pause."""
    ergebnis = rechne(hf("3650.00", *regeln), stichtag=T(2025, 1, 31), zinsbeginn=zinsbeginn)
    assert [(a[1], a[2], a[3], a[4]) for a in abschnitte(ergebnis)] == [
        (von, bis, "zinsbeginn", tage) for von, bis, tage in erwartet
    ]


@pytest.mark.parametrize("mit_bis", [True, False])
def test_regelwechsel_ohne_luecke_setzt_den_zinslauf_fort(mit_bis: bool) -> None:
    """Folgt eine verzinsliche Regel ohne Lücke, wirkt zinsbeginn dort nicht (E-24)."""
    erste = fest(T(2025, 1, 1), bis=T(2025, 1, 10) if mit_bis else None)
    ergebnis = rechne(
        hf("3650.00", erste, fest(T(2025, 1, 11), "20")),
        stichtag=T(2025, 1, 20),
        zinsbeginn=Zinsbeginn.FOLGETAG,
    )
    assert abschnitte(ergebnis) == [
        ("hauptforderung", "2025-01-02", "2025-01-10", "zinsbeginn", 9, 365, "3650.00", "9.00"),
        ("hauptforderung", "2025-01-11", "2025-01-20", "regelwechsel", 10, 365, "3650.00", "20.00"),
    ]


def test_stichtag_vor_dem_zinsbeginn() -> None:
    ergebnis = rechne(hf("3650.00", fest(T(2025, 1, 1))), stichtag=T(2024, 12, 31))
    assert ergebnis.abschnitte == ()
    assert (ergebnis.hauptforderung, ergebnis.zinsen, ergebnis.gesamt) == (
        D("3650.00"),
        D(0),
        D("3650.00"),
    )


# --- Teilung (Kap. 5.2 Schritt 2, E-31, E-32) ------------------------------------------------


@pytest.mark.parametrize(
    ("teilung", "beginne"),
    [
        (Teilung.KALENDER, ["2025-07-01", "2026-01-01", "2026-07-01"]),
        # 2025-07-01 und 2026-01-01 haben beide 1,27 % (stammdaten/basiszinssatz.yaml).
        (Teilung.SATZWECHSEL, ["2025-07-01", "2026-07-01"]),
    ],
)
def test_halbjahr_kalender_und_satzwechsel(teilung: Teilung, beginne: list[str]) -> None:
    ergebnis = rechne(
        hf("1000.00", gesetzlich(T(2025, 7, 1))), stichtag=T(2026, 12, 31), teilung=teilung
    )
    assert [a[1] for a in abschnitte(ergebnis)] == beginne
    assert [a[3] for a in abschnitte(ergebnis)] == ["zinsbeginn"] + ["halbjahr"] * (
        len(beginne) - 1
    )
    erster = ergebnis.abschnitte[0]
    assert (erster.basiszins, erster.satz) == (D("1.27"), D("6.27"))
    letzter = ergebnis.abschnitte[-1]
    assert (letzter.basiszins, letzter.satz) == (D("1.52"), D("6.52"))


def test_fester_satz_wird_nicht_halbjaehrlich_geteilt() -> None:
    ergebnis = rechne(hf("3650.00", fest(T(2025, 6, 1))), stichtag=T(2025, 7, 31))
    assert [a[1] for a in abschnitte(ergebnis)] == ["2025-06-01"]


def test_act_act_teilt_am_jahreswechsel_auch_bei_festem_satz() -> None:
    """E-31: Tagesbasis 365 bis 31.12.2027, 366 ab 01.01.2028 (Schaltjahr)."""
    ergebnis = rechne(
        hf("3660.00", fest(T(2027, 12, 30))),
        stichtag=T(2028, 1, 2),
        tageszaehlung=Tageszaehlung.ACT_ACT,
    )
    assert abschnitte(ergebnis) == [
        # 3660 x 10 % x 2 / 365 = 2,0054…
        ("hauptforderung", "2027-12-30", "2027-12-31", "zinsbeginn", 2, 365, "3660.00", "2.01"),
        ("hauptforderung", "2028-01-01", "2028-01-02", "jahreswechsel", 2, 366, "3660.00", "2.00"),
    ]


def test_mehrere_gruende_in_fester_reihenfolge() -> None:
    """Kap. 12: halbjahr, jahreswechsel, teilungstag, zahlung, regelwechsel."""
    ergebnis = rechne(
        hf("1000.00", gesetzlich(T(2025, 12, 1))),
        zahlungen=((T(2025, 12, 31), "1.00"),),
        stichtag=T(2026, 1, 10),
        tageszaehlung=Tageszaehlung.ACT_ACT,
        teilungstage=frozenset({T(2026, 1, 1)}),
    )
    assert [a[3] for a in abschnitte(ergebnis)] == [
        "zinsbeginn",
        "halbjahr+jahreswechsel+teilungstag+zahlung",
    ]


def test_act_360() -> None:
    ergebnis = rechne(
        hf("3600.00", fest(T(2025, 1, 1))),
        stichtag=T(2025, 1, 30),
        tageszaehlung=Tageszaehlung.ACT_360,
    )
    assert abschnitte(ergebnis) == [
        ("hauptforderung", "2025-01-01", "2025-01-30", "zinsbeginn", 30, 360, "3600.00", "30.00")
    ]


@pytest.mark.parametrize(
    ("teilungstage", "erwartet"),
    [
        (
            frozenset({T(2027, 3, 1)}),
            [
                ("2027-01-31", "2027-02-28", "zinsbeginn", 29, "29.00"),
                ("2027-03-01", "2027-03-31", "teilungstag", 32, "32.00"),
            ],
        ),
        (frozenset[date](), [("2027-01-31", "2027-03-31", "zinsbeginn", 61, "61.00")]),
    ],
)
def test_30_360_geteilt_wie_ungeteilt(
    teilungstage: frozenset[date], erwartet: list[tuple[str, str, str, int, str]]
) -> None:
    """E-34, Tabelle Kap. 5.1: 31.01.-28.02.2027 mit unverzinstem Vortag 29 Tage, 01.03.-31.03.
    als weiterer Abschnitt 32 Tage; ungeteilt dieselben 61."""
    ergebnis = rechne(
        hf("3600.00", fest(T(2027, 1, 31))),
        stichtag=T(2027, 3, 31),
        tageszaehlung=Tageszaehlung.DREISSIG_360,
        teilungstage=teilungstage,
    )
    assert [(a[1], a[2], a[3], a[4], a[7]) for a in abschnitte(ergebnis)] == erwartet


def test_30_360_nach_einer_pause_zaehlt_mit_plus_eins() -> None:
    """E-34, Tabelle Kap. 5.1: 01.03.-31.03.2027 nach einer Pause sind 30 Tage, nicht 32."""
    ergebnis = rechne(
        hf(
            "3600.00",
            fest(T(2027, 1, 1), bis=T(2027, 1, 31)),
            keine(T(2027, 2, 1)),
            fest(T(2027, 3, 1)),
        ),
        stichtag=T(2027, 3, 31),
        tageszaehlung=Tageszaehlung.DREISSIG_360,
    )
    assert [(a[1], a[3], a[4]) for a in abschnitte(ergebnis)] == [
        ("2027-01-01", "zinsbeginn", 30),
        ("2027-03-01", "zinsbeginn", 30),
    ]


def test_teilungstage_nur_innerhalb_des_zinslaufs() -> None:
    """E-32: Ein Teilungstag außerhalb des Zinslaufs wirkt nicht; am ersten Zinstag steht
    zinsbeginn allein."""
    ergebnis = rechne(
        hf("3650.00", fest(T(2025, 1, 1))),
        stichtag=T(2025, 1, 20),
        teilungstage=frozenset({T(2024, 12, 15), T(2025, 1, 1), T(2025, 1, 11), T(2025, 2, 15)}),
    )
    assert [(a[1], a[2], a[3]) for a in abschnitte(ergebnis)] == [
        ("2025-01-01", "2025-01-10", "zinsbeginn"),
        ("2025-01-11", "2025-01-20", "teilungstag"),
    ]


# --- Zahltag (E-30) ----------------------------------------------------------------------------


def test_zahltag_verminderter_betrag() -> None:
    """Der verminderte Betrag gilt ab dem Zahltag; angerechnet wird auf die Zinsen davor."""
    ergebnis = rechne(
        hf("3650.00", fest(T(2025, 1, 1))),
        zahlungen=((T(2025, 1, 11), "375.00"),),
        stichtag=T(2025, 1, 20),
        zahltag=Zahltag.VERMINDERTER_BETRAG,
    )
    assert abschnitte(ergebnis) == [
        ("hauptforderung", "2025-01-01", "2025-01-10", "zinsbeginn", 10, 365, "3650.00", "10.00"),
        ("hauptforderung", "2025-01-11", "2025-01-20", "zahlung", 10, 365, "3285.00", "9.00"),
    ]
    assert anrechnungen(ergebnis) == [
        ("2025-01-11", "hauptforderung", "zinsen", "10.00", "0.00"),
        ("2025-01-11", "hauptforderung", "hauptforderung", "365.00", "3285.00"),
    ]


def test_zahltag_alter_betrag() -> None:
    """Am Zahltag wird noch der alte Betrag verzinst; angerechnet wird einschließlich Zahltag."""
    ergebnis = rechne(
        hf("3650.00", fest(T(2025, 1, 1))),
        zahlungen=((T(2025, 1, 11), "375.00"),),
        stichtag=T(2025, 1, 20),
    )
    assert [a[:7] for a in abschnitte(ergebnis)] == [
        ("hauptforderung", "2025-01-01", "2025-01-11", "zinsbeginn", 11, 365, "3650.00"),
        ("hauptforderung", "2025-01-12", "2025-01-20", "zahlung", 9, 365, "3286.00"),
    ]
    assert anrechnungen(ergebnis) == [
        ("2025-01-11", "hauptforderung", "zinsen", "11.00", "0.00"),
        ("2025-01-11", "hauptforderung", "hauptforderung", "364.00", "3286.00"),
    ]


def test_zahlung_am_stichtag_zaehlt_danach_nicht() -> None:
    ergebnis = rechne(
        hf("3650.00", fest(T(2025, 1, 1))),
        zahlungen=((T(2025, 1, 10), "10.00"), (T(2025, 1, 11), "5.00")),
        stichtag=T(2025, 1, 10),
    )
    assert anrechnungen(ergebnis) == [("2025-01-10", "hauptforderung", "zinsen", "10.00", "0.00")]
    assert (ergebnis.zinsen, ergebnis.gesamt) == (D("0.00"), D("3650.00"))


# --- Anrechnung (Kap. 5.3) ---------------------------------------------------------------------

ZWEI = (hf("3650.00", fest(T(2025, 1, 1))), kosten("kosten_verfahren", "50.00"))


def test_bgb_367_kosten_zinsen_hauptforderung() -> None:
    ergebnis = rechne(*ZWEI, zahlungen=((T(2025, 1, 10), "100.00"),), stichtag=T(2025, 1, 10))
    assert anrechnungen(ergebnis) == [
        ("2025-01-10", "kosten_verfahren", "kosten", "50.00", "0.00"),
        ("2025-01-10", "hauptforderung", "zinsen", "10.00", "0.00"),
        ("2025-01-10", "hauptforderung", "hauptforderung", "40.00", "3610.00"),
    ]


def test_bgb_497_kosten_hauptforderung_zinsen() -> None:
    ergebnis = rechne(
        *ZWEI,
        zahlungen=((T(2025, 1, 10), "100.00"),),
        stichtag=T(2025, 1, 10),
        anrechnung=Anrechnungsregel.BGB_497,
    )
    assert anrechnungen(ergebnis) == [
        ("2025-01-10", "kosten_verfahren", "kosten", "50.00", "0.00"),
        ("2025-01-10", "hauptforderung", "hauptforderung", "50.00", "3600.00"),
    ]
    assert (ergebnis.hauptforderung, ergebnis.zinsen, ergebnis.kosten) == (
        D("3600.00"),
        D("10.00"),
        D("0.00"),
    )


def test_individuelle_reihenfolge() -> None:
    ergebnis = rechne(
        *ZWEI,
        zahlungen=((T(2025, 1, 10), "3655.00"),),
        stichtag=T(2025, 1, 10),
        anrechnung=Anrechnungsregel.INDIVIDUELL,
        reihenfolge=(Gruppe.HAUPTFORDERUNG, Gruppe.ZINSEN, Gruppe.KOSTEN),
    )
    assert anrechnungen(ergebnis) == [
        ("2025-01-10", "hauptforderung", "hauptforderung", "3650.00", "0.00"),
        ("2025-01-10", "hauptforderung", "zinsen", "5.00", "5.00"),
    ]


def test_ueberzahlung() -> None:
    """Kap. 5.3: Was sich nicht mehr anrechnen lässt, ist Überzahlung. Ohne offenen Betrag
    entstehen keine weiteren Zinsen."""
    ergebnis = rechne(*ZWEI, zahlungen=((T(2025, 1, 10), "4000.00"),), stichtag=T(2025, 1, 31))
    assert anrechnungen(ergebnis) == [
        ("2025-01-10", "kosten_verfahren", "kosten", "50.00", "0.00"),
        ("2025-01-10", "hauptforderung", "zinsen", "10.00", "0.00"),
        ("2025-01-10", "hauptforderung", "hauptforderung", "3650.00", "0.00"),
        ("2025-01-10", "", "ueberzahlung", "290.00", ""),
    ]
    assert [a[1] for a in abschnitte(ergebnis)] == ["2025-01-01"]
    assert (ergebnis.ueberzahlung, ergebnis.gesamt) == (D("290.00"), D("0.00"))


def test_aelteste_kosten_zuerst() -> None:
    """E-35: innerhalb der Gruppe älteste Position zuerst, nach entstanden_am."""
    ergebnis = rechne(
        kosten("kosten_vollstreckung", "20.00", entstanden_am=T(2025, 3, 1)),
        kosten("kosten_verfahren", "20.00", entstanden_am=T(2025, 1, 15)),
        zahlungen=((T(2025, 4, 1), "30.00"),),
        stichtag=T(2025, 4, 1),
    )
    assert anrechnungen(ergebnis) == [
        ("2025-04-01", "kosten_verfahren", "kosten", "20.00", "0.00"),
        ("2025-04-01", "kosten_vollstreckung", "kosten", "10.00", "10.00"),
    ]


def test_aelteste_zinsen_zuerst_ueber_bestandteile() -> None:
    """Zinsen eines früher endenden Abschnitts sind älter, auch bei einem anderen Bestandteil."""
    ergebnis = rechne(
        kosten("kosten_verfahren", "365.00", fest(T(2025, 1, 1))),
        hf("3650.00", fest(T(2025, 1, 1), bis=T(2025, 1, 5))),
        zahlungen=((T(2025, 1, 10), "5.50"),),
        stichtag=T(2025, 1, 10),
        anrechnung=Anrechnungsregel.INDIVIDUELL,
        reihenfolge=(Gruppe.ZINSEN, Gruppe.KOSTEN, Gruppe.HAUPTFORDERUNG),
    )
    assert anrechnungen(ergebnis) == [
        ("2025-01-10", "hauptforderung", "zinsen", "5.00", "0.00"),
        ("2025-01-10", "kosten_verfahren", "zinsen", "0.50", "0.50"),
    ]


def test_aufgelaufene_zinsen_als_bestandteil() -> None:
    """Feste aufgelaufene Zinsen (Kap. 4.3) sind Zinsen, älter als laufende, nie verzinst."""
    ergebnis = rechne(
        Bestandteil("zinsen", Bestandteilart.ZINSEN, D("20.00"), (), T(2024, 12, 31)),
        hf("3650.00", fest(T(2025, 1, 1))),
        zahlungen=((T(2025, 1, 10), "25.00"),),
        stichtag=T(2025, 1, 10),
    )
    assert [a[0] for a in abschnitte(ergebnis)] == ["hauptforderung"]
    assert anrechnungen(ergebnis) == [
        ("2025-01-10", "zinsen", "zinsen", "20.00", "0.00"),
        ("2025-01-10", "hauptforderung", "zinsen", "5.00", "5.00"),
    ]
    assert ergebnis.zinsen == D("5.00")


# --- Fehler --------------------------------------------------------------------------------------


def test_fehlender_basiszins_wirft() -> None:
    """Fehlt ein Stammdatensatz für einen Tag, wird nicht geschätzt (CLAUDE.md)."""
    with pytest.raises(StammdatenFehlenError):
        rechne(hf("1000.00", gesetzlich(T(2001, 6, 1))), stichtag=T(2002, 6, 30))


def test_kennungen_muessen_eindeutig_sein() -> None:
    with pytest.raises(EingabeUngueltigError):
        rechne(hf("1.00"), hf("2.00"), stichtag=T(2025, 1, 1))


# --- Entstehung der Bestandteile (Review zu #25, Kap. 5.3, P-20 offen) ---------------------------


def test_zahlung_geht_nicht_auf_spaeter_entstehende_kosten() -> None:
    """Angerechnet wird nur auf Bestandteile, die am Tag der Wertstellung schon entstanden sind.
    Der Rest ist Überzahlung und bleibt es, auch wenn später Kosten entstehen (P-20 offen)."""
    ergebnis = rechne(
        hf("100.00"),
        kosten("kosten_vollstreckung", "50.00", entstanden_am=T(2025, 6, 1)),
        zahlungen=((T(2024, 9, 20), "120.00"),),
        stichtag=T(2025, 8, 31),
    )
    assert anrechnungen(ergebnis) == [
        ("2024-09-20", "hauptforderung", "hauptforderung", "100.00", "0.00"),
        ("2024-09-20", "", "ueberzahlung", "20.00", ""),
    ]
    assert (ergebnis.hauptforderung, ergebnis.kosten, ergebnis.gesamt) == (
        D("0.00"),
        D("50.00"),
        D("50.00"),
    )
    assert ergebnis.ueberzahlung == D("20.00")


def test_am_zahltag_entstandene_kosten_sind_anrechenbar() -> None:
    ergebnis = rechne(
        hf("100.00"),
        kosten("kosten_vollstreckung", "50.00", entstanden_am=T(2024, 9, 20)),
        zahlungen=((T(2024, 9, 20), "120.00"),),
        stichtag=T(2024, 9, 30),
    )
    assert anrechnungen(ergebnis) == [
        ("2024-09-20", "kosten_vollstreckung", "kosten", "50.00", "0.00"),
        ("2024-09-20", "hauptforderung", "hauptforderung", "70.00", "30.00"),
    ]


def test_bestandteile_nach_dem_stichtag_zaehlen_nicht_zur_restschuld() -> None:
    ergebnis = rechne(
        hf("1000.00"),
        kosten("kosten_vollstreckung", "50.00", entstanden_am=T(2025, 9, 1)),
        Bestandteil(
            "hauptforderung_2",
            Bestandteilart.HAUPTFORDERUNG,
            D("3650.00"),
            (fest(T(2025, 1, 1)),),
            T(2025, 9, 1),
        ),
        stichtag=T(2025, 8, 31),
    )
    assert ergebnis.abschnitte == ()
    assert (ergebnis.hauptforderung, ergebnis.kosten, ergebnis.gesamt) == (
        D("1000.00"),
        D("0.00"),
        D("1000.00"),
    )


# --- Untergrenze null für den Jahressatz (Kap. 5.2 Schritt 6) ------------------------------------


def test_negativer_satz_ergibt_null_und_bleibt_im_rechenweg() -> None:
    """Basiszinssatz -0,88 % plus 0,5 Prozentpunkte ist negativ: Jahressatz 0, Zins 0,00 €."""
    regel = Zinsregel(Zinsregeltyp.BASISZINS_PLUS, ab=T(2022, 7, 1), aufschlag=D("0.5"))
    ergebnis = rechne(hf("1000.00", regel), stichtag=T(2022, 7, 10))
    (abschnitt,) = ergebnis.abschnitte
    assert (abschnitt.basiszins, abschnitt.satz, abschnitt.tage, abschnitt.zins) == (
        D("-0.88"),
        D(0),
        10,
        D("0.00"),
    )
    assert ergebnis.zinsen == D("0.00")
