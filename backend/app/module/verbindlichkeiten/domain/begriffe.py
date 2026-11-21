# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fachbegriffe als Aufzählungen, mit den Werten aus Fachkonzept Kap. 4.5, 5.1 bis 5.3."""

from enum import StrEnum


class Gruppe(StrEnum):
    """Gruppe, auf die eine Zahlung angerechnet wird (Kap. 5.3)."""

    KOSTEN = "kosten"
    ZINSEN = "zinsen"
    HAUPTFORDERUNG = "hauptforderung"


class Grund(StrEnum):
    """Warum ein Abschnitt beginnt (Kap. 5.2 Schritte 1 und 2, Kap. 12 Spalte ``grund``).

    Die Reihenfolge der Werte ist die, in der mehrere Gründe stehen; ``zinsbeginn`` steht allein.
    """

    ZINSBEGINN = "zinsbeginn"
    HALBJAHR = "halbjahr"
    JAHRESWECHSEL = "jahreswechsel"
    TEILUNGSTAG = "teilungstag"
    ZAHLUNG = "zahlung"
    REGELWECHSEL = "regelwechsel"


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


class Ereignistyp(StrEnum):
    """Ereignistypen in Release 1 (Kap. 4.5)."""

    ZUSTELLUNG_MAHNBESCHEID = "zustellung_mahnbescheid"
    ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID = "zustellung_vollstreckungsbescheid"
    ZUSTELLUNG_URTEIL = "zustellung_urteil"
    RECHTSKRAFT = "rechtskraft"
    ERRICHTUNG_TITEL = "errichtung_titel"
    EINTRAGUNGSANORDNUNG = "eintragungsanordnung"
    ZAHLUNG = "zahlung"
    VOLLSTRECKUNGSANTRAG = "vollstreckungsantrag"
    VOLLSTRECKUNGSHANDLUNG = "vollstreckungshandlung"
    ANERKENNTNIS = "anerkenntnis"
    GLAEUBIGERWECHSEL = "glaeubigerwechsel"
    ANRECHNUNG_ABGELEHNT = "anrechnung_abgelehnt"
    AUSGLEICH = "ausgleich"
    QUITTUNG_ERHALTEN = "quittung_erhalten"
    TITEL_ERHALTEN = "titel_erhalten"
    LOESCHUNG_SCHULDNERVERZEICHNIS = "loeschung_schuldnerverzeichnis"
    ERLEDIGT_GEMELDET_AUSKUNFTEI = "erledigt_gemeldet_auskunftei"
    VERJAEHRUNG_EINGEWANDT = "verjaehrung_eingewandt"
    # Ergänzt am 20.11.2026 für die Verjährung (Kap. 5.5)
    EINSPRUCH = "einspruch"
    MAHNVERFAHREN_OHNE_TITEL_BEENDET = "mahnverfahren_ohne_titel_beendet"
    LETZTE_VERFAHRENSHANDLUNG = "letzte_verfahrenshandlung"
    VERZUG_EINGETRETEN = "verzug_eingetreten"
    # Ergänzt am 20.11.2026 für das Statusmodell (Kap. 6)
    ZUSTELLUNG_KOSTENFESTSETZUNGSBESCHLUSS = "zustellung_kostenfestsetzungsbeschluss"
    AKTE_GESCHLOSSEN = "akte_geschlossen"
    RATENPLAN_VEREINBART = "ratenplan_vereinbart"
    RATENPLAN_BEENDET = "ratenplan_beendet"
    VOLLSTRECKUNGSMASSNAHME_BEGONNEN = "vollstreckungsmassnahme_begonnen"
    VOLLSTRECKUNGSMASSNAHME_AUFGEHOBEN = "vollstreckungsmassnahme_aufgehoben"
    FORDERUNG_BESTRITTEN = "forderung_bestritten"
    BESTREITEN_BEENDET = "bestreiten_beendet"
    # Ergänzt am 21.11.2026 für die Verjährung des Kostenfestsetzungsbeschlusses (Kap. 5.5)
    SOFORTIGE_BESCHWERDE = "sofortige_beschwerde"
    # Ergänzt am 21.11.2026: Erinnerung gegen den Kostenfestsetzungsbeschluss (Kap. 5.4, 5.5)
    ERINNERUNG = "erinnerung"

    @property
    def ist_zustellung(self) -> bool:
        return self.value.startswith("zustellung_")
