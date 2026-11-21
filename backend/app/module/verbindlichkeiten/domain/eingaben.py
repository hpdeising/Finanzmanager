# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eingaben der Berechnung von Zinsen und Anrechnung (Fachkonzept Kap. 4.5, 5.1 bis 5.3).

Die Berechnung arbeitet auf diesen Werten, nicht auf der Datenbank: Zinsen und Anrechnung
werden bei jeder Abfrage neu berechnet (E-21). Stornierte Zahlungen gibt der Aufrufer nicht mit.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import NoReturn

from app.kern.stammdaten import LAENDER
from app.module.verbindlichkeiten.domain.begriffe import (
    Anrechnungsregel,
    Bestandteilart,
    Ereignistyp,
    Gruppe,
    Tageszaehlung,
    Teilung,
    Zahltag,
    Zinsbeginn,
    Zinsregeltyp,
)
from app.module.verbindlichkeiten.domain.fehler import EingabeUngueltigError


@dataclass(frozen=True, slots=True)
class Zinsregel:
    """Berechnungsvorschrift für die Zinsen eines Bestandteils (Kap. 4.5, 5.2).

    ``ab`` ist der genannte Tag des Zinsbeginns, ``bis`` der letzte verzinste Tag; ohne ``bis``
    gilt die Regel bis zur nächsten Zinsregel oder bis zum Stichtag. Eine Zinsregel ``keine``
    beginnt eine Pause ohne Verzinsung; ohne ``ab`` gilt sie von Anfang an.
    """

    typ: Zinsregeltyp
    ab: date | None = None
    bis: date | None = None
    aufschlag: Decimal | None = None
    satz: Decimal | None = None

    def __post_init__(self) -> None:
        if self.typ.verzinslich and self.ab is None:
            _fehler("Eine verzinsliche Zinsregel braucht ab.")
        if self.typ is Zinsregeltyp.KEINE and self.bis is not None:
            _fehler("Eine Zinsregel keine endet mit der nächsten Zinsregel, nicht mit bis.")
        if self.ab is not None and self.bis is not None and self.bis < self.ab:
            _fehler("bis liegt vor ab.")
        if (self.aufschlag is not None) != (self.typ is Zinsregeltyp.BASISZINS_PLUS):
            _fehler("Einen Aufschlag hat genau die Zinsregel basiszins_plus.")
        if (self.satz is not None) != (self.typ is Zinsregeltyp.FEST):
            _fehler("Einen festen Satz hat genau die Zinsregel fest.")


@dataclass(frozen=True, slots=True, init=False)
class Bestandteil:
    """Teil der Forderung mit eigener Rechtslogik (Kap. 3, 4.5).

    ``kennung`` benennt den Bestandteil in Rechenweg und Anrechnung. ``entstanden_am`` ordnet
    Bestandteile derselben Gruppe für die Anrechnung (älteste Position zuerst, Kap. 5.3).
    ``faellig_am`` und ``kenntnis_am`` (Kenntnis des Gläubigers, sonst mit der Fälligkeit
    gegeben) bestimmen den Beginn der Verjährung einer nicht titulierten Forderung (Kap. 5.5).
    """

    kennung: str
    art: Bestandteilart
    betrag: Decimal
    zinsregeln: tuple[Zinsregel, ...] = ()
    entstanden_am: date | None = None
    faellig_am: date | None = None
    kenntnis_am: date | None = None

    def __init__(
        self,
        kennung: str,
        art: Bestandteilart,
        betrag: Decimal,
        zinsregeln: Iterable[Zinsregel] = (),
        entstanden_am: date | None = None,
        *,
        faellig_am: date | None = None,
        kenntnis_am: date | None = None,
    ) -> None:
        regeln = tuple(sorted(zinsregeln, key=lambda r: r.ab or date.min))
        object.__setattr__(self, "kennung", kennung)
        object.__setattr__(self, "art", art)
        object.__setattr__(self, "betrag", betrag)
        object.__setattr__(self, "zinsregeln", regeln)
        object.__setattr__(self, "entstanden_am", entstanden_am)
        object.__setattr__(self, "faellig_am", faellig_am)
        object.__setattr__(self, "kenntnis_am", kenntnis_am)
        self._pruefe()

    def _pruefe(self) -> None:
        if not self.kennung:
            _fehler("Ein Bestandteil braucht eine Kennung.")
        if self.betrag <= 0:
            _fehler("Der Betrag eines Bestandteils muss positiv sein.")
        if self.art is Bestandteilart.ZINSEN and any(r.typ.verzinslich for r in self.zinsregeln):
            _fehler("Zinsen sind nie verzinslich (§ 289 S. 1 BGB).")
        for vorige, naechste in zip(self.zinsregeln, self.zinsregeln[1:], strict=False):
            beginn_vorige = vorige.ab or date.min
            beginn_naechste = naechste.ab or date.min
            if beginn_naechste <= beginn_vorige:
                _fehler("Zwei Zinsregeln eines Bestandteils beginnen am selben Tag.")
            if vorige.bis is not None and vorige.bis >= beginn_naechste:
                _fehler("Zinsregeln eines Bestandteils überlappen sich.")


@dataclass(frozen=True, slots=True)
class Zahlung:
    """Nicht stornierte Zahlung mit ihrer Wertstellung (Kap. 5.3, E-26)."""

    datum: date
    betrag: Decimal

    def __post_init__(self) -> None:
        if self.betrag <= 0:
            _fehler("Der Betrag einer Zahlung muss positiv sein.")


@dataclass(frozen=True, slots=True)
class Aktenparameter:
    """Rechenvorgaben einer Akte; die Voreinstellungen sind die des Fachkonzepts (Kap. 5.1).

    ``reihenfolge`` gilt nur bei ``anrechnung = individuell``: die Gruppen in der Reihenfolge,
    die die Vereinbarung mit dem Gläubiger festlegt.
    """

    anrechnung: Anrechnungsregel = Anrechnungsregel.BGB_367
    tageszaehlung: Tageszaehlung = Tageszaehlung.ACT_365
    zinsbeginn: Zinsbeginn = Zinsbeginn.GENANNTER_TAG
    zahltag: Zahltag = Zahltag.ALTER_BETRAG
    teilung: Teilung = Teilung.KALENDER
    teilungstage: frozenset[date] = field(default_factory=frozenset[date])
    reihenfolge: tuple[Gruppe, ...] | None = None

    def __post_init__(self) -> None:
        if self.anrechnung is Anrechnungsregel.INDIVIDUELL:
            if self.reihenfolge is None or sorted(self.reihenfolge) != sorted(Gruppe):
                _fehler("Individuelle Anrechnung braucht jede Gruppe genau einmal.")
        elif self.reihenfolge is not None:
            _fehler("Eine eigene Reihenfolge gibt es nur bei individueller Anrechnung.")

    @property
    def gruppenfolge(self) -> tuple[Gruppe, ...]:
        """Reihenfolge der Gruppen bei der Anrechnung (Kap. 5.3).

        ``bgb_367``: Kosten, Zinsen, Hauptforderung (§ 367 Abs. 1 BGB). ``bgb_497``: Kosten der
        Rechtsverfolgung, Hauptforderung, Zinsen (§ 497 Abs. 3 BGB). ``individuell``: laut
        Vereinbarung.
        """
        if self.anrechnung is Anrechnungsregel.BGB_367:
            return (Gruppe.KOSTEN, Gruppe.ZINSEN, Gruppe.HAUPTFORDERUNG)
        if self.anrechnung is Anrechnungsregel.BGB_497:
            return (Gruppe.KOSTEN, Gruppe.HAUPTFORDERUNG, Gruppe.ZINSEN)
        if self.reihenfolge is None:  # durch __post_init__ ausgeschlossen
            _fehler("Individuelle Anrechnung braucht eine Reihenfolge.")
        return self.reihenfolge


def _fehler(meldung: str) -> NoReturn:
    raise EingabeUngueltigError(meldung)


@dataclass(frozen=True, slots=True)
class Ereignis:
    """Datiertes, rechtlich relevantes Geschehen (Kap. 3, 4.5); Fristen folgen daraus (Kap. 5.4).

    ``datum`` kann fehlen, etwa wenn bei einer Zustellung das Datum unbekannt ist; dann gibt es
    keine Frist, sondern eine Warnung. ``versaeumnisurteil`` unterscheidet bei
    ``zustellung_urteil`` das Versäumnisurteil vom streitigen Urteil, ``bekanntgabe_am`` nennt
    bei ``eintragungsanordnung`` den Tag der Bekanntgabe. ``gericht_land`` ist das Land des
    Gerichts, bei dem die Handlung vorzunehmen ist; nach ihm richten sich die Feiertage (Kap. 5.4).
    ``zurueckgegeben`` markiert eine Zahlung, die per Rücklastschrift zurückgegeben wurde (P-17).
    """

    typ: Ereignistyp
    datum: date | None
    versaeumnisurteil: bool = False
    bekanntgabe_am: date | None = None
    gericht_land: str | None = None
    zurueckgegeben: bool = False

    def __post_init__(self) -> None:
        if self.zurueckgegeben and self.typ is not Ereignistyp.ZAHLUNG:
            _fehler("zurueckgegeben gibt es nur bei zahlung.")
        if self.gericht_land is not None and self.gericht_land not in LAENDER:
            _fehler("Unbekanntes Land des Gerichts.")
        if self.versaeumnisurteil and self.typ is not Ereignistyp.ZUSTELLUNG_URTEIL:
            _fehler("versaeumnisurteil gibt es nur bei zustellung_urteil.")
        if self.bekanntgabe_am is not None and self.typ is not Ereignistyp.EINTRAGUNGSANORDNUNG:
            _fehler("bekanntgabe_am gibt es nur bei eintragungsanordnung.")
