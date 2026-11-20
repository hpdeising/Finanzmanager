# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eigenschaften von Zinsen und Anrechnung, geprüft mit zufälligen Fällen (Fachkonzept Kap. 12).

- Teilt man einen Zinslauf an beliebigen Tagen in Abschnitte, ändert sich die Summe der
  Zinstage nicht, für jede Tageszählung.
- Die Anrechnung verteilt exakt den Zahlbetrag, höchstens bis zur Restschuld; der Rest ist die
  berechnete Überzahlung.
- Zinskonten erzeugen keine Zinsen: Die Basis eines Abschnitts ist der Betrag des Bestandteils
  abzüglich der Anrechnung auf ihn, nie seine Zinsen (§ 289 S. 1 BGB).
- Nichts geht verloren: Beträge und Zinsen sind gleich Restschuld und Anrechnung.
"""

from datetime import date, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.kern.stammdaten import lade_basiszinsreihe
from app.module.verbindlichkeiten.berechnung import Ergebnis, berechne
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Anrechnungsregel,
    Bestandteil,
    Bestandteilart,
    Tageszaehlung,
    Teilung,
    Zahltag,
    Zahlung,
    Zinsbeginn,
    Zinsregel,
    Zinsregeltyp,
)
from app.module.verbindlichkeiten.zinsen import zinstage

REIHE = lade_basiszinsreihe()
EIN_TAG = timedelta(days=1)
# Innerhalb der belegten Basiszinsreihe (stammdaten/basiszinssatz.yaml).
TAGE = st.dates(min_value=date(2024, 1, 1), max_value=date(2026, 12, 31))
BETRAEGE = st.decimals(min_value=Decimal("0.01"), max_value=Decimal(100000), places=2)


# --- Tageszählung ------------------------------------------------------------------------------


def _summe_geteilt(von: date, bis: date, schnitte: set[int], zaehlung: Tageszaehlung) -> int:
    beginne = [von, *sorted(von + timedelta(days=s) for s in schnitte if s <= (bis - von).days)]
    summe = 0
    for nummer, beginn in enumerate(beginne):
        ende = beginne[nummer + 1] - EIN_TAG if nummer + 1 < len(beginne) else bis
        summe += zinstage(beginn, ende, zaehlung, vortag_verzinst=nummer > 0)
    return summe


@given(
    zaehlung=st.sampled_from(
        [Tageszaehlung.ACT_365, Tageszaehlung.ACT_360, Tageszaehlung.DREISSIG_360]
    ),
    von=st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 1, 1)),
    laenge=st.integers(min_value=0, max_value=1500),
    schnitte=st.sets(st.integers(min_value=1, max_value=1500), max_size=10),
)
def test_teilen_aendert_die_summe_der_zinstage_nicht(
    zaehlung: Tageszaehlung, von: date, laenge: int, schnitte: set[int]
) -> None:
    bis = von + timedelta(days=laenge)
    ungeteilt = zinstage(von, bis, zaehlung, vortag_verzinst=False)
    assert _summe_geteilt(von, bis, schnitte, zaehlung) == ungeteilt


@given(
    jahr=st.integers(min_value=2000, max_value=2100),
    tag=st.integers(min_value=0, max_value=364),
    laenge=st.integers(min_value=0, max_value=365),
    schnitte=st.sets(st.integers(min_value=1, max_value=365), max_size=10),
)
def test_teilen_innerhalb_eines_jahres_bei_act_act(
    jahr: int, tag: int, laenge: int, schnitte: set[int]
) -> None:
    """Bei act_act liegt jeder Abschnitt in einem Kalenderjahr (E-31)."""
    von = date(jahr, 1, 1) + timedelta(days=tag)
    bis = min(von + timedelta(days=laenge), date(jahr, 12, 31))
    ungeteilt = zinstage(von, bis, Tageszaehlung.ACT_ACT, vortag_verzinst=False)
    assert _summe_geteilt(von, bis, schnitte, Tageszaehlung.ACT_ACT) == ungeteilt


# --- Berechnung --------------------------------------------------------------------------------


@st.composite
def _zinsregeln(draw: st.DrawFn) -> tuple[Zinsregel, ...]:
    typ = draw(st.sampled_from([Zinsregeltyp.FEST, Zinsregeltyp.GESETZLICH_288_1, None]))
    if typ is None:
        return ()
    ab = draw(TAGE)
    if typ is Zinsregeltyp.FEST:
        satz = draw(st.decimals(min_value=0, max_value=20, places=2))
        return (Zinsregel(typ, ab=ab, satz=satz),)
    return (Zinsregel(typ, ab=ab),)


@st.composite
def _faelle(
    draw: st.DrawFn,
) -> tuple[Aktenparameter, list[Bestandteil], list[Zahlung], date]:
    arten = [
        Bestandteilart.HAUPTFORDERUNG,
        Bestandteilart.KOSTEN_VERFAHREN,
        Bestandteilart.KOSTEN_VORGERICHTLICH,
        Bestandteilart.ZINSEN,
    ]
    bestandteile: list[Bestandteil] = []
    for nummer in range(draw(st.integers(min_value=1, max_value=3))):
        art = draw(st.sampled_from(arten))
        regeln = () if art is Bestandteilart.ZINSEN else draw(_zinsregeln())
        bestandteile.append(
            Bestandteil(f"b{nummer}", art, draw(BETRAEGE), regeln, draw(st.none() | TAGE))
        )
    zahlungen = [Zahlung(draw(TAGE), draw(BETRAEGE)) for _ in range(draw(st.integers(0, 5)))]
    parameter = Aktenparameter(
        anrechnung=draw(st.sampled_from([Anrechnungsregel.BGB_367, Anrechnungsregel.BGB_497])),
        tageszaehlung=draw(st.sampled_from(list(Tageszaehlung))),
        zinsbeginn=draw(st.sampled_from(list(Zinsbeginn))),
        zahltag=draw(st.sampled_from(list(Zahltag))),
        teilung=draw(st.sampled_from(list(Teilung))),
        teilungstage=frozenset(draw(st.sets(TAGE, max_size=3))),
    )
    return parameter, bestandteile, zahlungen, draw(TAGE)


def _grenze(parameter: Aktenparameter, zahlung: Zahlung) -> date:
    if parameter.zahltag is Zahltag.ALTER_BETRAG:
        return zahlung.datum + EIN_TAG
    return zahlung.datum


Fall = tuple[Aktenparameter, list[Bestandteil], list[Zahlung], date]


def _rechne(fall: Fall) -> Ergebnis:
    parameter, bestandteile, zahlungen, stichtag = fall
    return berechne(parameter, bestandteile, zahlungen, stichtag, REIHE)


@given(_faelle())
def test_anrechnung_verteilt_genau_den_zahlbetrag(fall: Fall) -> None:
    _, _, zahlungen, stichtag = fall
    ergebnis = _rechne(fall)
    for zahlung in zahlungen:
        zeilen = [z for z in ergebnis.anrechnungen if z.zahlung is zahlung]
        if zahlung.datum > stichtag:
            assert zeilen == []
        else:
            assert sum(z.angerechnet for z in zeilen) == zahlung.betrag
            assert all(z.angerechnet > 0 for z in zeilen)


@given(_faelle())
def test_ueberzahlung_nur_ohne_restschuld(fall: Fall) -> None:
    ergebnis = _rechne(fall)
    assert ergebnis.ueberzahlung == sum(
        z.angerechnet for z in ergebnis.anrechnungen if z.gruppe is None
    )
    if ergebnis.ueberzahlung > 0:
        assert ergebnis.gesamt == 0
    assert min(ergebnis.hauptforderung, ergebnis.zinsen, ergebnis.kosten) >= 0


@given(_faelle())
def test_zinsen_werden_nicht_verzinst(fall: Fall) -> None:
    parameter, bestandteile, _, _ = fall
    ergebnis = _rechne(fall)
    for abschnitt in ergebnis.abschnitte:
        b = next(b for b in bestandteile if b.kennung == abschnitt.bestandteil)
        angerechnet = sum(
            (
                z.angerechnet
                for z in ergebnis.anrechnungen
                if z.bestandteil == b.kennung
                and z.gruppe is b.art.gruppe
                and _grenze(parameter, z.zahlung) <= abschnitt.von
            ),
            Decimal(0),
        )
        assert abschnitt.basis == b.betrag - angerechnet


@given(_faelle())
def test_nichts_geht_verloren(fall: Fall) -> None:
    _, bestandteile, _, _ = fall
    ergebnis = _rechne(fall)
    entstanden = sum(b.betrag for b in bestandteile) + sum(a.zins for a in ergebnis.abschnitte)
    angerechnet = sum(z.angerechnet for z in ergebnis.anrechnungen if z.gruppe is not None)
    assert entstanden == ergebnis.gesamt + angerechnet
