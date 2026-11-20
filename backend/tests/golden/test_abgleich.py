# SPDX-License-Identifier: AGPL-3.0-or-later
"""Abgleich der Golden Files mit ihrer Aufstellung (Fachkonzept Kap. 12 und 5.3).

Der Abgleich meldet bei jedem Fall genau die Abweichungen aus dem Block ``abweichungen``: bei
konstruierten Fällen keine, bei realen genau deren Orte mit dem Wert laut Aufstellung.
"""

from pathlib import Path

import pytest

from app.kern.stammdaten import lade_basiszinsreihe
from app.module.verbindlichkeiten.abgleich import gleiche_ab
from tests.golden.abgleich_fall import aufstellung, gemeldet
from tests.golden.faelle import (
    Fall,
    FormatError,
    Ort,
    abweichungen,
    alle_faelle,
    eingaben,
    lies_fall,
)


def _gemeldet(fall: Fall) -> dict[Ort, str | None]:
    e = eingaben(fall)
    a = aufstellung(fall)
    ergebnis = gleiche_ab(e.parameter, e.bestandteile, e.zahlungen, a, lade_basiszinsreihe())
    return dict(gemeldet(fall, a, ergebnis))


@pytest.mark.parametrize("pfad", alle_faelle(), ids=lambda p: p.stem)
def test_abgleich_meldet_genau_die_abweichungen(pfad: Path) -> None:
    fall = lies_fall(pfad)
    assert _gemeldet(fall) == dict(abweichungen(fall))


# --- Selbsttest mit einem ausgedachten realen Fall ---------------------------------------------

GR_YAML = """\
id: GR-0001
sorte: real
erwartungswerte:
  quelle: aufstellung
  stand: 2026-09-30
  freigegeben_von: "Test"
  freigegeben_am: 2026-10-01
dateien:
  rechenweg: GR-0001.rechenweg.csv
akte:
  titelart: vollstreckungsbescheid
  verbraucherdarlehen: false
  anrechnung: bgb_367
  tageszaehlung: act_365
  zinsbeginn: genannter_tag
  zahltag: alter_betrag
  teilung: kalender
  teilungstage: []
bestandteile:
  - art: hauptforderung
    betrag: "1000.00"
    zinsregel:
      typ: fest
      ab: 2025-03-15
      satz: "5"
  - art: kosten_verfahren
    betrag: "50.00"
    zinsregel:
      typ: keine
erwartung:
  stichtag: 2025-05-20
  hauptforderung: "1000.00"
  zinsen: "9.18"
  kosten: "50.00"
  gesamt: "1059.18"
toleranz: "0.00"
abweichungen:
  - ort:
      datei: GR-0001.rechenweg.csv
      zeile: 2
      spalte: zins_gerundet
    laut_aufstellung: "9.20"
    erwartet: "9.18"
    grund: Rundung falsch
  - ort:
      feld: erwartung.zinsen
    laut_aufstellung: "9.20"
    erwartet: "9.18"
    grund: Folgewert der Rundung
  - ort:
      feld: bestandteile.2.betrag
    laut_aufstellung: "55.00"
    erwartet: "50.00"
    grund: Kosten zu hoch angesetzt
  - ort:
      feld: erwartung.kosten
    laut_aufstellung: "55.00"
    erwartet: "50.00"
    grund: Folgewert der Kosten
  - ort:
      feld: erwartung.gesamt
    laut_aufstellung: "1064.20"
    erwartet: "1059.18"
    grund: Folgewert
"""

GR_RECHENWEG = (
    "bestandteil,von,bis,grund,tage,tagesbasis,basis,basiszins,satz,zins_ungerundet,zins_gerundet\n"
    "hauptforderung,2025-03-15,2025-05-20,zinsbeginn,67,365,1000.00,,5,,9.18\n"
)


def _realer_fall(tmp_path: Path, yaml_text: str = GR_YAML) -> Path:
    ziel = tmp_path / "verbindlichkeiten" / "real"
    ziel.mkdir(parents=True)
    (ziel / "GR-0001.rechenweg.csv").write_bytes(GR_RECHENWEG.encode("utf-8"))
    pfad = ziel / "GR-0001.yaml"
    pfad.write_bytes(yaml_text.encode("utf-8"))
    return pfad


def test_realer_fall_meldet_genau_seine_abweichungen(tmp_path: Path) -> None:
    fall = lies_fall(_realer_fall(tmp_path))
    erwartet = {
        ("datei", "GR-0001.rechenweg.csv", 2, "zins_gerundet"): "9.20",
        ("feld", "erwartung.zinsen"): "9.20",
        ("feld", "bestandteile.2.betrag"): "55.00",
        ("feld", "erwartung.kosten"): "55.00",
        ("feld", "erwartung.gesamt"): "1064.20",
    }
    assert dict(abweichungen(fall)) == erwartet
    assert _gemeldet(fall) == erwartet


def test_leerer_wert_der_aufstellung_wird_nicht_verglichen(tmp_path: Path) -> None:
    """zins_ungerundet ist im realen Fall leer: Die Aufstellung nennt ihn nicht."""
    fall = lies_fall(_realer_fall(tmp_path))
    assert ("datei", "GR-0001.rechenweg.csv", 2, "zins_ungerundet") not in _gemeldet(fall)


@pytest.mark.parametrize(
    ("alt", "neu", "meldung"),
    [
        ("      feld: erwartung.gesamt", "      feld: akte.tageszaehlung", "keine Position"),
        (
            "      feld: bestandteile.2.betrag",
            "      feld: bestandteile.1.betrag",
            "keine Position",
        ),
        ("      feld: erwartung.kosten", "      feld: bestandteile.2.betrag", "schon"),
        ('    laut_aufstellung: "1064.20"', '    laut_aufstellung: "1059.18"', "gleich"),
    ],
)
def test_format_lehnt_orte_ausserhalb_des_abgleichs_ab(
    tmp_path: Path, alt: str, neu: str, meldung: str
) -> None:
    assert alt in GR_YAML
    with pytest.raises(FormatError, match=meldung):
        lies_fall(_realer_fall(tmp_path, GR_YAML.replace(alt, neu, 1)))
