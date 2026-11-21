# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests des Abgleichs mit der Forderungsaufstellung (Fachkonzept Kap. 5.3).

Die Programmwerte der Fälle hier prüft schon ``test_berechnung.py``; die Aufstellungen weichen
davon gezielt ab. Werte der Aufstellung stehen als Text wie in den CSV-Dateien aus Kap. 12.
"""

from datetime import date
from decimal import Decimal

from app.kern.stammdaten import lade_basiszinsreihe
from app.module.verbindlichkeiten.abgleich import (
    Abgleich,
    Aufstellung,
    Bereich,
    Kostenposition,
    Position,
    Ursache,
    gleiche_ab,
)
from app.module.verbindlichkeiten.domain import (
    Aktenparameter,
    Bestandteil,
    Bestandteilart,
    Zahlung,
    Zinsregel,
    Zinsregeltyp,
)

T = date
D = Decimal
REIHE = lade_basiszinsreihe()

RW = Bereich.RECHENWEG
AN = Bereich.ANRECHNUNG
SU = Bereich.SUMME
KO = Bereich.KOSTEN


def fest(ab: date, satz: str = "10") -> Zinsregel:
    return Zinsregel(Zinsregeltyp.FEST, ab=ab, satz=D(satz))


def hf(betrag: str, *regeln: Zinsregel) -> Bestandteil:
    return Bestandteil("hauptforderung", Bestandteilart.HAUPTFORDERUNG, D(betrag), regeln)


def kosten(betrag: str) -> Bestandteil:
    return Bestandteil("kosten_verfahren", Bestandteilart.KOSTEN_VERFAHREN, D(betrag))


def abgleich(
    bestandteile: list[Bestandteil],
    zahlungen: list[tuple[date, str]],
    aufstellung: Aufstellung,
    parameter: Aktenparameter | None = None,
) -> Abgleich:
    return gleiche_ab(
        parameter or Aktenparameter(),
        bestandteile,
        [Zahlung(tag, D(betrag)) for tag, betrag in zahlungen],
        aufstellung,
        REIHE,
    )


def positionen(ergebnis: Abgleich) -> dict[Position, tuple[str | None, str | None]]:
    return {a.position: (a.laut_aufstellung, a.programm) for a in ergebnis.abweichungen}


def ursachen(ergebnis: Abgleich, position: Position) -> frozenset[Ursache]:
    (treffer,) = (a for a in ergebnis.abweichungen if a.position == position)
    return treffer.ursachen


# Formatbeispiel aus Kap. 12: 1000,00 € zu 5 % fest ab 15.03.2025, Zahlung 200,00 € am 20.05.2025.
BEISPIEL = ([hf("1000.00", fest(T(2025, 3, 15), "5"))], [(T(2025, 5, 20), "200.00")])
BEISPIEL_RECHENWEG = (
    {
        "bestandteil": "hauptforderung",
        "von": "2025-03-15",
        "bis": "2025-05-20",
        "grund": "zinsbeginn",
        "tage": "67",
        "tagesbasis": "365",
        "basis": "1000.00",
        "basiszins": "",
        "satz": "5",
        "zins_ungerundet": "9.178082",
        "zins_gerundet": "9.18",
    },
    {
        "bestandteil": "hauptforderung",
        "von": "2025-05-21",
        "bis": "2025-06-30",
        "grund": "zahlung",
        "tage": "41",
        "tagesbasis": "365",
        "basis": "809.18",
        "basiszins": "",
        "satz": "5",
        "zins_ungerundet": "4.544709",
        "zins_gerundet": "4.54",
    },
)
BEISPIEL_ANRECHNUNG = (
    {
        "zahlung": "2025-05-20",
        "betrag": "200.00",
        "bestandteil": "hauptforderung",
        "gruppe": "zinsen",
        "angerechnet": "9.18",
        "offen_danach": "0.00",
    },
    {
        "zahlung": "2025-05-20",
        "betrag": "200.00",
        "bestandteil": "hauptforderung",
        "gruppe": "hauptforderung",
        "angerechnet": "190.82",
        "offen_danach": "809.18",
    },
)
BEISPIEL_SUMMEN = {
    "hauptforderung": "809.18",
    "zinsen": "4.54",
    "kosten": "0.00",
    "gesamt": "813.72",
}


def test_uebereinstimmende_aufstellung_hat_keine_abweichung() -> None:
    aufstellung = Aufstellung(
        T(2025, 6, 30), BEISPIEL_SUMMEN, BEISPIEL_RECHENWEG, BEISPIEL_ANRECHNUNG
    )
    assert abgleich(*BEISPIEL, aufstellung).abweichungen == ()


def test_nicht_genannte_werte_werden_nicht_verglichen() -> None:
    zeilen = ({"von": "2025-03-15", "zins_gerundet": "9.18", "tage": ""}, {"basis": "809.18"})
    aufstellung = Aufstellung(T(2025, 6, 30), {"hauptforderung": "809.18"}, zeilen)
    assert abgleich(*BEISPIEL, aufstellung).abweichungen == ()


def test_rechenfehler_der_aufstellung_hat_keine_bekannte_ursache() -> None:
    """Gleiche Tage, Basis und Satz, aber anderer Zins: keine der Ursachen aus Kap. 5.3."""
    zeile = {**BEISPIEL_RECHENWEG[0], "zins_gerundet": "9.20"}
    summen = {**BEISPIEL_SUMMEN, "zinsen": "4.56", "gesamt": "813.74"}
    zeilen = (zeile, BEISPIEL_RECHENWEG[1])
    ergebnis = abgleich(*BEISPIEL, Aufstellung(T(2025, 6, 30), summen, zeilen))
    assert positionen(ergebnis) == {
        Position(RW, "zins_gerundet", 1): ("9.20", "9.18"),
        Position(SU, "zinsen"): ("4.56", "4.54"),
        Position(SU, "gesamt"): ("813.74", "813.72"),
    }
    assert all(a.ursachen == frozenset() for a in ergebnis.abweichungen)
    assert ergebnis.ursachen == frozenset()


def test_andere_tageszaehlung() -> None:
    """3650,00 € zu 10 % für 10 Tage: act_365 10,00 €, act_360 10,14 € (36500 / 3600)."""
    zeile = {"von": "2025-01-01", "tagesbasis": "360", "zins_gerundet": "10.14"}
    ergebnis = abgleich(
        [hf("3650.00", fest(T(2025, 1, 1)))], [], Aufstellung(T(2025, 1, 10), {}, (zeile,))
    )
    assert set(positionen(ergebnis)) == {
        Position(RW, "tagesbasis", 1),
        Position(RW, "zins_gerundet", 1),
    }
    for a in ergebnis.abweichungen:
        assert Ursache.TAGESZAEHLUNG in a.ursachen


def test_anderer_zahltag() -> None:
    """Programm: alter_betrag; Aufstellung: verminderter_betrag (Werte aus test_berechnung)."""
    rechenweg = (
        {"von": "2025-01-01", "bis": "2025-01-10", "tage": "10", "zins_gerundet": "10.00"},
        {"von": "2025-01-11", "bis": "2025-01-20", "basis": "3285.00", "zins_gerundet": "9.00"},
    )
    ergebnis = abgleich(
        [hf("3650.00", fest(T(2025, 1, 1)))],
        [(T(2025, 1, 11), "375.00")],
        Aufstellung(T(2025, 1, 20), {}, rechenweg),
    )
    assert Position(RW, "bis", 1) in positionen(ergebnis)
    assert positionen(ergebnis)[Position(RW, "basis", 2)] == ("3285.00", "3286.00")
    for a in ergebnis.abweichungen:
        assert Ursache.ZAHLTAG in a.ursachen
    assert Ursache.TEILUNG in ursachen(ergebnis, Position(RW, "bis", 1))


def test_andere_anrechnungsreihenfolge() -> None:
    """Programm bgb_367 (Kosten, Zinsen, Hauptforderung); Aufstellung nach bgb_497."""
    anrechnung = (
        {"zahlung": "2025-01-10", "betrag": "100.00", "gruppe": "kosten", "angerechnet": "50.00"},
        {"gruppe": "hauptforderung", "angerechnet": "50.00", "offen_danach": "3600.00"},
    )
    ergebnis = abgleich(
        [hf("3650.00", fest(T(2025, 1, 1))), kosten("50.00")],
        [(T(2025, 1, 10), "100.00")],
        Aufstellung(T(2025, 1, 10), {"hauptforderung": "3600.00"}, (), anrechnung),
    )
    assert positionen(ergebnis) == {
        Position(AN, "gruppe", 2): ("hauptforderung", "zinsen"),
        Position(AN, "angerechnet", 2): ("50.00", "10.00"),
        Position(AN, "offen_danach", 2): ("3600.00", "0.00"),
        Position(AN, "zahlung", 3): (None, "2025-01-10"),
        Position(SU, "hauptforderung"): ("3600.00", "3610.00"),
    }
    for a in ergebnis.abweichungen:
        assert Ursache.ANRECHNUNGSREIHENFOLGE in a.ursachen


def test_anderer_zinssatz() -> None:
    zeilen = ({**BEISPIEL_RECHENWEG[0], "satz": "6"}, BEISPIEL_RECHENWEG[1])
    ergebnis = abgleich(*BEISPIEL, Aufstellung(T(2025, 6, 30), {}, zeilen))
    assert positionen(ergebnis) == {Position(RW, "satz", 1): ("6", "5")}
    assert ursachen(ergebnis, Position(RW, "satz", 1)) == {Ursache.ZINSSATZ}


def test_unbekannte_und_abweichende_kosten() -> None:
    aufstellung = Aufstellung(
        T(2025, 1, 10),
        {"kosten": "90.00"},
        kosten=(
            Kostenposition("kosten_verfahren", "60.00"),
            Kostenposition(None, "30.00"),
        ),
    )
    ergebnis = abgleich([hf("1000.00"), kosten("50.00")], [], aufstellung)
    assert positionen(ergebnis) == {
        Position(KO, "betrag", 1): ("60.00", "50.00"),
        Position(KO, "betrag", 2): ("30.00", None),
        Position(SU, "kosten"): ("90.00", "50.00"),
    }
    assert ursachen(ergebnis, Position(KO, "betrag", 1)) == frozenset()
    assert ursachen(ergebnis, Position(KO, "betrag", 2)) == {Ursache.UNBEKANNTE_KOSTEN}
    assert Ursache.UNBEKANNTE_KOSTEN in ursachen(ergebnis, Position(SU, "kosten"))


def test_fehlende_zahlung() -> None:
    """Die Aufstellung verrechnet eine Zahlung, die das Programm nicht kennt."""
    anrechnung = (
        {
            "zahlung": "2025-01-05",
            "betrag": "100.00",
            "bestandteil": "hauptforderung",
            "gruppe": "zinsen",
            "angerechnet": "5.00",
        },
    )
    ergebnis = abgleich(
        [hf("3650.00", fest(T(2025, 1, 1)))],
        [],
        Aufstellung(T(2025, 1, 10), {"hauptforderung": "3555.00"}, (), anrechnung),
    )
    assert Position(AN, "zahlung", 1) in positionen(ergebnis)
    assert positionen(ergebnis)[Position(SU, "hauptforderung")] == ("3555.00", "3650.00")
    for a in ergebnis.abweichungen:
        assert Ursache.FEHLENDE_ZAHLUNGEN in a.ursachen


def test_andere_teilung() -> None:
    """Programm teilt nach Kalender am 01.01.2026; die Aufstellung nur bei Satzwechsel
    (01.07.2025 und 01.01.2026 haben beide 1,27 %)."""
    zeile = {"von": "2025-07-01", "bis": "2026-03-31", "tage": "274"}
    ergebnis = abgleich(
        [hf("1000.00", Zinsregel(Zinsregeltyp.GESETZLICH_288_1, ab=T(2025, 7, 1)))],
        [],
        Aufstellung(T(2026, 3, 31), {}, (zeile,)),
    )
    assert positionen(ergebnis)[Position(RW, "bis", 1)] == ("2026-03-31", "2025-12-31")
    assert Position(RW, "von", 2) in positionen(ergebnis)
    for a in ergebnis.abweichungen:
        assert Ursache.TEILUNG in a.ursachen


def test_fehlende_zeilen_der_aufstellung_deuten_auf_andere_teilung() -> None:
    """Nennt die Aufstellung Zeilen des Rechenwegs, gelten sie als vollständig."""
    ergebnis = abgleich(*BEISPIEL, Aufstellung(T(2025, 6, 30), {}, (BEISPIEL_RECHENWEG[0],)))
    assert positionen(ergebnis) == {Position(RW, "von", 2): (None, "2025-05-21")}
    assert ursachen(ergebnis, Position(RW, "von", 2)) == {Ursache.TEILUNG}


def test_ursachen_des_abgleichs_sind_die_vereinigung() -> None:
    zeilen = ({**BEISPIEL_RECHENWEG[0], "satz": "6"}, BEISPIEL_RECHENWEG[1])
    aufstellung = Aufstellung(T(2025, 6, 30), {}, zeilen, kosten=(Kostenposition(None, "1.00"),))
    ergebnis = abgleich(*BEISPIEL, aufstellung)
    assert ergebnis.ursachen == {Ursache.ZINSSATZ, Ursache.UNBEKANNTE_KOSTEN}


def test_anderer_zinsbeginn() -> None:
    """Programm: genannter Tag; Aufstellung: Folgetag (erster Zinstag 02.01., 9 Tage, 9,00 €)."""
    zeile = {"von": "2025-01-02", "tage": "9", "zins_gerundet": "9.00"}
    ergebnis = abgleich(
        [hf("3650.00", fest(T(2025, 1, 1)))], [], Aufstellung(T(2025, 1, 10), {}, (zeile,))
    )
    assert set(positionen(ergebnis)) == {
        Position(RW, "von", 1),
        Position(RW, "tage", 1),
        Position(RW, "zins_gerundet", 1),
    }
    for a in ergebnis.abweichungen:
        assert Ursache.ZINSBEGINN in a.ursachen


def test_anzeige_der_ursachen() -> None:
    """Ohne Ursache zeigt der Abgleich „keine Ursache gefunden“ (Entscheidung vom 20.11.2026)."""
    zeilen = ({**BEISPIEL_RECHENWEG[0], "zins_gerundet": "9.20"}, BEISPIEL_RECHENWEG[1])
    ohne = abgleich(*BEISPIEL, Aufstellung(T(2025, 6, 30), {}, zeilen)).abweichungen[0]
    assert ohne.ursachen_anzeige == ("keine Ursache gefunden",)
    zeilen = ({**BEISPIEL_RECHENWEG[0], "satz": "6"}, BEISPIEL_RECHENWEG[1])
    mit = abgleich(*BEISPIEL, Aufstellung(T(2025, 6, 30), {}, zeilen)).abweichungen[0]
    assert mit.ursachen_anzeige == ("Zinssatz",)


def test_jede_ursache_hat_eine_anzeige() -> None:
    assert {u.anzeige for u in Ursache} == {
        "Zinssatz",
        "Tageszählung",
        "Zinsbeginn",
        "Zahltag",
        "Teilung der Abschnitte",
        "Anrechnungsreihenfolge",
        "unbekannte Kosten",
        "fehlende Zahlungen",
    }
