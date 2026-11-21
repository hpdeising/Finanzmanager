# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verjährung je Bestandteil und je Zinsjahr (Fachkonzept Kap. 5.5).

Wie die Fristen wird die Verjährung aus Ereignissen berechnet und nie gespeichert. Wo Rechtslage
oder Datum unsicher sind, endet sie im Zweifel später (E-36).

Ablauf je Gegenstand (ein Bestandteil oder die Zinsen eines Bestandteils für ein Kalenderjahr):

1. Beginn und regelmäßiges Ende nach dem Fall der Tabelle in Kap. 5.5.
2. Neubeginn (§ 212 Abs. 1 BGB) durch Zahlung, Anerkenntnis, Antrag oder Vornahme einer
   Vollstreckungshandlung, solange die Verjährung läuft und noch nicht eingetreten ist: Die volle
   Frist beginnt mit dem Ereignis neu, ohne Jahresschluss.
3. Hemmung (§ 209 BGB): Tage, an denen die Verjährung gehemmt ist, zählen nicht; das Ende
   verschiebt sich um sie. Hemmung durch Mahnbescheid (§ 204 Abs. 1 Nr. 3, Abs. 2 BGB) und bei
   Verbraucherdarlehen ab Verzug (§ 497 Abs. 3 BGB).
4. § 193 BGB (P-01, Voreinstellung nach E-36): Fällt das Ende auf einen Samstag, Sonntag oder
   Feiertag, endet die Verjährung am nächsten Werktag.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from app.kern.stammdaten import Feiertagskalender
from app.module.verbindlichkeiten.anrechnung import Anrechnungszeile
from app.module.verbindlichkeiten.berechnung import Abschnitt
from app.module.verbindlichkeiten.domain import (
    Bestandteil,
    Bestandteilart,
    Ereignis,
    Ereignistyp,
    Gruppe,
)
from app.module.verbindlichkeiten.fristen import (
    Dauer,
    Einheit,
    Fristart,
    fristende,
    warnstufen,
)

EIN_TAG = timedelta(days=1)
SAMSTAG = 5
PFLICHTHINWEIS = (
    "Verjährung tritt nicht von selbst ein, sie muss als Einrede erhoben werden (§ 214 Abs. 1 "
    "BGB). Die Berechnung ist eine Näherung auf Grundlage der erfassten Ereignisse. Fehlt ein "
    "Ereignis, ist das Ergebnis falsch."
)
_NEUBEGINN = {
    Ereignistyp.ZAHLUNG,
    Ereignistyp.ANERKENNTNIS,
    Ereignistyp.VOLLSTRECKUNGSANTRAG,
    Ereignistyp.VOLLSTRECKUNGSHANDLUNG,
}
# Sofortige Beschwerde (§ 104 Abs. 3, § 567 ZPO) oder Erinnerung (§ 11 Abs. 2 Satz 1 RPflG);
# beide verhindern die berechnete Rechtskraft (Entscheidung vom 21.11.2026).
_RECHTSBEHELF_KFB = (Ereignistyp.SOFORTIGE_BESCHWERDE, Ereignistyp.ERINNERUNG)
_ENDE_MAHNVERFAHREN = {
    Ereignistyp.MAHNVERFAHREN_OHNE_TITEL_BEENDET,
    Ereignistyp.LETZTE_VERFAHRENSHANDLUNG,
}


class Verjaehrungsfall(StrEnum):
    """Fall der Tabelle in Kap. 5.5."""

    NICHT_TITULIERT = "nicht_tituliert"
    RECHTSKRAEFTIG_FESTGESTELLT = "rechtskraeftig_festgestellt"
    VERGLEICH_URKUNDE = "vergleich_urkunde"
    KOSTENFESTSETZUNGSBESCHLUSS = "kostenfestsetzungsbeschluss"
    KOSTEN_ZWANGSVOLLSTRECKUNG = "kosten_zwangsvollstreckung"
    LAUFENDE_ZINSEN = "laufende_zinsen"
    VERBRAUCHERDARLEHEN_ZINSEN = "verbraucherdarlehen_zinsen"

    @property
    def norm(self) -> str:
        return _NORM[self]

    @property
    def jahre(self) -> int:
        """Dauer der Verjährungsfrist in Jahren."""
        return 3 if self in _DREI_JAHRE else 30


_NORM = {
    Verjaehrungsfall.NICHT_TITULIERT: "§§ 195, 199 Abs. 1 BGB",
    Verjaehrungsfall.RECHTSKRAEFTIG_FESTGESTELLT: "§ 197 Abs. 1 Nr. 3, § 201 BGB; § 700 Abs. 1 ZPO",
    Verjaehrungsfall.VERGLEICH_URKUNDE: "§ 197 Abs. 1 Nr. 4, § 201 BGB",
    Verjaehrungsfall.KOSTENFESTSETZUNGSBESCHLUSS: "§ 197 Abs. 1 Nr. 3, § 201 BGB",
    Verjaehrungsfall.KOSTEN_ZWANGSVOLLSTRECKUNG: "§ 197 Abs. 1 Nr. 6, § 201 BGB",
    Verjaehrungsfall.LAUFENDE_ZINSEN: "§ 197 Abs. 2, §§ 195, 199 Abs. 1 BGB",
    Verjaehrungsfall.VERBRAUCHERDARLEHEN_ZINSEN: "§ 497 Abs. 3 BGB",
}
_DREI_JAHRE = {Verjaehrungsfall.NICHT_TITULIERT, Verjaehrungsfall.LAUFENDE_ZINSEN}


class NeubeginnUmfang(StrEnum):
    """P-02: Wirkt der Neubeginn durch Zahlung für alle Bestandteile oder nur für angerechnete?"""

    ALLE = "alle"
    ANGERECHNETE = "angerechnete"


@dataclass(frozen=True, slots=True)
class Verjaehrungseinstellungen:
    """Einstellbare Prüfpunkte; Voreinstellungen nach Kap. 5.5 und E-36."""

    p01_193_bgb: bool = True
    p17_ruecklastschrift_neubeginn: bool = True
    p02_neubeginn: NeubeginnUmfang = NeubeginnUmfang.ALLE


@dataclass(frozen=True, slots=True)
class Verjaehrung:
    """Verjährung eines Gegenstands. ``ende`` fehlt, wenn sie sich nicht bestimmen lässt.

    ``beginn`` ist der erste Tag, der zählt; ``hemmungstage`` die Tage, die nach § 209 BGB nicht
    zählen; ``neubeginn`` das letzte Ereignis, mit dem die Verjährung neu begann.
    """

    gegenstand: str
    bestandteil: str
    fall: Verjaehrungsfall
    beginn: date | None
    ende: date | None
    hemmungstage: int = 0
    neubeginn: date | None = None
    warnstufen: tuple[date, ...] = ()
    hinweise: tuple[str, ...] = ()

    @property
    def norm(self) -> str:
        return self.fall.norm

    @property
    def art(self) -> Fristart:
        """Verjährung ist eine Information mit Warnung 30 Tage vorher (Kap. 5.4)."""
        return Fristart.INFORMATION


@dataclass(frozen=True, slots=True)
class Verjaehrungsergebnis:
    eintraege: tuple[Verjaehrung, ...]
    warnungen: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Titel:
    datum: date | None
    fall: Verjaehrungsfall | None
    hinweis: str | None = None
    unbekannt: bool = False


@dataclass(frozen=True, slots=True)
class _Hemmung:
    von: date
    bis: date | None
    grund: str


@dataclass
class _Lauf:
    beginn: date
    grundende: date
    jahre: int
    neubeginn: date | None = None
    hinweise: list[str] = field(default_factory=list[str])


def verjaehrung_berechnen(
    bestandteile: Sequence[Bestandteil],
    ereignisse: Sequence[Ereignis],
    stichtag: date,
    kalender: Feiertagskalender,
    haushalt_land: str,
    *,
    verbraucherdarlehen: bool = False,
    einstellungen: Verjaehrungseinstellungen | None = None,
    abschnitte: Sequence[Abschnitt] = (),
    anrechnungen: Sequence[Anrechnungszeile] | None = None,
) -> Verjaehrungsergebnis:
    """Verjährung aller Bestandteile und ihrer Zinsen zum ``stichtag`` (Kap. 5.5).

    ``abschnitte`` (aus ``berechne``) bestimmen, in welchen Jahren Zinsen entstanden sind;
    ``anrechnungen`` braucht es nur bei P-02 = ``angerechnete``.

    Raises:
        ValueError: bei P-02 = ``angerechnete`` ohne ``anrechnungen``.
        StammdatenFehlenError: wenn der Feiertagskalender für eine nötige Einspruchsfrist nichts
            weiß.
    """
    einstellungen = einstellungen or Verjaehrungseinstellungen()
    if einstellungen.p02_neubeginn is NeubeginnUmfang.ANGERECHNETE and anrechnungen is None:
        msg = "P-02 = angerechnete braucht die Anrechnungen."
        raise ValueError(msg)
    erfasst = sorted(
        (e for e in ereignisse if e.datum is not None and e.datum <= stichtag),
        key=lambda e: e.datum or date.min,
    )
    warnungen: list[str] = []
    titel = _titel(erfasst, kalender, haushalt_land, warnungen)
    mahnverfahren = _hemmung_mahnverfahren(erfasst, titel)
    eintraege: list[Verjaehrung] = []
    for b in bestandteile:
        if b.entstanden_am is not None and b.entstanden_am > stichtag:
            continue
        hemmungen = list(mahnverfahren)
        if verbraucherdarlehen:
            hemmungen.extend(_hemmung_verzug(erfasst, titel, b))
        for gegenstand, fall, lauf in _gegenstaende(b, titel, abschnitte, verbraucherdarlehen):
            if lauf is None:
                if fall is Verjaehrungsfall.NICHT_TITULIERT and b.faellig_am is None:
                    warnungen.append(f"{b.kennung}: Fälligkeit fehlt; keine Verjährung berechnet.")
                eintraege.append(Verjaehrung(gegenstand, b.kennung, fall, None, None))
                continue
            neubeginn = _neubeginn_ereignisse(erfasst, b, gegenstand, einstellungen, anrechnungen)
            eintraege.append(
                _verjaehrung(
                    gegenstand,
                    b.kennung,
                    fall,
                    lauf,
                    hemmungen,
                    neubeginn,
                    kalender,
                    haushalt_land,
                    einstellungen,
                )
            )
    return Verjaehrungsergebnis(tuple(eintraege), tuple(dict.fromkeys(warnungen)))


# --- Titel ------------------------------------------------------------------------------------


def _titel(
    erfasst: Sequence[Ereignis], kalender: Feiertagskalender, land: str, warnungen: list[str]
) -> _Titel:
    """Tag, ab dem die Forderung tituliert ist (Rechtskraft oder Errichtung), und ihr Fall.

    Eine erfasste Rechtskraft hat Vorrang. Sonst wird beim Vollstreckungsbescheid die Rechtskraft
    aus Zustellung plus Einspruchsfrist berechnet, wenn kein Einspruch erfasst ist (§ 700 Abs. 1,
    § 339 Abs. 1 ZPO): rechtskräftig mit dem Tag nach dem Ende der Einspruchsfrist.

    Der Kostenfestsetzungsbeschluss zählt nur, wenn kein anderer Titel erfasst ist. Seine
    Rechtskraft wird aus Zustellung plus Frist der sofortigen Beschwerde berechnet (§ 104 Abs. 3,
    § 569 Abs. 1 ZPO: zwei Wochen, Notfrist), wenn keine Beschwerde erfasst ist (Entscheidung vom
    21.11.2026).
    """

    def erstes(typ: Ereignistyp) -> Ereignis | None:
        return next((e for e in erfasst if e.typ is typ), None)

    kfb = erstes(Ereignistyp.ZUSTELLUNG_KOSTENFESTSETZUNGSBESCHLUSS)
    nur_kfb = kfb is not None and not any(
        erstes(t) is not None
        for t in (
            Ereignistyp.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID,
            Ereignistyp.ZUSTELLUNG_URTEIL,
            Ereignistyp.ERRICHTUNG_TITEL,
        )
    )
    if (rechtskraft := erstes(Ereignistyp.RECHTSKRAFT)) is not None:
        fall = (
            Verjaehrungsfall.KOSTENFESTSETZUNGSBESCHLUSS
            if nur_kfb
            else Verjaehrungsfall.RECHTSKRAEFTIG_FESTGESTELLT
        )
        return _Titel(rechtskraft.datum, fall)
    vb = erstes(Ereignistyp.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID)
    if vb is not None and vb.datum is not None:
        if erstes(Ereignistyp.EINSPRUCH) is not None:
            warnungen.append("Einspruch erfasst, Rechtskraft fehlt: Verjährung offen.")
            return _Titel(None, None, unbekannt=True)
        ende = fristende(
            vb.datum, Dauer(2, Einheit.WOCHEN), Fristart.NOTFRIST, kalender, vb.gericht_land or land
        )
        return _Titel(
            ende + EIN_TAG,
            Verjaehrungsfall.RECHTSKRAEFTIG_FESTGESTELLT,
            "Rechtskraft berechnet aus Zustellung und Einspruchsfrist.",
        )
    if (errichtung := erstes(Ereignistyp.ERRICHTUNG_TITEL)) is not None:
        return _Titel(errichtung.datum, Verjaehrungsfall.VERGLEICH_URKUNDE)
    if erstes(Ereignistyp.ZUSTELLUNG_URTEIL) is not None:
        warnungen.append("Urteil erfasst, Rechtskraft fehlt: Verjährung offen.")
        return _Titel(None, None, unbekannt=True)
    if kfb is not None and kfb.datum is not None:
        if any(erstes(t) is not None for t in _RECHTSBEHELF_KFB):
            warnungen.append(
                "Rechtsbehelf gegen den Kostenfestsetzungsbeschluss erfasst, Rechtskraft fehlt:"
                " Verjährung offen."
            )
            return _Titel(None, None, unbekannt=True)
        ende = fristende(
            kfb.datum,
            Dauer(2, Einheit.WOCHEN),
            Fristart.NOTFRIST,
            kalender,
            kfb.gericht_land or land,
        )
        return _Titel(
            ende + EIN_TAG,
            Verjaehrungsfall.KOSTENFESTSETZUNGSBESCHLUSS,
            "Rechtskraft berechnet aus Zustellung und Frist der sofortigen Beschwerde.",
        )
    return _Titel(None, None)


# --- Gegenstände --------------------------------------------------------------------------------


def _gegenstaende(
    b: Bestandteil, titel: _Titel, abschnitte: Sequence[Abschnitt], verbraucherdarlehen: bool
) -> Iterable[tuple[str, Verjaehrungsfall, _Lauf | None]]:
    """Gegenstände eines Bestandteils mit Fall und regelmäßigem Lauf (ohne Lauf: offen)."""
    if b.art is Bestandteilart.KOSTEN_VOLLSTRECKUNG:
        fall = Verjaehrungsfall.KOSTEN_ZWANGSVOLLSTRECKUNG
        yield b.kennung, fall, _ab_ereignis(b.entstanden_am, fall)
    elif (
        titel.datum is not None
        and titel.fall is not None
        and (b.entstanden_am is None or b.entstanden_am <= titel.datum)
    ):
        lauf = _ab_ereignis(titel.datum, titel.fall)
        if lauf is not None and titel.hinweis:
            lauf.hinweise.append(titel.hinweis)
        yield b.kennung, titel.fall, lauf
    elif titel.unbekannt:
        yield b.kennung, Verjaehrungsfall.RECHTSKRAEFTIG_FESTGESTELLT, None
        return
    else:
        start = _kenntnis(b)
        fall = Verjaehrungsfall.NICHT_TITULIERT
        yield b.kennung, fall, _ab_jahresschluss(start.year, fall) if start else None
    yield from _zinsen(b, titel, abschnitte, verbraucherdarlehen)


def _zinsen(
    b: Bestandteil, titel: _Titel, abschnitte: Sequence[Abschnitt], verbraucherdarlehen: bool
) -> Iterable[tuple[str, Verjaehrungsfall, _Lauf | None]]:
    """Zinsen eines Bestandteils: bis zur Titulierung mit dem Titel; danach je Kalenderjahr
    der Entstehung (§ 197 Abs. 2 BGB), bei Verbraucherdarlehen 30 Jahre (§ 497 Abs. 3 BGB)."""
    tage = [(a.von, a.bis) for a in abschnitte if a.bestandteil == b.kennung and a.zins > 0]
    if not tage:
        return
    if titel.datum is not None and titel.fall is not None:
        if any(von <= titel.datum for von, _ in tage):
            yield (
                f"{b.kennung}: Zinsen bis Titulierung",
                titel.fall,
                _ab_ereignis(titel.datum, titel.fall),
            )
        danach = [(max(von, titel.datum + EIN_TAG), bis) for von, bis in tage if bis > titel.datum]
        if not danach:
            return
        if verbraucherdarlehen:
            fall = Verjaehrungsfall.VERBRAUCHERDARLEHEN_ZINSEN
            yield f"{b.kennung}: Zinsen ab Titulierung", fall, _ab_ereignis(titel.datum, fall)
            return
        fall = Verjaehrungsfall.LAUFENDE_ZINSEN
    else:
        danach = tage
        fall = Verjaehrungsfall.NICHT_TITULIERT
    jahre = sorted({j for von, bis in danach for j in range(von.year, bis.year + 1)})
    for jahr in jahre:
        yield f"{b.kennung}: Zinsen {jahr}", fall, _ab_jahresschluss(jahr, fall)


def _kenntnis(b: Bestandteil) -> date | None:
    """Fälligkeit; die Kenntnis des Gläubigers gilt mit ihr als gegeben, wenn nichts anderes
    erfasst ist (Entscheidung vom 20.11.2026)."""
    if b.faellig_am is None:
        return None
    return max(b.faellig_am, b.kenntnis_am or b.faellig_am)


def _ab_ereignis(tag: date | None, fall: Verjaehrungsfall) -> _Lauf | None:
    """Beginn mit einem Ereignis (§ 201 BGB, § 187 Abs. 1 BGB): der Tag selbst zählt nicht."""
    if tag is None:
        return None
    return _Lauf(tag + EIN_TAG, _plus_jahre(tag, fall.jahre), fall.jahre)


def _ab_jahresschluss(jahr: int, fall: Verjaehrungsfall) -> _Lauf:
    """Beginn mit dem Schluss des Jahres (§ 199 Abs. 1 BGB)."""
    return _Lauf(date(jahr + 1, 1, 1), date(jahr + fall.jahre, 12, 31), fall.jahre)


def _plus_jahre(tag: date, jahre: int) -> date:
    return fristende(tag, Dauer(jahre, Einheit.JAHRE), Fristart.INFORMATION)


# --- Hemmung und Neubeginn ---------------------------------------------------------------------


def _hemmung_mahnverfahren(erfasst: Sequence[Ereignis], titel: _Titel) -> list[_Hemmung]:
    """§ 204 Abs. 1 Nr. 3, Abs. 2 BGB: ab Zustellung des Mahnbescheids; endet mit der
    Rechtskraft des Vollstreckungsbescheids, sonst sechs Monate nach der Beendigung ohne Titel
    oder der letzten Verfahrenshandlung. Ohne solches Ereignis dauert sie an."""
    hemmungen: list[_Hemmung] = []
    for mb in (e for e in erfasst if e.typ is Ereignistyp.ZUSTELLUNG_MAHNBESCHEID):
        if mb.datum is None:
            continue
        grund = "gehemmt durch das Mahnverfahren (§ 204 Abs. 1 Nr. 3, Abs. 2 BGB)"
        if titel.datum is not None and titel.datum >= mb.datum:
            hemmungen.append(_Hemmung(mb.datum, titel.datum, grund))
            continue
        ende = [
            e.datum
            for e in erfasst
            if e.typ in _ENDE_MAHNVERFAHREN and e.datum and e.datum >= mb.datum
        ]
        bis = fristende(max(ende), Dauer(6, Einheit.MONATE), Fristart.INFORMATION) if ende else None
        hemmungen.append(_Hemmung(mb.datum, bis, grund))
    return hemmungen


def _hemmung_verzug(erfasst: Sequence[Ereignis], titel: _Titel, b: Bestandteil) -> list[_Hemmung]:
    """§ 497 Abs. 3 BGB: ab Verzug bis zur Titulierung, höchstens zehn Jahre ab Entstehung."""
    verzug = next((e for e in erfasst if e.typ is Ereignistyp.VERZUG_EINGETRETEN), None)
    if verzug is None or verzug.datum is None:
        return []
    grenze = _plus_jahre(b.entstanden_am or verzug.datum, 10)
    bis = min(titel.datum, grenze) if titel.datum is not None else grenze
    return [_Hemmung(verzug.datum, bis, "gehemmt ab Verzug (§ 497 Abs. 3 BGB)")]


def _neubeginn_ereignisse(
    erfasst: Sequence[Ereignis],
    b: Bestandteil,
    gegenstand: str,
    einstellungen: Verjaehrungseinstellungen,
    anrechnungen: Sequence[Anrechnungszeile] | None,
) -> list[date]:
    """Tage mit Neubeginn nach § 212 Abs. 1 BGB für diesen Gegenstand (P-02, P-17)."""
    zinsen = gegenstand != b.kennung
    tage: list[date] = []
    for e in erfasst:
        if e.typ not in _NEUBEGINN or e.datum is None:
            continue
        if e.zurueckgegeben and not einstellungen.p17_ruecklastschrift_neubeginn:
            continue
        if (
            e.typ is Ereignistyp.ZAHLUNG
            and einstellungen.p02_neubeginn is NeubeginnUmfang.ANGERECHNETE
            and not _angerechnet(e.datum, b.kennung, zinsen, anrechnungen or ())
        ):
            continue
        tage.append(e.datum)
    return tage


def _angerechnet(
    tag: date, kennung: str, zinsen: bool, anrechnungen: Sequence[Anrechnungszeile]
) -> bool:
    return any(
        z.zahlung.datum == tag
        and z.bestandteil == kennung
        and z.angerechnet > 0
        and ((z.gruppe is Gruppe.ZINSEN) == zinsen)
        for z in anrechnungen
    )


# --- Lauf ---------------------------------------------------------------------------------------


def _verjaehrung(
    gegenstand: str,
    kennung: str,
    fall: Verjaehrungsfall,
    lauf: _Lauf,
    hemmungen: Sequence[_Hemmung],
    neubeginn: Sequence[date],
    kalender: Feiertagskalender,
    land: str,
    einstellungen: Verjaehrungseinstellungen,
) -> Verjaehrung:
    for tag in sorted(neubeginn):
        ende, _ = _mit_hemmung(lauf.beginn, lauf.grundende, hemmungen)
        if tag < lauf.beginn - EIN_TAG:
            continue  # vor Beginn der Verjährung
        if ende is not None and tag > ende:
            break  # Verjährung schon eingetreten (§ 212 BGB setzt eine laufende voraus)
        neu = _Lauf(tag + EIN_TAG, _plus_jahre(tag, lauf.jahre), lauf.jahre, tag, lauf.hinweise)
        neu_ende, _ = _mit_hemmung(neu.beginn, neu.grundende, hemmungen)
        if ende is None or neu_ende is None or neu_ende >= ende:
            lauf = neu
    ende, tage = _mit_hemmung(lauf.beginn, lauf.grundende, hemmungen)
    hinweise = list(lauf.hinweise)
    if lauf.neubeginn is not None:
        hinweise.append(f"Neubeginn am {lauf.neubeginn.isoformat()} (§ 212 Abs. 1 BGB).")
    for h in hemmungen:
        if _ueberlappt(h, lauf.beginn, ende):
            hinweise.append(h.grund + ("" if h.bis else ", noch nicht beendet"))
    if ende is not None and einstellungen.p01_193_bgb:
        ende = _paragraf_193(ende, kalender, land)
    return Verjaehrung(
        gegenstand,
        kennung,
        fall,
        lauf.beginn,
        ende,
        tage,
        lauf.neubeginn,
        warnstufen(ende, Fristart.INFORMATION) if ende else (),
        tuple(dict.fromkeys(hinweise)),
    )


def _mit_hemmung(
    beginn: date, grundende: date, hemmungen: Sequence[_Hemmung]
) -> tuple[date | None, int]:
    """Ende nach § 209 BGB: um die gehemmten Tage zwischen Beginn und Ende verschoben. Dauert eine
    Hemmung an, die in die Frist fällt, gibt es kein Ende."""
    ende = grundende
    tage = 0
    while True:
        if any(h.bis is None and h.von <= ende for h in hemmungen):
            return None, tage
        gesamt = _gehemmte_tage(beginn, ende, hemmungen)
        if gesamt == tage:
            return ende, tage
        tage = gesamt
        ende = grundende + timedelta(days=tage)


def _gehemmte_tage(beginn: date, ende: date, hemmungen: Sequence[_Hemmung]) -> int:
    """Gehemmte Tage zwischen ``beginn`` und ``ende``, beide eingeschlossen, ohne Doppelzählung."""
    tage: set[date] = set()
    for h in hemmungen:
        if h.bis is None:
            continue
        von, bis = max(h.von, beginn), min(h.bis, ende)
        tag = von
        while tag <= bis:
            tage.add(tag)
            tag += EIN_TAG
    return len(tage)


def _ueberlappt(h: _Hemmung, beginn: date, ende: date | None) -> bool:
    bis = h.bis or date.max
    return h.von <= (ende or date.max) and bis >= beginn


def _paragraf_193(ende: date, kalender: Feiertagskalender, land: str) -> date:
    """§ 193 BGB: Ende an Samstag, Sonntag oder Feiertag am Leistungsort -> nächster Werktag.

    Nach E-36 zählen hier auch Feiertage, die nur in Teilen des Landes gelten (später).

    Raises:
        StammdatenFehlenError: wenn das Ende nach dem Feiertagskalender liegt (Fehler statt
            Schätzung, Entscheidung vom 21.11.2026).
    """
    while (
        ende.weekday() >= SAMSTAG
        or kalender.ist_feiertag(ende, land)
        or kalender.regionaler_feiertag(ende, land) is not None
    ):
        ende += EIN_TAG
    return ende
