# SPDX-License-Identifier: AGPL-3.0-or-later
"""Golden Files einlesen und ihr Format prüfen (Fachkonzept Kap. 12, CLAUDE.md).

``lies_fall`` liest eine YAML-Datei mit ihren CSV-Dateien und prüft alles, was Kap. 12 über
das Format sagt. Es rechnet nichts nach: Erwartungswerte stammen nie aus dem Programm.
"""

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import yaml

from app.kern.geld import betrag
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

GOLDEN = Path(__file__).resolve().parent
SORTEN = {"real": "GR", "konstruiert": "GK"}

ANRECHNUNGSREGELN = {"bgb_367", "bgb_497", "individuell"}
TAGESZAEHLUNGEN = {"act_365", "act_act", "act_360", "30_360"}
ZINSBEGINNE = {"genannter_tag", "folgetag"}
ZAHLTAGE = {"alter_betrag", "verminderter_betrag"}
TEILUNGEN = {"kalender", "satzwechsel"}
BESTANDTEILARTEN = {
    "hauptforderung",
    "zinsen",
    "kosten_vorgerichtlich",
    "kosten_verfahren",
    "kosten_vollstreckung",
}
ZINSREGELTYPEN = {
    "gesetzlich_288_1",
    "gesetzlich_288_2",
    "kostenfestsetzung",
    "basiszins_plus",
    "fest",
    "keine",
}
# Gründe in der Reihenfolge aus Kap. 12; zinsbeginn steht immer allein.
GRUENDE = ("halbjahr", "jahreswechsel", "teilungstag", "zahlung", "regelwechsel")
GRUPPEN = {"kosten", "zinsen", "hauptforderung", "ueberzahlung"}

KOPF_RECHENWEG = [
    "bestandteil",
    "von",
    "bis",
    "grund",
    "tage",
    "tagesbasis",
    "basis",
    "basiszins",
    "satz",
    "zins_ungerundet",
    "zins_gerundet",
]
KOPF_ANRECHNUNG = ["zahlung", "betrag", "bestandteil", "gruppe", "angerechnet", "offen_danach"]

_BETRAG = re.compile(r"-?[0-9]+\.[0-9]{2}")
_UNGERUNDET = re.compile(r"-?[0-9]+\.[0-9]{6,}")
_SATZ = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
_GANZ = re.compile(r"[0-9]+")
_DATUM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class FormatError(Exception):
    """Ein Golden File verletzt das Format aus Fachkonzept Kap. 12."""


@dataclass(frozen=True)
class Csv:
    """Eine CSV-Datei: Name und Datenzeilen. Zeile ``i`` der Liste ist Editorzeile ``i + 2``."""

    name: str
    zeilen: list[dict[str, str]]


@dataclass(frozen=True)
class Fall:
    """Ein Golden File mit seinen CSV-Dateien."""

    pfad: Path
    id: str
    sorte: str
    daten: dict[str, object]
    kennungen: list[str]
    rechenweg: Csv | None
    anrechnung: Csv | None


def alle_faelle() -> list[Path]:
    """Alle YAML-Dateien unter ``tests/golden/<modul>/<sorte>/``."""
    return sorted(GOLDEN.glob("*/*/*.yaml"))


def kennungen(arten: list[str]) -> list[str]:
    """Kennungen der Bestandteile für die CSV-Dateien (Kap. 12, Spalte ``bestandteil``).

    Das erste Vorkommen einer Art trägt keine Nummer, jedes weitere eine laufende Nummer in der
    Reihenfolge der YAML-Datei: ``kosten_vollstreckung``, ``kosten_vollstreckung_2``.
    """
    gezaehlt: dict[str, int] = {}
    ergebnis: list[str] = []
    for art in arten:
        gezaehlt[art] = gezaehlt.get(art, 0) + 1
        ergebnis.append(art if gezaehlt[art] == 1 else f"{art}_{gezaehlt[art]}")
    return ergebnis


def lies_fall(pfad: Path) -> Fall:
    """Golden File lesen und sein Format prüfen.

    Raises:
        FormatError: mit Datei und Ort des ersten Verstoßes.
    """
    try:
        roh: object = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as fehler:
        raise FormatError(f"{pfad.name}: nicht lesbar: {fehler}") from None
    ort = pfad.name
    daten = _zuordnung(
        roh,
        ort,
        pflicht={
            "id",
            "sorte",
            "erwartungswerte",
            "akte",
            "bestandteile",
            "erwartung",
            "toleranz",
        },
        erlaubt={"beschreibung", "dateien", "zahlungen", "abweichungen"},
    )
    fall_id = _text(daten["id"], f"{ort}, id")
    sorte = _text(daten["sorte"], f"{ort}, sorte")
    if sorte not in SORTEN:
        raise FormatError(f"{ort}, sorte: real oder konstruiert erwartet.")
    if pfad.parent.name != sorte:
        raise FormatError(f"{ort}: liegt im Ordner {pfad.parent.name}/, sorte ist {sorte}.")
    if not re.fullmatch(rf"{SORTEN[sorte]}-[0-9]{{4}}", fall_id):
        raise FormatError(f"{ort}, id: {SORTEN[sorte]}-nnnn erwartet.")
    if pfad.stem != fall_id:
        raise FormatError(f"{ort}: Dateiname muss der id entsprechen.")
    if "beschreibung" in daten:
        _text(daten["beschreibung"], f"{ort}, beschreibung")

    _pruefe_erwartungswerte(daten["erwartungswerte"], sorte, f"{ort}, erwartungswerte")
    _pruefe_akte(daten["akte"], f"{ort}, akte")
    arten = _pruefe_bestandteile(daten["bestandteile"], f"{ort}, bestandteile")
    zahlungen = _pruefe_zahlungen(daten.get("zahlungen", []), f"{ort}, zahlungen")
    _pruefe_erwartung(daten["erwartung"], f"{ort}, erwartung")
    _betrag(daten["toleranz"], f"{ort}, toleranz")

    namen = _pruefe_dateien(daten.get("dateien"), pfad, fall_id, sorte, bool(zahlungen), ort)
    kennung = kennungen(arten)
    rechenweg = anrechnung = None
    if "rechenweg" in namen:
        rechenweg = _lies_csv(pfad.parent / namen["rechenweg"], KOPF_RECHENWEG)
        _pruefe_rechenweg(rechenweg, kennung)
    if "anrechnung" in namen:
        anrechnung = _lies_csv(pfad.parent / namen["anrechnung"], KOPF_ANRECHNUNG)
        _pruefe_anrechnung(anrechnung, kennung, zahlungen)
    fall = Fall(pfad, fall_id, sorte, daten, kennung, rechenweg, anrechnung)

    if "abweichungen" in daten:
        if sorte != "real":
            raise FormatError(f"{ort}, abweichungen: nur bei realen Fällen.")
        _pruefe_abweichungen(daten["abweichungen"], fall, f"{ort}, abweichungen")
    return fall


# --- YAML ----------------------------------------------------------------------------------


def _pruefe_erwartungswerte(wert: object, sorte: str, ort: str) -> None:
    if sorte == "real":
        felder = _zuordnung(
            wert, ort, pflicht={"quelle", "stand", "freigegeben_von", "freigegeben_am"}
        )
        if felder["quelle"] != "aufstellung":
            raise FormatError(f"{ort}, quelle: bei realen Fällen aufstellung.")
        _datum(felder["stand"], f"{ort}, stand")
        _text(felder["freigegeben_von"], f"{ort}, freigegeben_von")
        _datum(felder["freigegeben_am"], f"{ort}, freigegeben_am")
        return
    felder = _zuordnung(wert, ort, pflicht={"quelle", "berechnet_am", "verfahren"})
    if felder["quelle"] != "berechnung":
        raise FormatError(f"{ort}, quelle: bei konstruierten Fällen berechnung.")
    _datum(felder["berechnet_am"], f"{ort}, berechnet_am")
    verfahren = _liste(felder["verfahren"], f"{ort}, verfahren")
    if len(verfahren) != 2:
        raise FormatError(f"{ort}, verfahren: genau zwei Rechenwege erwartet.")
    arten: set[str] = set()
    for nummer, eintrag in enumerate(verfahren, 1):
        e = _zuordnung(eintrag, f"{ort}, verfahren {nummer}", pflicht={"art"}, erlaubt={"beleg"})
        arten.add(_text(e["art"], f"{ort}, verfahren {nummer}, art"))
        if "beleg" in e:
            _text(e["beleg"], f"{ort}, verfahren {nummer}, beleg")
    if len(arten) != 2:
        raise FormatError(f"{ort}, verfahren: die beiden Rechenwege brauchen verschiedene art.")


def _pruefe_akte(wert: object, ort: str) -> None:
    felder = _zuordnung(
        wert,
        ort,
        pflicht={
            "titelart",
            "verbraucherdarlehen",
            "anrechnung",
            "tageszaehlung",
            "zinsbeginn",
            "zahltag",
            "teilung",
            "teilungstage",
        },
    )
    _text(felder["titelart"], f"{ort}, titelart")
    if not isinstance(felder["verbraucherdarlehen"], bool):
        raise FormatError(f"{ort}, verbraucherdarlehen: true oder false erwartet.")
    for feld, werte in (
        ("anrechnung", ANRECHNUNGSREGELN),
        ("tageszaehlung", TAGESZAEHLUNGEN),
        ("zinsbeginn", ZINSBEGINNE),
        ("zahltag", ZAHLTAGE),
        ("teilung", TEILUNGEN),
    ):
        _wahl(felder[feld], werte, f"{ort}, {feld}")
    tage = felder["teilungstage"]
    if not isinstance(tage, list):
        raise FormatError(f"{ort}, teilungstage: Liste erwartet.")
    for nummer, tag in enumerate(cast("list[object]", tage), 1):
        _datum(tag, f"{ort}, teilungstage {nummer}")


def _pruefe_bestandteile(wert: object, ort: str) -> list[str]:
    arten: list[str] = []
    for nummer, eintrag in enumerate(_liste(wert, ort), 1):
        o = f"{ort} {nummer}"
        felder = _zuordnung(
            eintrag, o, pflicht={"art", "betrag", "zinsregel"}, erlaubt={"entstanden_am"}
        )
        arten.append(_wahl(felder["art"], BESTANDTEILARTEN, f"{o}, art"))
        _betrag(felder["betrag"], f"{o}, betrag")
        if "entstanden_am" in felder:
            _datum(felder["entstanden_am"], f"{o}, entstanden_am")
        regel = _zuordnung(
            felder["zinsregel"],
            f"{o}, zinsregel",
            pflicht={"typ"},
            erlaubt={"ab", "bis", "aufschlag", "satz"},
        )
        _wahl(regel["typ"], ZINSREGELTYPEN, f"{o}, zinsregel, typ")
        for feld in ("ab", "bis"):
            if feld in regel:
                _datum(regel[feld], f"{o}, zinsregel, {feld}")
        for feld in ("aufschlag", "satz"):
            if feld in regel:
                _satz(regel[feld], f"{o}, zinsregel, {feld}")
    return arten


def _pruefe_zahlungen(wert: object, ort: str) -> list[tuple[date, str]]:
    if wert == []:
        return []
    zahlungen: list[tuple[date, str]] = []
    for nummer, eintrag in enumerate(_liste(wert, ort), 1):
        felder = _zuordnung(eintrag, f"{ort} {nummer}", pflicht={"datum", "betrag"})
        zahlungen.append(
            (
                _datum(felder["datum"], f"{ort} {nummer}, datum"),
                _betrag(felder["betrag"], f"{ort} {nummer}, betrag"),
            )
        )
    return zahlungen


def _pruefe_erwartung(wert: object, ort: str) -> None:
    felder = _zuordnung(
        wert, ort, pflicht={"stichtag", "hauptforderung", "zinsen", "kosten", "gesamt"}
    )
    _datum(felder["stichtag"], f"{ort}, stichtag")
    for feld in ("hauptforderung", "zinsen", "kosten", "gesamt"):
        _betrag(felder[feld], f"{ort}, {feld}")


def _pruefe_dateien(
    wert: object, pfad: Path, fall_id: str, sorte: str, hat_zahlungen: bool, ort: str
) -> dict[str, str]:
    namen: dict[str, str] = {}
    if wert is not None:
        felder = _zuordnung(
            wert, f"{ort}, dateien", pflicht=set(), erlaubt={"rechenweg", "anrechnung"}
        )
        for art, name in felder.items():
            if name != f"{fall_id}.{art}.csv":
                raise FormatError(f"{ort}, dateien, {art}: {fall_id}.{art}.csv erwartet.")
            if not (pfad.parent / f"{fall_id}.{art}.csv").is_file():
                raise FormatError(f"{ort}, dateien, {art}: Datei fehlt.")
            namen[art] = f"{fall_id}.{art}.csv"
    for datei in pfad.parent.glob(f"{fall_id}.*.csv"):
        if datei.name not in namen.values():
            raise FormatError(f"{ort}: {datei.name} liegt daneben, steht aber nicht unter dateien.")
    if sorte == "konstruiert":
        if "rechenweg" not in namen:
            raise FormatError(f"{ort}, dateien: rechenweg ist bei konstruierten Fällen Pflicht.")
        if hat_zahlungen and "anrechnung" not in namen:
            raise FormatError(
                f"{ort}, dateien: anrechnung ist bei konstruierten Fällen mit Zahlungen Pflicht."
            )
    return namen


def _pruefe_abweichungen(wert: object, fall: Fall, ort: str) -> None:
    """Am Ort jeder Abweichung steht der erwartete Wert (Kap. 12)."""
    for nummer, eintrag in enumerate(_liste(wert, ort), 1):
        o = f"{ort} {nummer}"
        felder = _zuordnung(eintrag, o, pflicht={"ort", "laut_aufstellung", "erwartet", "grund"})
        _text(felder["laut_aufstellung"], f"{o}, laut_aufstellung")
        erwartet = _text(felder["erwartet"], f"{o}, erwartet")
        _text(felder["grund"], f"{o}, grund")
        stelle = _zuordnung(
            felder["ort"], f"{o}, ort", pflicht=set(), erlaubt={"feld", "datei", "zeile", "spalte"}
        )
        if set(stelle) == {"feld"}:
            istwert = _feldwert(fall.daten, _text(stelle["feld"], f"{o}, ort, feld"), o)
        elif set(stelle) == {"datei", "zeile", "spalte"}:
            istwert = _csvwert(fall, stelle, o)
        else:
            raise FormatError(f"{o}, ort: feld oder datei, zeile und spalte erwartet.")
        if istwert != erwartet:
            raise FormatError(f"{o}: am Ort steht nicht der erwartete Wert.")


def _feldwert(daten: dict[str, object], pfad: str, ort: str) -> str:
    wert: object = daten
    for teil in pfad.split("."):
        if not isinstance(wert, dict) or teil not in wert:
            raise FormatError(f"{ort}, ort: Feld {pfad} gibt es nicht.")
        wert = cast("dict[object, object]", wert)[teil]
    if not isinstance(wert, str):
        raise FormatError(f"{ort}, ort: Feld {pfad} ist kein Text.")
    return wert


def _csvwert(fall: Fall, stelle: dict[str, object], ort: str) -> str:
    dateien = {c.name: c for c in (fall.rechenweg, fall.anrechnung) if c is not None}
    datei = dateien.get(str(stelle["datei"]))
    zeile = stelle["zeile"]
    if datei is None or not isinstance(zeile, int) or not 2 <= zeile <= len(datei.zeilen) + 1:
        raise FormatError(f"{ort}, ort: Datei oder Zeile gibt es nicht.")
    werte = datei.zeilen[zeile - 2]
    spalte = str(stelle["spalte"])
    if spalte not in werte:
        raise FormatError(f"{ort}, ort: Spalte gibt es nicht.")
    return werte[spalte]


# --- CSV -----------------------------------------------------------------------------------


def _lies_csv(pfad: Path, kopf: list[str]) -> Csv:
    """UTF-8 ohne BOM, LF, Komma, eine Kopfzeile, Anführungszeichen nach RFC 4180 (Kap. 12)."""
    roh = pfad.read_bytes()
    if roh.startswith(b"\xef\xbb\xbf"):
        raise FormatError(f"{pfad.name}: UTF-8 ohne BOM erwartet.")
    if b"\r" in roh:
        raise FormatError(f"{pfad.name}: Zeilenende LF erwartet.")
    if not roh.endswith(b"\n"):
        raise FormatError(f"{pfad.name}: letzte Zeile ohne Zeilenende.")
    try:
        text = roh.decode("utf-8")
    except UnicodeDecodeError:
        raise FormatError(f"{pfad.name}: UTF-8 erwartet.") from None
    zeilen = list(csv.reader(text.splitlines(), strict=True))
    if not zeilen or zeilen[0] != kopf:
        raise FormatError(f"{pfad.name}, Zeile 1: Kopfzeile {','.join(kopf)} erwartet.")
    daten: list[dict[str, str]] = []
    for nummer, zeile in enumerate(zeilen[1:], 2):
        if len(zeile) != len(kopf):
            raise FormatError(f"{pfad.name}, Zeile {nummer}: {len(kopf)} Spalten erwartet.")
        daten.append(dict(zip(kopf, zeile, strict=True)))
    return Csv(pfad.name, daten)


def _pruefe_rechenweg(datei: Csv, kennungen: list[str]) -> None:
    vorige: tuple[int, date] | None = None
    for nummer, z in enumerate(datei.zeilen, 2):
        o = f"{datei.name}, Zeile {nummer}"
        if z["bestandteil"] not in kennungen:
            raise FormatError(f"{o}, bestandteil: unbekannte Kennung.")
        von = _csv_datum(z["von"], f"{o}, von")
        bis = _csv_datum(z["bis"], f"{o}, bis")
        if bis < von:
            raise FormatError(f"{o}: bis liegt vor von.")
        _pruefe_grund(z["grund"], f"{o}, grund")
        for spalte in ("tage", "tagesbasis"):
            if not _GANZ.fullmatch(z[spalte]):
                raise FormatError(f"{o}, {spalte}: ganze Zahl erwartet.")
        _csv_muster(z["basis"], _BETRAG, f"{o}, basis")
        if z["basiszins"]:
            _csv_muster(z["basiszins"], _SATZ, f"{o}, basiszins")
        _csv_muster(z["satz"], _SATZ, f"{o}, satz")
        _csv_muster(z["zins_ungerundet"], _UNGERUNDET, f"{o}, zins_ungerundet")
        _csv_muster(z["zins_gerundet"], _BETRAG, f"{o}, zins_gerundet")
        position = (kennungen.index(z["bestandteil"]), von)
        if vorige is not None and position <= vorige:
            raise FormatError(
                f"{o}: Reihenfolge je Bestandteil wie in der YAML-Datei, darin nach von."
            )
        vorige = position


def _pruefe_grund(wert: str, ort: str) -> None:
    if wert == "zinsbeginn":
        return
    teile = wert.split("+")
    if not teile or any(t not in GRUENDE for t in teile):
        raise FormatError(f"{ort}: zinsbeginn allein oder {'+'.join(GRUENDE)} erwartet.")
    if teile != sorted(set(teile), key=GRUENDE.index):
        raise FormatError(f"{ort}: Gründe in der Reihenfolge {'+'.join(GRUENDE)}, ohne Doppelte.")


def _pruefe_anrechnung(datei: Csv, kennungen: list[str], zahlungen: list[tuple[date, str]]) -> None:
    vorige: date | None = None
    for nummer, z in enumerate(datei.zeilen, 2):
        o = f"{datei.name}, Zeile {nummer}"
        zahlung = _csv_datum(z["zahlung"], f"{o}, zahlung")
        _csv_muster(z["betrag"], _BETRAG, f"{o}, betrag")
        if (zahlung, z["betrag"]) not in zahlungen:
            raise FormatError(f"{o}: Zahlung steht nicht unter zahlungen.")
        if vorige is not None and zahlung < vorige:
            raise FormatError(f"{o}: Zeilen nach der Wertstellung der Zahlung ordnen.")
        vorige = zahlung
        if z["gruppe"] not in GRUPPEN:
            raise FormatError(f"{o}, gruppe: {', '.join(sorted(GRUPPEN))} erwartet.")
        _csv_muster(z["angerechnet"], _BETRAG, f"{o}, angerechnet")
        if z["gruppe"] == "ueberzahlung":
            if z["bestandteil"] or z["offen_danach"]:
                raise FormatError(
                    f"{o}: bei ueberzahlung bleiben bestandteil und offen_danach leer."
                )
            continue
        if z["bestandteil"] not in kennungen:
            raise FormatError(f"{o}, bestandteil: unbekannte Kennung.")
        _csv_muster(z["offen_danach"], _BETRAG, f"{o}, offen_danach")


# --- Grundtypen ------------------------------------------------------------------------------


def _zuordnung(
    wert: object, ort: str, pflicht: set[str], erlaubt: set[str] | None = None
) -> dict[str, object]:
    if not isinstance(wert, dict):
        raise FormatError(f"{ort}: Zuordnung erwartet.")
    felder = {str(k): v for k, v in cast("dict[object, object]", wert).items()}
    if fehlend := pflicht - felder.keys():
        raise FormatError(f"{ort}: Pflichtfeld fehlt: {', '.join(sorted(fehlend))}.")
    if unbekannt := felder.keys() - pflicht - (erlaubt or set()):
        raise FormatError(f"{ort}: unbekanntes Feld: {', '.join(sorted(unbekannt))}.")
    return felder


def _liste(wert: object, ort: str) -> list[object]:
    if not isinstance(wert, list) or not wert:
        raise FormatError(f"{ort}: nicht leere Liste erwartet.")
    return list(cast("list[object]", wert))


def _text(wert: object, ort: str) -> str:
    if not isinstance(wert, str) or not wert.strip():
        raise FormatError(f"{ort}: nicht leerer Text erwartet.")
    return wert


def _wahl(wert: object, werte: set[str], ort: str) -> str:
    if wert not in werte:
        raise FormatError(f"{ort}: einer von {', '.join(sorted(werte))} erwartet.")
    return str(wert)


def _datum(wert: object, ort: str) -> date:
    if isinstance(wert, datetime) or not isinstance(wert, date):
        raise FormatError(f"{ort}: Datum JJJJ-MM-TT ohne Anführungszeichen erwartet.")
    return wert


def _betrag(wert: object, ort: str) -> str:
    """Beträge stehen als Text mit zwei Nachkommastellen, nie als YAML-Zahl (CLAUDE.md, Geld)."""
    if not isinstance(wert, str) or not _BETRAG.fullmatch(wert):
        raise FormatError(f'{ort}: Betrag als Text wie "125.30" erwartet.')
    return wert


def _satz(wert: object, ort: str) -> Decimal:
    if not isinstance(wert, str) or not _SATZ.fullmatch(wert):
        raise FormatError(f'{ort}: Satz als Text wie "2.5" erwartet.')
    return Decimal(wert)


def _csv_datum(wert: str, ort: str) -> date:
    if not _DATUM.fullmatch(wert):
        raise FormatError(f"{ort}: Datum JJJJ-MM-TT erwartet.")
    try:
        return date.fromisoformat(wert)
    except ValueError:
        raise FormatError(f"{ort}: kein gültiges Datum.") from None


def _csv_muster(wert: str, muster: re.Pattern[str], ort: str) -> None:
    if not muster.fullmatch(wert):
        raise FormatError(f"{ort}: Format verletzt.")


# --- Eingaben für das Programm ------------------------------------------------------------


@dataclass(frozen=True)
class Eingaben:
    """Die Angaben eines Golden Files als Eingaben der Berechnung."""

    parameter: Aktenparameter
    bestandteile: list[Bestandteil]
    zahlungen: list[Zahlung]
    stichtag: date


def eingaben(fall: Fall) -> Eingaben:
    """Akte, Bestandteile und Zahlungen eines geprüften Falls für ``berechne``."""
    akte = cast("dict[str, object]", fall.daten["akte"])
    parameter = Aktenparameter(
        anrechnung=Anrechnungsregel(str(akte["anrechnung"])),
        tageszaehlung=Tageszaehlung(str(akte["tageszaehlung"])),
        zinsbeginn=Zinsbeginn(str(akte["zinsbeginn"])),
        zahltag=Zahltag(str(akte["zahltag"])),
        teilung=Teilung(str(akte["teilung"])),
        teilungstage=frozenset(cast("list[date]", akte["teilungstage"])),
    )
    bestandteile: list[Bestandteil] = []
    roh_bestandteile = cast("list[dict[str, object]]", fall.daten["bestandteile"])
    for kennung, roh in zip(fall.kennungen, roh_bestandteile, strict=True):
        regel = cast("dict[str, object]", roh["zinsregel"])
        bestandteile.append(
            Bestandteil(
                kennung,
                Bestandteilart(str(roh["art"])),
                betrag(roh["betrag"]),
                (
                    Zinsregel(
                        Zinsregeltyp(str(regel["typ"])),
                        ab=cast("date | None", regel.get("ab")),
                        bis=cast("date | None", regel.get("bis")),
                        aufschlag=_dezimal_oder_nichts(regel.get("aufschlag")),
                        satz=_dezimal_oder_nichts(regel.get("satz")),
                    ),
                ),
                entstanden_am=cast("date | None", roh.get("entstanden_am")),
            )
        )
    zahlungen = [
        Zahlung(cast("date", z["datum"]), betrag(z["betrag"]))
        for z in cast("list[dict[str, object]]", fall.daten.get("zahlungen") or [])
    ]
    erwartung = cast("dict[str, object]", fall.daten["erwartung"])
    return Eingaben(parameter, bestandteile, zahlungen, cast("date", erwartung["stichtag"]))


def _dezimal_oder_nichts(wert: object) -> Decimal | None:
    return None if wert is None else Decimal(str(wert))
