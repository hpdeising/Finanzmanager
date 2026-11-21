# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests der Verjährung (Fachkonzept Kap. 5.5, Entscheidungen des Maintainers vom 20.11.2026).

Feiertage aus ``stammdaten/feiertage.yaml``, Land des Haushalts SH. Wochentage der Daten stehen
an den Erwartungen, wo sie zählen.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.kern.stammdaten import (
    StammdatenFehlenError,
    lade_basiszinsreihe,
    lade_feiertagskalender,
)
from app.module.verbindlichkeiten.berechnung import berechne
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Bestandteil,
    Bestandteilart,
    Ereignis,
    Ereignistyp,
    Zahlung,
    Zinsregel,
    Zinsregeltyp,
)
from app.module.verbindlichkeiten.fristen import Fristart
from app.module.verbindlichkeiten.verjaehrung import (
    NeubeginnUmfang,
    Verjaehrung,
    Verjaehrungseinstellungen,
    Verjaehrungsergebnis,
    Verjaehrungsfall,
    verjaehrung_berechnen,
)

T = date
D = Decimal
E = Ereignistyp
KALENDER = lade_feiertagskalender()
STICHTAG = T(2025, 1, 1)
FAELLIG = T(2021, 5, 10)


def hf(
    *,
    faellig_am: date | None = FAELLIG,
    entstanden_am: date | None = None,
    kenntnis_am: date | None = None,
    regeln: tuple[Zinsregel, ...] = (),
) -> Bestandteil:
    return Bestandteil(
        "hauptforderung",
        Bestandteilart.HAUPTFORDERUNG,
        D("1000.00"),
        regeln,
        entstanden_am,
        faellig_am=faellig_am,
        kenntnis_am=kenntnis_am,
    )


def rechne(
    bestandteile: list[Bestandteil],
    *ereignisse: Ereignis,
    stichtag: date = STICHTAG,
    **optionen: Any,
) -> Verjaehrungsergebnis:
    return verjaehrung_berechnen(
        bestandteile,
        list(ereignisse),
        stichtag,
        KALENDER,
        "SH",
        **optionen,
    )


def eintrag(ergebnis: Verjaehrungsergebnis, gegenstand: str = "hauptforderung") -> Verjaehrung:
    (treffer,) = (e for e in ergebnis.eintraege if e.gegenstand == gegenstand)
    return treffer


# --- Nicht titulierte Forderung (§§ 195, 199 Abs. 1 BGB) -----------------------------------------


def test_nicht_tituliert_drei_jahre_ab_schluss_des_jahres_der_faelligkeit() -> None:
    e = eintrag(rechne([hf()]))
    assert e.fall is Verjaehrungsfall.NICHT_TITULIERT
    assert e.norm == "§§ 195, 199 Abs. 1 BGB"
    assert (e.beginn, e.ende) == (T(2022, 1, 1), T(2024, 12, 31))  # Di
    assert e.warnstufen == (T(2024, 12, 1),)  # Fristart information, 30 Tage (Kap. 5.4)


def test_kenntnis_des_glaeubigers_ueberschreibt_die_faelligkeit() -> None:
    e = eintrag(rechne([hf(kenntnis_am=T(2022, 2, 1))]))
    assert e.ende == T(2025, 12, 31)


def test_ohne_faelligkeit_keine_verjaehrung_und_eine_warnung() -> None:
    ergebnis = rechne([hf(faellig_am=None)])
    assert eintrag(ergebnis).ende is None
    assert any("Fälligkeit" in w for w in ergebnis.warnungen)


# --- § 193 BGB (P-01) ----------------------------------------------------------------------------


def test_p01_ende_am_naechsten_werktag_als_voreinstellung() -> None:
    """31.12.2022 ist ein Samstag, 01.01.2023 Sonntag und Neujahr: Ende Montag, 02.01.2023."""
    assert eintrag(rechne([hf(faellig_am=T(2019, 7, 1))])).ende == T(2023, 1, 2)


def test_p01_abschaltbar() -> None:
    einstellungen = Verjaehrungseinstellungen(p01_193_bgb=False)
    ergebnis = rechne([hf(faellig_am=T(2019, 7, 1))], einstellungen=einstellungen)
    assert eintrag(ergebnis).ende == T(2022, 12, 31)


# --- Neubeginn (§ 212 BGB) -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "typ", [E.ZAHLUNG, E.ANERKENNTNIS, E.VOLLSTRECKUNGSANTRAG, E.VOLLSTRECKUNGSHANDLUNG]
)
def test_neubeginn(typ: Ereignistyp) -> None:
    """§ 212 Abs. 1 BGB: Die volle Frist beginnt mit dem Ereignis neu, ohne Jahresschluss."""
    e = eintrag(rechne([hf()], Ereignis(typ, T(2023, 3, 16))))
    assert (e.neubeginn, e.beginn, e.ende) == (T(2023, 3, 16), T(2023, 3, 17), T(2026, 3, 16))


def test_kein_neubeginn_nach_eingetretener_verjaehrung() -> None:
    e = eintrag(rechne([hf()], Ereignis(E.ZAHLUNG, T(2025, 2, 1)), stichtag=T(2025, 6, 1)))
    assert (e.neubeginn, e.ende) == (None, T(2024, 12, 31))


@pytest.mark.parametrize(("zaehlt", "ende"), [(True, T(2026, 3, 16)), (False, T(2024, 12, 31))])
def test_p17_ruecklastschrift(zaehlt: bool, ende: date) -> None:
    """P-17, Voreinstellung (E-36): Eine zurückgegebene Zahlung zählt als Abschlagszahlung."""
    ereignis = Ereignis(E.ZAHLUNG, T(2023, 3, 16), zurueckgegeben=True)
    einstellungen = Verjaehrungseinstellungen(p17_ruecklastschrift_neubeginn=zaehlt)
    assert eintrag(rechne([hf()], ereignis, einstellungen=einstellungen)).ende == ende


def test_p02_voreinstellung_alle_bestandteile() -> None:
    kosten = Bestandteil(
        "kosten_verfahren", Bestandteilart.KOSTEN_VERFAHREN, D("50.00"), faellig_am=T(2021, 5, 10)
    )
    ergebnis = rechne([hf(), kosten], Ereignis(E.ZAHLUNG, T(2023, 3, 16)))
    assert {e.gegenstand: e.ende for e in ergebnis.eintraege} == {
        "hauptforderung": T(2026, 3, 16),
        "kosten_verfahren": T(2026, 3, 16),
    }


def test_p02_nur_angerechnete_bestandteile() -> None:
    """P-02 einstellbar: Eine Zahlung beginnt die Verjährung nur für die Bestandteile neu, auf
    die sie angerechnet wird (hier nur die Kosten, § 367 Abs. 1 BGB)."""
    kosten = Bestandteil(
        "kosten_verfahren", Bestandteilart.KOSTEN_VERFAHREN, D("50.00"), faellig_am=T(2021, 5, 10)
    )
    anrechnungen = berechne(
        Aktenparameter(),
        [hf(), kosten],
        [Zahlung(T(2023, 3, 16), D("20.00"))],
        T(2023, 3, 16),
        lade_basiszinsreihe(),
    ).anrechnungen
    ergebnis = rechne(
        [hf(), kosten],
        Ereignis(E.ZAHLUNG, T(2023, 3, 16)),
        einstellungen=Verjaehrungseinstellungen(p02_neubeginn=NeubeginnUmfang.ANGERECHNETE),
        anrechnungen=anrechnungen,
    )
    assert {e.gegenstand: e.ende for e in ergebnis.eintraege} == {
        "hauptforderung": T(2024, 12, 31),
        "kosten_verfahren": T(2026, 3, 16),
    }


# --- Hemmung (§ 204 Abs. 1 Nr. 3, Abs. 2, § 209 BGB) ---------------------------------------------


@pytest.mark.parametrize("typ", [E.MAHNVERFAHREN_OHNE_TITEL_BEENDET, E.LETZTE_VERFAHRENSHANDLUNG])
def test_hemmung_endet_sechs_monate_nach_beendigung_oder_stillstand(typ: Ereignistyp) -> None:
    """Gehemmt vom 03.06.2024 bis 01.02.2025: 244 Tage zählen nicht (§ 209 BGB)."""
    ergebnis = rechne(
        [hf()],
        Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2024, 6, 3)),
        Ereignis(typ, T(2024, 8, 1)),
        stichtag=T(2025, 6, 1),
    )
    e = eintrag(ergebnis)
    assert (e.hemmungstage, e.ende) == (244, T(2025, 9, 1))  # Mo


def test_laufende_hemmung_ohne_ende() -> None:
    e = eintrag(rechne([hf()], Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2024, 6, 3))))
    assert e.ende is None
    assert any("gehemmt" in h for h in e.hinweise)


def test_hemmung_bei_verbraucherdarlehen_ab_verzug() -> None:
    """§ 497 Abs. 3 BGB: gehemmt ab Verzug bis zur Titulierung, höchstens zehn Jahre ab
    Entstehung (15.01.2019 bis 15.01.2029). Gezählt ab Beginn der Verjährung am 01.01.2020."""
    ergebnis = rechne(
        [hf(faellig_am=T(2019, 5, 1), entstanden_am=T(2019, 1, 15))],
        Ereignis(E.VERZUG_EINGETRETEN, T(2019, 6, 1)),
        verbraucherdarlehen=True,
    )
    e = eintrag(ergebnis)
    assert (e.hemmungstage, e.ende) == (3303, T(2032, 1, 16))  # Fr


# --- Titel (§ 197 Abs. 1, § 201 BGB) -------------------------------------------------------------


def test_vollstreckungsbescheid_rechtskraft_berechnet() -> None:
    """Zustellung Mo 02.05.2022, Einspruchsfrist bis Mo 16.05.2022, rechtskräftig mit dem
    Folgetag; die Hemmung durch den Mahnbescheid endet mit der Rechtskraft."""
    ergebnis = rechne(
        [hf()],
        Ereignis(E.ZUSTELLUNG_MAHNBESCHEID, T(2022, 3, 1)),
        Ereignis(E.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID, T(2022, 5, 2)),
    )
    e = eintrag(ergebnis)
    assert e.fall is Verjaehrungsfall.RECHTSKRAEFTIG_FESTGESTELLT
    assert e.norm == "§ 197 Abs. 1 Nr. 3, § 201 BGB; § 700 Abs. 1 ZPO"
    assert (e.beginn, e.ende) == (T(2022, 5, 18), T(2052, 5, 17))
    assert any("berechnet" in h for h in e.hinweise)
    assert not any("Feiertage" in h for h in e.hinweise)  # Kalender reicht bis 2080


def test_erfasste_rechtskraft_hat_vorrang() -> None:
    ergebnis = rechne(
        [hf()],
        Ereignis(E.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID, T(2022, 5, 2)),
        Ereignis(E.RECHTSKRAFT, T(2022, 6, 1)),
    )
    assert eintrag(ergebnis).ende == T(2052, 6, 3)  # 01.06.2052 ist ein Samstag (P-01)


def test_kostenfestsetzungsbeschluss_rechtskraft_berechnet() -> None:
    """Entscheidung vom 21.11.2026: 30 Jahre ab Rechtskraft (§ 197 Abs. 1 Nr. 3, § 201 BGB).
    Zustellung Mo 02.05.2022, Frist der sofortigen Beschwerde bis Mo 16.05.2022 (§ 104 Abs. 3,
    § 569 Abs. 1 ZPO), rechtskräftig mit dem Folgetag."""
    ergebnis = rechne([hf()], Ereignis(E.ZUSTELLUNG_KOSTENFESTSETZUNGSBESCHLUSS, T(2022, 5, 2)))
    e = eintrag(ergebnis)
    assert e.fall is Verjaehrungsfall.KOSTENFESTSETZUNGSBESCHLUSS
    assert e.norm == "§ 197 Abs. 1 Nr. 3, § 201 BGB"
    assert (e.beginn, e.ende) == (T(2022, 5, 18), T(2052, 5, 17))
    assert any("berechnet" in h for h in e.hinweise)


def test_kostenfestsetzungsbeschluss_erfasste_rechtskraft_hat_vorrang() -> None:
    ergebnis = rechne(
        [hf()],
        Ereignis(E.ZUSTELLUNG_KOSTENFESTSETZUNGSBESCHLUSS, T(2022, 5, 2)),
        Ereignis(E.RECHTSKRAFT, T(2022, 6, 1)),
    )
    e = eintrag(ergebnis)
    assert e.fall is Verjaehrungsfall.KOSTENFESTSETZUNGSBESCHLUSS
    assert e.ende == T(2052, 6, 3)  # 01.06.2052 ist ein Samstag (P-01)


def test_kostenfestsetzungsbeschluss_mit_beschwerde_ohne_rechtskraft_warnt() -> None:
    ergebnis = rechne(
        [hf()],
        Ereignis(E.ZUSTELLUNG_KOSTENFESTSETZUNGSBESCHLUSS, T(2022, 5, 2)),
        Ereignis(E.SOFORTIGE_BESCHWERDE, T(2022, 5, 10)),
    )
    assert eintrag(ergebnis).ende is None
    assert any("Rechtskraft" in w for w in ergebnis.warnungen)


def test_anderer_titel_geht_dem_kostenfestsetzungsbeschluss_vor() -> None:
    ergebnis = rechne(
        [hf()],
        Ereignis(E.ERRICHTUNG_TITEL, T(2022, 4, 1)),
        Ereignis(E.ZUSTELLUNG_KOSTENFESTSETZUNGSBESCHLUSS, T(2022, 5, 2)),
    )
    assert eintrag(ergebnis).fall is Verjaehrungsfall.VERGLEICH_URKUNDE


def test_einspruch_ohne_rechtskraft_warnt() -> None:
    ergebnis = rechne(
        [hf()],
        Ereignis(E.ZUSTELLUNG_VOLLSTRECKUNGSBESCHEID, T(2022, 5, 2)),
        Ereignis(E.EINSPRUCH, T(2022, 5, 10)),
    )
    assert eintrag(ergebnis).ende is None
    assert any("Rechtskraft" in w for w in ergebnis.warnungen)


def test_urteil_braucht_die_rechtskraft() -> None:
    mit = rechne(
        [hf()],
        Ereignis(E.ZUSTELLUNG_URTEIL, T(2023, 2, 1)),
        Ereignis(E.RECHTSKRAFT, T(2023, 4, 3)),
    )
    assert eintrag(mit).ende == T(2053, 4, 3)
    ohne = rechne([hf()], Ereignis(E.ZUSTELLUNG_URTEIL, T(2023, 2, 1)))
    assert eintrag(ohne).ende is None
    assert any("Rechtskraft" in w for w in ohne.warnungen)


def test_vergleich_oder_urkunde_ab_errichtung() -> None:
    e = eintrag(rechne([hf()], Ereignis(E.ERRICHTUNG_TITEL, T(2024, 6, 15))))
    assert e.fall is Verjaehrungsfall.VERGLEICH_URKUNDE
    assert e.norm == "§ 197 Abs. 1 Nr. 4, § 201 BGB"
    assert e.ende == T(2054, 6, 15)


def test_kosten_der_zwangsvollstreckung_ab_entstehung() -> None:
    kosten = Bestandteil(
        "kosten_vollstreckung",
        Bestandteilart.KOSTEN_VOLLSTRECKUNG,
        D("80.00"),
        entstanden_am=T(2019, 6, 15),
    )
    e = eintrag(rechne([kosten]), "kosten_vollstreckung")
    assert e.fall is Verjaehrungsfall.KOSTEN_ZWANGSVOLLSTRECKUNG
    assert e.norm == "§ 197 Abs. 1 Nr. 6, § 201 BGB"
    assert e.ende == T(2049, 6, 15)  # Di


# --- Zinsen (§ 197 Abs. 2 BGB, § 497 Abs. 3 BGB) -------------------------------------------------


def _mit_zinsen(verbraucherdarlehen: bool) -> Verjaehrungsergebnis:
    zinsen = (Zinsregel(Zinsregeltyp.FEST, ab=T(2022, 1, 1), satz=D(5)),)
    bestandteil = hf(regeln=zinsen)
    stichtag = T(2025, 6, 30)
    abschnitte = berechne(
        Aktenparameter(), [bestandteil], [], stichtag, lade_basiszinsreihe()
    ).abschnitte
    return rechne(
        [bestandteil],
        Ereignis(E.ERRICHTUNG_TITEL, T(2022, 6, 15)),
        stichtag=stichtag,
        abschnitte=abschnitte,
        verbraucherdarlehen=verbraucherdarlehen,
    )


def test_laufende_zinsen_nach_titulierung_je_kalenderjahr() -> None:
    """Entscheidung 5: je Kalenderjahr der Entstehung, Ende mit Ablauf des 31.12. des dritten
    Folgejahres. Zinsen bis zur Titulierung gehören zum Titel."""
    ergebnis = _mit_zinsen(verbraucherdarlehen=False)
    enden = {e.gegenstand: (e.fall, e.ende) for e in ergebnis.eintraege}
    assert enden == {
        # 15.06.2052 ist ein Samstag: Montag, 17.06.2052 (P-01)
        "hauptforderung": (Verjaehrungsfall.VERGLEICH_URKUNDE, T(2052, 6, 17)),
        "hauptforderung: Zinsen bis Titulierung": (
            Verjaehrungsfall.VERGLEICH_URKUNDE,
            T(2052, 6, 17),
        ),
        "hauptforderung: Zinsen 2022": (Verjaehrungsfall.LAUFENDE_ZINSEN, T(2025, 12, 31)),
        "hauptforderung: Zinsen 2023": (Verjaehrungsfall.LAUFENDE_ZINSEN, T(2026, 12, 31)),
        "hauptforderung: Zinsen 2024": (Verjaehrungsfall.LAUFENDE_ZINSEN, T(2027, 12, 31)),
        # 31.12.2028 ist ein Sonntag, 01.01.2029 Neujahr: § 193 BGB (P-01)
        "hauptforderung: Zinsen 2025": (Verjaehrungsfall.LAUFENDE_ZINSEN, T(2029, 1, 2)),
    }
    assert (
        eintrag(ergebnis, "hauptforderung: Zinsen 2022").norm
        == "§ 197 Abs. 2, §§ 195, 199 Abs. 1 BGB"
    )


def test_zinsen_nach_titulierung_bei_verbraucherdarlehen_dreissig_jahre() -> None:
    ergebnis = _mit_zinsen(verbraucherdarlehen=True)
    e = eintrag(ergebnis, "hauptforderung: Zinsen ab Titulierung")
    assert (e.fall, e.norm, e.ende) == (
        Verjaehrungsfall.VERBRAUCHERDARLEHEN_ZINSEN,
        "§ 497 Abs. 3 BGB",
        T(2052, 6, 17),
    )
    assert not any("Zinsen 20" in e.gegenstand for e in ergebnis.eintraege)


def test_ohne_feiertage_fehler_statt_schaetzung() -> None:
    """Entscheidung vom 21.11.2026: Der Kalender reicht bis 2080; danach gilt wieder Fehler statt
    Schätzung. Errichtung 15.06.2051, Ende 15.06.2081."""
    with pytest.raises(StammdatenFehlenError):
        rechne([hf()], Ereignis(E.ERRICHTUNG_TITEL, T(2051, 6, 15)), stichtag=T(2052, 1, 1))


def test_verjaehrung_ist_eine_information() -> None:
    """Kap. 5.4 (Entscheidung vom 20.11.2026): Fristart information, Warnung 30 Tage vorher."""
    assert eintrag(rechne([hf()])).art is Fristart.INFORMATION
