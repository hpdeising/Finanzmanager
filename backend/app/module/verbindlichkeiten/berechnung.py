# SPDX-License-Identifier: AGPL-3.0-or-later
"""Zinsen und Anrechnung einer Akte zu einem Stichtag (Fachkonzept Kap. 5.1 bis 5.3).

Zinsen und Anrechnung hängen voneinander ab: Eine Zahlung wird auf die gerundeten Zinsen der
Abschnitte vor ihrer Grenze angerechnet, und der Abschnitt ab der Grenze verzinst den Betrag
nach der Anrechnung (E-30, Kap. 5.2 Schritt 3). Deshalb läuft die Berechnung durch die Zeit:
An jedem Tag, an dem ein Abschnitt beginnt oder eine Zahlung wirkt, wird zuerst die Zahlung
angerechnet und dann der Abschnitt verzinst.

Berechnet wird bei jeder Abfrage neu, ohne Datenbank (E-21). Gleiche Eingaben ergeben dasselbe
Ergebnis (Kap. 5.1).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.kern.geld import runde_auf_cent, teile
from app.kern.stammdaten import Basiszinsreihe
from app.module.verbindlichkeiten.anrechnung import Anrechnungszeile, Posten, verteile
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Bestandteil,
    Bestandteilart,
    EingabeUngueltigError,
    Grund,
    Gruppe,
    Zahltag,
    Zahlung,
)
from app.module.verbindlichkeiten.zinsen import jahressatz, tagesbasis, zinstage
from app.module.verbindlichkeiten.zinsen.abschnitte import Abschnittsrahmen, abschnittsrahmen

__all__ = ["Abschnitt", "Anrechnungszeile", "Ergebnis", "berechne"]

HUNDERT = Decimal(100)


@dataclass(frozen=True, slots=True)
class Abschnitt:
    """Eine Zeile des Rechenwegs (Kap. 12): Basis, Satz und Tagesbasis bleiben gleich."""

    bestandteil: str
    von: date
    bis: date
    gruende: tuple[Grund, ...]
    tage: int
    tagesbasis: int
    basis: Decimal
    basiszins: Decimal | None
    satz: Decimal
    zins_exakt: Decimal
    zins: Decimal


@dataclass(frozen=True, slots=True)
class Ergebnis:
    """Rechenweg, Anrechnung und offene Beträge zum Stichtag.

    ``zinsen`` enthält für einen angebrochenen Abschnitt den bis zum Stichtag berechneten und
    gerundeten Betrag (Kap. 5.2 Schritt 7). ``ueberzahlung`` ist ein Rechenergebnis, kein Saldo
    (Kap. 5.3).
    """

    abschnitte: tuple[Abschnitt, ...]
    anrechnungen: tuple[Anrechnungszeile, ...]
    hauptforderung: Decimal
    zinsen: Decimal
    kosten: Decimal
    ueberzahlung: Decimal

    @property
    def gesamt(self) -> Decimal:
        """Restschuld: Summe der offenen Beträge (Kap. 3)."""
        return self.hauptforderung + self.zinsen + self.kosten


def berechne(
    parameter: Aktenparameter,
    bestandteile: Sequence[Bestandteil],
    zahlungen: Sequence[Zahlung],
    stichtag: date,
    reihe: Basiszinsreihe,
) -> Ergebnis:
    """Zinsen und Anrechnung bis einschließlich ``stichtag``.

    - Zinsen je Abschnitt = Basis x Jahressatz x Tage / Tagesbasis, ohne Zwischenrundung,
      kaufmännisch auf Cent gerundet (Kap. 5.2 Schritt 4, E-33). Basis ist der offene Betrag des
      Bestandteils zu Beginn des Abschnitts, nie seine Zinsen (§ 289 S. 1 BGB).
    - Ist der offene Betrag eines Bestandteils null, entstehen keine Zinsen mehr; solche
      Abschnitte erscheinen nicht im Rechenweg.
    - Zahlungen nach dem Stichtag zählen nicht. Jede andere wird an ihrer Grenze angerechnet
      (E-30), in der Gruppenfolge der Akte (§ 367 Abs. 1 BGB, § 497 Abs. 3 BGB oder individuell).

    Raises:
        EingabeUngueltigError: wenn zwei Bestandteile dieselbe Kennung haben.
        StammdatenFehlenError: wenn für einen verzinsten Tag kein Basiszinssatz vorliegt.
    """
    kennungen = [b.kennung for b in bestandteile]
    if len(set(kennungen)) != len(kennungen):
        msg = "Zwei Bestandteile haben dieselbe Kennung."
        raise EingabeUngueltigError(msg)

    gezahlt = sorted((z for z in zahlungen if z.datum <= stichtag), key=lambda z: z.datum)
    verschiebung = timedelta(days=1 if parameter.zahltag is Zahltag.ALTER_BETRAG else 0)
    grenzen = {z.datum + verschiebung for z in gezahlt}

    kapital: dict[str, Posten] = {}
    posten: list[Posten] = []
    rahmen: list[tuple[int, Bestandteil, Abschnittsrahmen]] = []
    for index, b in enumerate(bestandteile):
        p = Posten(b.kennung, b.art.gruppe, (b.entstanden_am or date.min, index), b.betrag)
        posten.append(p)
        if b.art is not Bestandteilart.ZINSEN:
            kapital[b.kennung] = p
            for r in abschnittsrahmen(b, parameter, grenzen, stichtag, reihe):
                rahmen.append((index, b, r))

    abschnitte: list[tuple[int, Abschnitt]] = []
    zeilen: list[Anrechnungszeile] = []
    ueberzahlung = Decimal(0)
    tage = sorted({r.von for _, _, r in rahmen} | grenzen)
    for tag in tage:
        for zahlung in (z for z in gezahlt if z.datum + verschiebung == tag):
            neu, rest = verteile(zahlung, parameter.gruppenfolge, posten)
            zeilen.extend(neu)
            ueberzahlung += rest
        for index, b, r in rahmen:
            if r.von != tag:
                continue
            basis = kapital[b.kennung].offen
            if basis <= 0:
                continue
            abschnitt = _verzinse(b.kennung, r, basis, parameter, reihe)
            abschnitte.append((index, abschnitt))
            posten.append(Posten(b.kennung, Gruppe.ZINSEN, (r.bis, index), abschnitt.zins))

    abschnitte.sort(key=lambda eintrag: (eintrag[0], eintrag[1].von))
    return Ergebnis(
        abschnitte=tuple(a for _, a in abschnitte),
        anrechnungen=tuple(zeilen),
        hauptforderung=_offen(posten, Gruppe.HAUPTFORDERUNG),
        zinsen=_offen(posten, Gruppe.ZINSEN),
        kosten=_offen(posten, Gruppe.KOSTEN),
        ueberzahlung=ueberzahlung,
    )


def _verzinse(
    kennung: str,
    r: Abschnittsrahmen,
    basis: Decimal,
    parameter: Aktenparameter,
    reihe: Basiszinsreihe,
) -> Abschnitt:
    """Zinsen eines Abschnitts (Kap. 5.2 Schritt 4; Satz nach § 288 BGB u. a., siehe jahressatz)."""
    satz = jahressatz(r.regel, r.von, reihe)
    tage = zinstage(r.von, r.bis, parameter.tageszaehlung, r.vortag_verzinst)
    basis_tage = tagesbasis(parameter.tageszaehlung, r.von)
    exakt = teile(basis * satz.satz * tage, HUNDERT * basis_tage)
    return Abschnitt(
        kennung,
        r.von,
        r.bis,
        r.gruende,
        tage,
        basis_tage,
        basis,
        satz.basiszins,
        satz.satz,
        exakt,
        runde_auf_cent(exakt),
    )


def _offen(posten: Sequence[Posten], gruppe: Gruppe) -> Decimal:
    return sum((p.offen for p in posten if p.gruppe is gruppe), Decimal(0))
