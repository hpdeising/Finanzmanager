# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prüfung der Datei ``stammdaten/feiertage.yaml`` (Fachkonzept Kap. 5.4 und 7).

Die Werte stammen aus der Datei, erzeugt mit python-holidays; hier wird nur geprüft, dass sie
vollständig und stimmig ist, nicht nachgerechnet.
"""

from datetime import date

import pytest

from app.kern.stammdaten import LAENDER, lade_feiertagskalender

JAHRE = range(2000, 2081)


def test_zeitraum_2000_bis_2080() -> None:
    kalender = lade_feiertagskalender()
    assert (kalender.gueltig_ab, kalender.gueltig_bis) == (date(2000, 1, 1), date(2080, 12, 31))
    assert "python-holidays" in kalender.quelle
    assert kalender.geprueft_von


@pytest.mark.parametrize(("monat", "tag"), [(1, 1), (5, 1), (10, 3), (12, 25), (12, 26)])
def test_bundesweite_feste_tage_in_jedem_jahr(monat: int, tag: int) -> None:
    kalender = lade_feiertagskalender()
    for jahr in JAHRE:
        for land in LAENDER:
            assert kalender.ist_feiertag(date(jahr, monat, tag), land)


def test_jedes_land_hat_in_jedem_jahr_mindestens_neun_feiertage() -> None:
    """Bundesweit gelten in jedem Jahr neun Feiertage (Neujahr bis zweiter Weihnachtstag).

    Gezählt werden Feiertage, nicht Tage: Fallen zwei auf einen Tag (2008 Christi Himmelfahrt und
    1. Mai), stehen beide Namen, mit „; “ getrennt, an einem Eintrag.
    """
    kalender = lade_feiertagskalender()
    for land in LAENDER:
        for jahr in JAHRE:
            anzahl = sum(
                len(f.name.split("; "))
                for f in kalender.feiertage
                if f.datum.year == jahr and land in f.laender
            )
            assert anzahl >= 9, (land, jahr)


def test_regionale_feiertage_aus_der_entscheidung() -> None:
    """Augsburger Friedensfest und Mariä Himmelfahrt (BY), Fronleichnam (SN, TH) gelten nur in
    Teilen des Landes und zählen nicht als Feiertag des Landes."""
    kalender = lade_feiertagskalender()
    namen = {(f.name, land) for f in kalender.regionale_feiertage for land in f.laender}
    assert {
        ("Augsburger Hohes Friedensfest", "BY"),
        ("Mariä Himmelfahrt", "BY"),
        ("Fronleichnam", "SN"),
        ("Fronleichnam", "TH"),
    } <= namen
    for f in kalender.regionale_feiertage:
        for land in f.laender:
            assert not kalender.ist_feiertag(f.datum, land)
