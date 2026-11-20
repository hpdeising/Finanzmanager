# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests der Eingaben für Zinsen und Anrechnung (Fachkonzept Kap. 4.5, 5.1 bis 5.3)."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Anrechnungsregel,
    Bestandteil,
    Bestandteilart,
    EingabeUngueltigError,
    Gruppe,
    Zahlung,
    Zinsregel,
    Zinsregeltyp,
)

T = date
EINS = Decimal("1.00")


@pytest.mark.parametrize(
    ("art", "gruppe"),
    [
        (Bestandteilart.HAUPTFORDERUNG, Gruppe.HAUPTFORDERUNG),
        (Bestandteilart.ZINSEN, Gruppe.ZINSEN),
        (Bestandteilart.KOSTEN_VORGERICHTLICH, Gruppe.KOSTEN),
        (Bestandteilart.KOSTEN_VERFAHREN, Gruppe.KOSTEN),
        (Bestandteilart.KOSTEN_VOLLSTRECKUNG, Gruppe.KOSTEN),
    ],
)
def test_gruppe_der_bestandteilart(art: Bestandteilart, gruppe: Gruppe) -> None:
    assert art.gruppe is gruppe


@pytest.mark.parametrize(
    "erzeuge",
    [
        pytest.param(lambda: Zinsregel(Zinsregeltyp.GESETZLICH_288_1), id="ohne ab"),
        pytest.param(lambda: Zinsregel(Zinsregeltyp.FEST, ab=T(2025, 1, 1)), id="fest ohne Satz"),
        pytest.param(
            lambda: Zinsregel(Zinsregeltyp.BASISZINS_PLUS, ab=T(2025, 1, 1)),
            id="basiszins_plus ohne Aufschlag",
        ),
        pytest.param(
            lambda: Zinsregel(Zinsregeltyp.GESETZLICH_288_1, ab=T(2025, 1, 1), satz=EINS),
            id="gesetzlich mit Satz",
        ),
        pytest.param(
            lambda: Zinsregel(Zinsregeltyp.KEINE, ab=T(2025, 1, 1), aufschlag=EINS),
            id="keine mit Aufschlag",
        ),
        pytest.param(lambda: Zinsregel(Zinsregeltyp.KEINE, bis=T(2025, 1, 1)), id="keine mit bis"),
        pytest.param(
            lambda: Zinsregel(Zinsregeltyp.FEST, ab=T(2025, 2, 1), bis=T(2025, 1, 31), satz=EINS),
            id="bis vor ab",
        ),
    ],
)
def test_zinsregel_prueft_ihre_felder(erzeuge: Callable[[], object]) -> None:
    with pytest.raises(EingabeUngueltigError):
        erzeuge()


def _hf(*regeln: Zinsregel, betrag: Decimal = Decimal(100)) -> Bestandteil:
    return Bestandteil("hauptforderung", Bestandteilart.HAUPTFORDERUNG, betrag, regeln)


def test_bestandteil_sortiert_zinsregeln_nach_beginn() -> None:
    spaeter = Zinsregel(Zinsregeltyp.FEST, ab=T(2025, 6, 1), satz=EINS)
    frueher = Zinsregel(Zinsregeltyp.FEST, ab=T(2025, 1, 1), bis=T(2025, 3, 31), satz=EINS)
    assert _hf(spaeter, frueher).zinsregeln == (frueher, spaeter)


@pytest.mark.parametrize(
    "regeln",
    [
        pytest.param(
            (
                Zinsregel(Zinsregeltyp.FEST, ab=T(2025, 1, 1), bis=T(2025, 6, 1), satz=EINS),
                Zinsregel(Zinsregeltyp.FEST, ab=T(2025, 6, 1), satz=EINS),
            ),
            id="überlappend",
        ),
        pytest.param(
            (
                Zinsregel(Zinsregeltyp.FEST, ab=T(2025, 1, 1), satz=EINS),
                Zinsregel(Zinsregeltyp.FEST, ab=T(2025, 1, 1), satz=EINS),
            ),
            id="gleicher Beginn",
        ),
        pytest.param(
            (Zinsregel(Zinsregeltyp.KEINE), Zinsregel(Zinsregeltyp.KEINE)),
            id="zweimal keine ohne ab",
        ),
    ],
)
def test_bestandteil_lehnt_ueberlappende_zinsregeln_ab(regeln: tuple[Zinsregel, ...]) -> None:
    with pytest.raises(EingabeUngueltigError):
        _hf(*regeln)


def test_zinsen_als_bestandteil_sind_nie_verzinslich() -> None:
    """§ 289 S. 1 BGB: keine Zinsen auf Zinsen (Kap. 5.2 Schritt 5)."""
    with pytest.raises(EingabeUngueltigError, match="289"):
        Bestandteil(
            "zinsen",
            Bestandteilart.ZINSEN,
            EINS,
            (Zinsregel(Zinsregeltyp.FEST, ab=T(2025, 1, 1), satz=EINS),),
        )


@pytest.mark.parametrize("betrag", [Decimal(0), Decimal("-1.00")])
def test_bestandteil_und_zahlung_brauchen_positive_betraege(betrag: Decimal) -> None:
    with pytest.raises(EingabeUngueltigError):
        _hf(betrag=betrag)
    with pytest.raises(EingabeUngueltigError):
        Zahlung(T(2025, 1, 1), betrag)


def test_aktenparameter_voreinstellungen_wie_fachkonzept() -> None:
    parameter = Aktenparameter()
    assert parameter.anrechnung.value == "bgb_367"
    assert parameter.tageszaehlung.value == "act_365"
    assert parameter.zinsbeginn.value == "genannter_tag"
    assert parameter.zahltag.value == "alter_betrag"
    assert parameter.teilung.value == "kalender"
    assert parameter.teilungstage == frozenset()


def test_individuelle_anrechnung_braucht_eine_vollstaendige_reihenfolge() -> None:
    with pytest.raises(EingabeUngueltigError):
        Aktenparameter(anrechnung=Anrechnungsregel.INDIVIDUELL)
    with pytest.raises(EingabeUngueltigError):
        Aktenparameter(
            anrechnung=Anrechnungsregel.INDIVIDUELL,
            reihenfolge=(Gruppe.ZINSEN, Gruppe.KOSTEN),
        )
    parameter = Aktenparameter(
        anrechnung=Anrechnungsregel.INDIVIDUELL,
        reihenfolge=(Gruppe.HAUPTFORDERUNG, Gruppe.ZINSEN, Gruppe.KOSTEN),
    )
    assert parameter.gruppenfolge == (Gruppe.HAUPTFORDERUNG, Gruppe.ZINSEN, Gruppe.KOSTEN)


def test_reihenfolge_nur_bei_individueller_anrechnung() -> None:
    with pytest.raises(EingabeUngueltigError):
        Aktenparameter(reihenfolge=(Gruppe.HAUPTFORDERUNG, Gruppe.ZINSEN, Gruppe.KOSTEN))


@pytest.mark.parametrize(
    ("regel", "folge"),
    [
        # § 367 Abs. 1 BGB: Kosten → Zinsen → Hauptforderung.
        (Anrechnungsregel.BGB_367, (Gruppe.KOSTEN, Gruppe.ZINSEN, Gruppe.HAUPTFORDERUNG)),
        # § 497 Abs. 3 BGB: Kosten der Rechtsverfolgung → Hauptforderung → Zinsen.
        (Anrechnungsregel.BGB_497, (Gruppe.KOSTEN, Gruppe.HAUPTFORDERUNG, Gruppe.ZINSEN)),
    ],
)
def test_gruppenfolge_der_gesetzlichen_regeln(
    regel: Anrechnungsregel, folge: tuple[Gruppe, ...]
) -> None:
    assert Aktenparameter(anrechnung=regel).gruppenfolge == folge
