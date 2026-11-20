# SPDX-License-Identifier: AGPL-3.0-or-later
"""Format aller Golden Files (Fachkonzept Kap. 12), ohne Rechnen.

Die Prüfung wird zuerst an kaputten Kopien getestet. Ohne diese Selbsttests könnte eine
defekte Prüfung unbemerkt immer grün melden.
"""

import shutil
from pathlib import Path

import pytest

from tests.golden.faelle import FormatError, alle_faelle, kennungen, lies_fall

GK_0001 = Path(__file__).parent / "verbindlichkeiten" / "konstruiert" / "GK-0001.yaml"


def test_es_gibt_golden_files() -> None:
    assert GK_0001 in alle_faelle()


@pytest.mark.parametrize("pfad", alle_faelle(), ids=lambda p: p.stem)
def test_golden_file_hat_gueltiges_format(pfad: Path) -> None:
    lies_fall(pfad)


def test_kennungen_nummerieren_wiederholte_arten() -> None:
    arten = ["kosten_vollstreckung", "hauptforderung", "kosten_vollstreckung"]
    assert kennungen(arten) == [
        "kosten_vollstreckung",
        "hauptforderung",
        "kosten_vollstreckung_2",
    ]


# --- Selbsttests an Kopien von GK-0001 --------------------------------------------------------


def _kopie(tmp_path: Path) -> Path:
    ziel = tmp_path / "verbindlichkeiten" / "konstruiert"
    ziel.mkdir(parents=True)
    for datei in GK_0001.parent.glob("GK-0001*"):
        shutil.copy(datei, ziel / datei.name)
    return ziel / "GK-0001.yaml"


def _ersetze(datei: Path, alt: str, neu: str) -> None:
    text = datei.read_bytes().decode("utf-8")
    assert alt in text, f"{alt!r} fehlt in {datei.name}"
    datei.write_bytes(text.replace(alt, neu, 1).encode("utf-8"))


def test_kopie_ist_gueltig(tmp_path: Path) -> None:
    fall = lies_fall(_kopie(tmp_path))
    assert fall.kennungen == ["hauptforderung", "kosten_vorgerichtlich"]
    assert fall.rechenweg is not None
    assert len(fall.rechenweg.zeilen) == 6


YAML_FEHLER = [
    ("id: GK-0001", "id: GK-0002", "Dateiname"),
    ("id: GK-0001", "id: GR-0001", "GK-nnnn"),
    ("sorte: konstruiert", "sorte: real", "Ordner"),
    (
        "  berechnet_am: 2026-10-25\n",
        "  berechnet_am: 2026-10-25\n  freigegeben_von: X\n",
        "unbekannt",
    ),
    ("    - art: dezimalrechnung\n", "", "genau zwei"),
    ("art: dezimalrechnung", "art: tabellenkalkulation", "verschiedene"),
    ("quelle: berechnung", "quelle: rechentabelle", "berechnung"),
    ('betrag: "2400.00"', "betrag: 2400.00", "Betrag als Text"),
    ('betrag: "2400.00"', 'betrag: "2400"', "Betrag als Text"),
    ("ab: 2024-04-16", 'ab: "2024-04-16"', "Datum"),
    ("tageszaehlung: act_365", "tageszaehlung: act_366", "tageszaehlung"),
    ("toleranz: ", "abweichungen: []\ntoleranz: ", "nur bei realen"),
]


@pytest.mark.parametrize(("alt", "neu", "meldung"), YAML_FEHLER)
def test_erkennt_fehler_in_der_yaml_datei(tmp_path: Path, alt: str, neu: str, meldung: str) -> None:
    pfad = _kopie(tmp_path)
    _ersetze(pfad, alt, neu)
    with pytest.raises(FormatError, match=meldung):
        lies_fall(pfad)


RECHENWEG = "GK-0001.rechenweg.csv"
ANRECHNUNG = "GK-0001.anrechnung.csv"

CSV_FEHLER = [
    (RECHENWEG, "\n", "\r\n", "LF"),
    (RECHENWEG, "bestandteil,von", "﻿bestandteil,von", "BOM"),
    (RECHENWEG, "zins_gerundet\n", "zins\n", "Kopfzeile"),
    (RECHENWEG, ",zahlung,102,", ",zahlung+halbjahr,102,", "Reihenfolge"),
    (RECHENWEG, ",zahlung,102,", ",zinsbeginn+zahlung,102,", "zinsbeginn allein"),
    (RECHENWEG, ",43.076383,", ",43.07638,", "zins_ungerundet"),
    (RECHENWEG, ",43.08\n", ",43.1\n", "zins_gerundet"),
    (RECHENWEG, "hauptforderung,2024-07-01", "hauptforderung,2024-02-30", "kein gültiges Datum"),
    (RECHENWEG, "hauptforderung,2024-07-01", "kosten_vorgerichtlich,2024-07-01", "Reihenfolge"),
    (RECHENWEG, "hauptforderung,2024-07-01", "hauptforderung_2,2024-07-01", "Kennung"),
    (ANRECHNUNG, "2024-09-20,200.00,kosten", "2024-09-21,200.00,kosten", "zahlungen"),
    (ANRECHNUNG, ",kosten,159.40", ",gebuehren,159.40", "gruppe"),
    (ANRECHNUNG, ",661.35,1738.65\n", ",661.35\n", "Spalten"),
]


@pytest.mark.parametrize(("datei", "alt", "neu", "meldung"), CSV_FEHLER)
def test_erkennt_fehler_in_den_csv_dateien(
    tmp_path: Path, datei: str, alt: str, neu: str, meldung: str
) -> None:
    pfad = _kopie(tmp_path)
    _ersetze(pfad.parent / datei, alt, neu)
    with pytest.raises(FormatError, match=meldung):
        lies_fall(pfad)


def test_konstruierter_fall_mit_zahlungen_braucht_die_anrechnung(tmp_path: Path) -> None:
    pfad = _kopie(tmp_path)
    _ersetze(pfad, "  anrechnung: GK-0001.anrechnung.csv\n", "")
    (pfad.parent / ANRECHNUNG).unlink()
    with pytest.raises(FormatError, match="anrechnung ist"):
        lies_fall(pfad)


def test_erkennt_csv_ohne_eintrag_unter_dateien(tmp_path: Path) -> None:
    pfad = _kopie(tmp_path)
    shutil.copy(pfad.parent / RECHENWEG, pfad.parent / "GK-0001.notizen.csv")
    with pytest.raises(FormatError, match="nicht unter dateien"):
        lies_fall(pfad)


# --- Selbsttests für reale Fälle und den Block abweichungen -----------------------------------

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
erwartung:
  stichtag: 2025-05-20
  hauptforderung: "1000.00"
  zinsen: "9.18"
  kosten: "0.00"
  gesamt: "1009.18"
toleranz: "0.00"
abweichungen:
  - ort:
      feld: erwartung.zinsen
    laut_aufstellung: "9.20"
    erwartet: "9.18"
    grund: Tage falsch gezählt
  - ort:
      datei: GR-0001.rechenweg.csv
      zeile: 2
      spalte: zins_gerundet
    laut_aufstellung: "9.20"
    erwartet: "9.18"
    grund: Tage falsch gezählt
"""

GR_RECHENWEG = (
    "bestandteil,von,bis,grund,tage,tagesbasis,basis,basiszins,satz,zins_ungerundet,zins_gerundet\n"
    "hauptforderung,2025-03-15,2025-05-20,zinsbeginn,67,365,1000.00,,5,9.178082,9.18\n"
)


def _realer_fall(tmp_path: Path, yaml_text: str = GR_YAML) -> Path:
    ziel = tmp_path / "verbindlichkeiten" / "real"
    ziel.mkdir(parents=True)
    (ziel / "GR-0001.rechenweg.csv").write_bytes(GR_RECHENWEG.encode("utf-8"))
    pfad = ziel / "GR-0001.yaml"
    pfad.write_bytes(yaml_text.encode("utf-8"))
    return pfad


def test_realer_fall_mit_abweichungen_ist_gueltig(tmp_path: Path) -> None:
    assert lies_fall(_realer_fall(tmp_path)).sorte == "real"


@pytest.mark.parametrize(
    ("alt", "neu", "meldung"),
    [
        (
            '    erwartet: "9.18"\n    grund: Tage falsch gezählt\n  - ort:',
            '    erwartet: "9.19"\n    grund: Tage falsch gezählt\n  - ort:',
            "erwartete Wert",
        ),
        ("      zeile: 2", "      zeile: 3", "Zeile gibt es nicht"),
        ("      feld: erwartung.zinsen", "      feld: erwartung.zins", "gibt es nicht"),
        ("quelle: aufstellung", "quelle: berechnung", "aufstellung"),
        ('  freigegeben_von: "Test"\n', "", "freigegeben_von"),
    ],
)
def test_erkennt_fehler_in_realen_faellen(tmp_path: Path, alt: str, neu: str, meldung: str) -> None:
    assert alt in GR_YAML
    with pytest.raises(FormatError, match=meldung):
        lies_fall(_realer_fall(tmp_path, GR_YAML.replace(alt, neu, 1)))
