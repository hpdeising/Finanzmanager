# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fachbegriffe als Aufzählungen, mit den Werten aus Fachkonzept Kap. 4.5, 5.1 bis 5.3."""

from enum import StrEnum


class Gruppe(StrEnum):
    """Gruppe, auf die eine Zahlung angerechnet wird (Kap. 5.3)."""

    KOSTEN = "kosten"
    ZINSEN = "zinsen"
    HAUPTFORDERUNG = "hauptforderung"


class Bestandteilart(StrEnum):
    """Art eines Bestandteils (Kap. 3, Kontenrahmen Kap. 4.2)."""

    HAUPTFORDERUNG = "hauptforderung"
    ZINSEN = "zinsen"
    KOSTEN_VORGERICHTLICH = "kosten_vorgerichtlich"
    KOSTEN_VERFAHREN = "kosten_verfahren"
    KOSTEN_VOLLSTRECKUNG = "kosten_vollstreckung"

    @property
    def gruppe(self) -> Gruppe:
        """Gruppe des Betrags dieses Bestandteils; seine berechneten Zinsen sind immer Zinsen."""
        if self is Bestandteilart.HAUPTFORDERUNG:
            return Gruppe.HAUPTFORDERUNG
        if self is Bestandteilart.ZINSEN:
            return Gruppe.ZINSEN
        return Gruppe.KOSTEN


class Zinsregeltyp(StrEnum):
    """Typ einer Zinsregel (Kap. 5.2, Tabelle)."""

    GESETZLICH_288_1 = "gesetzlich_288_1"
    GESETZLICH_288_2 = "gesetzlich_288_2"
    KOSTENFESTSETZUNG = "kostenfestsetzung"
    BASISZINS_PLUS = "basiszins_plus"
    FEST = "fest"
    KEINE = "keine"

    @property
    def verzinslich(self) -> bool:
        return self is not Zinsregeltyp.KEINE

    @property
    def basiszinsabhaengig(self) -> bool:
        """Satz hängt vom Basiszinssatz ab; dann wird halbjährlich geteilt (Kap. 5.2 Schritt 2)."""
        return self not in {Zinsregeltyp.FEST, Zinsregeltyp.KEINE}


class Anrechnungsregel(StrEnum):
    """Aktenparameter ``anrechnung`` (Kap. 5.3)."""

    BGB_367 = "bgb_367"
    BGB_497 = "bgb_497"
    INDIVIDUELL = "individuell"


class Tageszaehlung(StrEnum):
    """Aktenparameter ``tageszaehlung`` (Kap. 5.1, E-22, E-31, E-34)."""

    ACT_365 = "act_365"
    ACT_ACT = "act_act"
    ACT_360 = "act_360"
    DREISSIG_360 = "30_360"


class Zinsbeginn(StrEnum):
    """Aktenparameter ``zinsbeginn`` (Kap. 5.1, E-24)."""

    GENANNTER_TAG = "genannter_tag"
    FOLGETAG = "folgetag"


class Zahltag(StrEnum):
    """Aktenparameter ``zahltag`` (Kap. 5.1, E-30)."""

    ALTER_BETRAG = "alter_betrag"
    VERMINDERTER_BETRAG = "verminderter_betrag"


class Teilung(StrEnum):
    """Aktenparameter ``teilung`` (Kap. 5.1, E-32)."""

    KALENDER = "kalender"
    SATZWECHSEL = "satzwechsel"
