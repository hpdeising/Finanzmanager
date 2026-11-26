# SPDX-License-Identifier: AGPL-3.0-or-later
"""Importläufe: speichern, Duplikate, gebucht markieren, abschließen (Fachkonzept Kap. 8).

Gegen PostgreSQL; jeder Test wird zurückgerollt. Alle Namen, IBANs und Beträge sind erfunden.
"""

import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.kern.haushalt import lege_haushalt_an
from app.kern.import_ import (
    CsvProfil,
    Format,
    ImportLauf,
    ImportUngueltigError,
    ImportZeile,
    ImportZeileBuchung,
    LaufAbgeschlossenError,
    LaufUnbekanntError,
    ProfilUnbekanntError,
    ProfilUngueltigError,
    ProfilVorhandenError,
    Richtung,
    Umsatz,
    WertstellungAus,
    ZeileNichtBuchbarError,
    ZeileUnbekanntError,
    importiere,
    kandidaten,
    laeufe,
    lauf,
    lies_datei,
    loesche_profil,
    markiere_gebucht,
    profil,
    profile,
    schliesse_ab,
    speichere_profil,
)
from app.kern.ledger import EXTERNE_MITTEL, PostingEingabe, buche, lege_konto_an, storniere

IBAN = "DE02120300000000202051"


def umsatz(
    betrag: str = "150.00",
    *,
    tag: date = date(2025, 2, 3),
    valuta: date | None = date(2025, 2, 4),
    richtung: Richtung = Richtung.BELASTUNG,
    zweck: str = "AZ 4711 Rate 2",
    rueckbuchung: bool = False,
) -> Umsatz:
    return Umsatz(
        buchungstag=tag,
        valuta=valuta,
        betrag=Decimal(betrag),
        richtung=richtung,
        gegen_name="Muster Inkasso GmbH",
        gegen_iban="de02 1203 0000 0000 2020 51",
        verwendungszweck=zweck,
        rueckbuchung=rueckbuchung,
    )


@pytest.fixture
def haushalt_id(session: Session) -> uuid.UUID:
    return lege_haushalt_an(session, betriebsart="einzel").id


def camt(
    session: Session,
    haushalt_id: uuid.UUID,
    *umsaetze: Umsatz,
    aus: WertstellungAus = WertstellungAus.VALUTA,
) -> ImportLauf:
    return importiere(
        session,
        haushalt_id=haushalt_id,
        umsaetze=umsaetze,
        dateiformat=Format.CAMT053,
        profil_name=None,
        wertstellung_aus=aus,
    )


class Konten:
    def __init__(self, session: Session, haushalt_id: uuid.UUID) -> None:
        self.session = session
        self.haushalt_id = haushalt_id
        self.extern = lege_konto_an(
            session,
            haushalt_id=haushalt_id,
            kontoart="eigenkapital",
            rolle=EXTERNE_MITTEL,
            bezeichnung="Externe Mittel",
        ).id
        self.zahlungen = lege_konto_an(
            session,
            haushalt_id=haushalt_id,
            kontoart="passiv",
            rolle="test.zahlungen",
            bezeichnung="Zahlungen",
        ).id

    def zahlung(self, betrag: str, wertstellung: date = date(2025, 2, 4)) -> uuid.UUID:
        """Wie eine Zahlung im Modul: Soll Zahlungen, Haben Externe Mittel (Kap. 4.3)."""
        return buche(
            self.session,
            haushalt_id=self.haushalt_id,
            art="test.zahlung",
            wertstellung=wertstellung,
            postings=[
                PostingEingabe(self.zahlungen, Decimal(betrag)),
                PostingEingabe(self.extern, -Decimal(betrag)),
            ],
        ).id


# --- CSV-Profile ------------------------------------------------------------------------------

PROFIL = CsvProfil(
    name="Beispielbank",
    spalte_buchungstag="Buchungstag",
    spalte_valuta="Valuta",
    spalte_betrag="Betrag",
    spalte_gegen_name="Empfänger",
    spalte_gegen_iban="IBAN",
    spalten_verwendungszweck=("Verwendungszweck", "Zusatz"),
    tausendertrennzeichen=None,
    kopfzeilen_ueberspringen=2,
)


def test_profil_speichern_lesen_loeschen(session: Session, haushalt_id: uuid.UUID) -> None:
    profil_id = speichere_profil(session, haushalt_id=haushalt_id, profil=PROFIL)
    assert profil(session, haushalt_id, profil_id) == PROFIL
    assert profile(session, haushalt_id) == [(profil_id, PROFIL)]
    loesche_profil(session, haushalt_id, profil_id)
    assert profile(session, haushalt_id) == []
    with pytest.raises(ProfilUnbekanntError):
        profil(session, haushalt_id, profil_id)


def test_profil_name_je_haushalt_einmal(session: Session, haushalt_id: uuid.UUID) -> None:
    speichere_profil(session, haushalt_id=haushalt_id, profil=PROFIL)
    with pytest.raises(ProfilVorhandenError):
        speichere_profil(session, haushalt_id=haushalt_id, profil=PROFIL)
    anderer = lege_haushalt_an(session, betriebsart="einzel").id
    speichere_profil(session, haushalt_id=anderer, profil=PROFIL)


def test_profil_eines_anderen_haushalts_ist_unbekannt(
    session: Session, haushalt_id: uuid.UUID
) -> None:
    profil_id = speichere_profil(session, haushalt_id=haushalt_id, profil=PROFIL)
    anderer = lege_haushalt_an(session, betriebsart="einzel").id
    with pytest.raises(ProfilUnbekanntError):
        profil(session, anderer, profil_id)
    with pytest.raises(ProfilUnbekanntError):
        loesche_profil(session, anderer, profil_id)


@pytest.mark.parametrize(
    "ungueltig",
    [
        replace(PROFIL, kodierung="keine-kodierung"),
        replace(PROFIL, trennzeichen=";;"),
        replace(PROFIL, name=" "),
        replace(PROFIL, kopfzeilen_ueberspringen=-1),
    ],
)
def test_ungueltiges_profil(session: Session, haushalt_id: uuid.UUID, ungueltig: CsvProfil) -> None:
    with pytest.raises(ProfilUngueltigError):
        speichere_profil(session, haushalt_id=haushalt_id, profil=ungueltig)


# --- Importieren ------------------------------------------------------------------------------


def test_speichert_nur_zahlungskandidaten(session: Session, haushalt_id: uuid.UUID) -> None:
    """Gutschriften und Rückbuchungen werden nie gespeichert (Kap. 8, Datenminimierung)."""
    neu = camt(
        session,
        haushalt_id,
        umsatz("1234.56", richtung=Richtung.GUTSCHRIFT, zweck="Gehalt"),
        umsatz("150.00"),
        umsatz("75.00", rueckbuchung=True),
        umsatz("80.00", zweck="AZ 0815"),
    )
    assert neu.umsaetze_gelesen == 4
    zeilen = [k.zeile for k in kandidaten(session, neu)]
    assert [(z.position, z.betrag) for z in zeilen] == [
        (1, Decimal("150.00")),
        (2, Decimal("80.00")),
    ]
    erste = zeilen[0]
    assert erste.datum == date(2025, 2, 4)  # Valuta nach Einstellung
    assert erste.buchungstag == date(2025, 2, 3)
    assert erste.gegen_iban == IBAN
    assert erste.gegen_name == "Muster Inkasso GmbH"
    assert erste.status == "offen"
    assert len(erste.schluessel) == 64


def test_wertstellung_nach_einstellung_zu_p16(session: Session, haushalt_id: uuid.UUID) -> None:
    neu = camt(session, haushalt_id, umsatz(), aus=WertstellungAus.BUCHUNGSTAG)
    assert kandidaten(session, neu)[0].zeile.datum == date(2025, 2, 3)


def test_fehlende_valuta_bricht_ab(session: Session, haushalt_id: uuid.UUID) -> None:
    """Es wird nicht geschätzt und nichts gespeichert (Kap. 8, P-16)."""
    with pytest.raises(ImportUngueltigError, match=r"Belastung Nr\. 2"):
        camt(session, haushalt_id, umsatz(), umsatz("80.00", valuta=None))
    assert laeufe(session, haushalt_id) == []


def test_gutschrift_ohne_valuta_stoert_nicht(session: Session, haushalt_id: uuid.UUID) -> None:
    neu = camt(session, haushalt_id, umsatz(valuta=None, richtung=Richtung.GUTSCHRIFT), umsatz())
    assert len(kandidaten(session, neu)) == 1


def test_csv_braucht_profilnamen(session: Session, haushalt_id: uuid.UUID) -> None:
    with pytest.raises(ImportUngueltigError):
        importiere(
            session,
            haushalt_id=haushalt_id,
            umsaetze=[umsatz()],
            dateiformat=Format.CSV,
            profil_name=None,
            wertstellung_aus=WertstellungAus.VALUTA,
        )


def test_lies_datei_csv_und_camt() -> None:
    csv = (
        "Bericht\nKonto\n"
        "Buchungstag;Valuta;Empfänger;IBAN;Verwendungszweck;Zusatz;Betrag\n"
        "03.02.2025;04.02.2025;Muster Inkasso GmbH;DE02120300000000202051;AZ 4711;Rate;-150,00\n"
    ).encode()
    gelesen = lies_datei(csv, Format.CSV, PROFIL)
    assert [u.verwendungszweck for u in gelesen] == ["AZ 4711 Rate"]
    with pytest.raises(ImportUngueltigError):
        lies_datei(csv, Format.CSV, None)
    with pytest.raises(ImportUngueltigError):
        lies_datei(b"<x/>", Format.CAMT053, PROFIL)


def test_lauf_eines_anderen_haushalts_ist_unbekannt(
    session: Session, haushalt_id: uuid.UUID
) -> None:
    neu = camt(session, haushalt_id, umsatz())
    anderer = lege_haushalt_an(session, betriebsart="einzel").id
    assert lauf(session, haushalt_id, neu.id) is neu
    with pytest.raises(LaufUnbekanntError):
        lauf(session, anderer, neu.id)
    with pytest.raises(LaufUnbekanntError):
        schliesse_ab(session, anderer, neu.id)
    assert laeufe(session, anderer) == []


# --- Duplikate --------------------------------------------------------------------------------


def test_duplikat_in_derselben_datei(session: Session, haushalt_id: uuid.UUID) -> None:
    """Zweimal dieselbe Zeile: Die zweite ist ein Duplikat (Hash nach Kap. 8, Schritt 3)."""
    neu = camt(session, haushalt_id, umsatz(), umsatz("80.00"), umsatz())
    assert [k.duplikat for k in kandidaten(session, neu)] == [False, False, True]


def test_duplikat_einer_gebuchten_zeile(session: Session, haushalt_id: uuid.UUID) -> None:
    konten = Konten(session, haushalt_id)
    erster = camt(session, haushalt_id, umsatz(), umsatz("80.00"))
    zweiter = camt(session, haushalt_id, umsatz(), umsatz("80.00"))
    assert [k.duplikat for k in kandidaten(session, zweiter)] == [False, False]
    zeile = kandidaten(session, erster)[0].zeile
    markiere_gebucht(
        session, haushalt_id=haushalt_id, zeile_id=zeile.id, buchung_ids=[konten.zahlung("150.00")]
    )
    assert [k.duplikat for k in kandidaten(session, zweiter)] == [True, False]
    # Die gebuchte Zeile selbst ist kein Duplikat.
    assert [k.duplikat for k in kandidaten(session, erster)] == [False, False]


def test_anderer_haushalt_kein_duplikat(session: Session, haushalt_id: uuid.UUID) -> None:
    konten = Konten(session, haushalt_id)
    erster = camt(session, haushalt_id, umsatz())
    markiere_gebucht(
        session,
        haushalt_id=haushalt_id,
        zeile_id=kandidaten(session, erster)[0].zeile.id,
        buchung_ids=[konten.zahlung("150.00")],
    )
    anderer = lege_haushalt_an(session, betriebsart="einzel").id
    assert [k.duplikat for k in kandidaten(session, camt(session, anderer, umsatz()))] == [False]


# --- Gebucht markieren ------------------------------------------------------------------------


def test_markiere_gebucht_mit_mehreren_buchungen(session: Session, haushalt_id: uuid.UUID) -> None:
    """Je Akte eine Buchung (Kap. 4.5); zusammen der Betrag der Zeile."""
    konten = Konten(session, haushalt_id)
    zeile = kandidaten(session, camt(session, haushalt_id, umsatz()))[0].zeile
    buchungen = [konten.zahlung("100.00"), konten.zahlung("50.00")]
    markiere_gebucht(session, haushalt_id=haushalt_id, zeile_id=zeile.id, buchung_ids=buchungen)
    assert zeile.status == "gebucht"
    verknuepft = session.scalars(
        select(ImportZeileBuchung.buchung_id).where(ImportZeileBuchung.zeile_id == zeile.id)
    ).all()
    assert set(verknuepft) == set(buchungen)


@pytest.mark.parametrize(
    ("betraege", "wertstellung", "meldung"),
    [
        ([], date(2025, 2, 4), "mindestens eine Buchung"),
        (["140.00"], date(2025, 2, 4), "Betrag der Zeile"),
        (["100.00", "60.00"], date(2025, 2, 4), "Betrag der Zeile"),
        (["150.00"], date(2025, 2, 3), "Wertstellung"),
    ],
)
def test_buchungen_muessen_zur_zeile_passen(
    session: Session,
    haushalt_id: uuid.UUID,
    betraege: list[str],
    wertstellung: date,
    meldung: str,
) -> None:
    konten = Konten(session, haushalt_id)
    zeile = kandidaten(session, camt(session, haushalt_id, umsatz()))[0].zeile
    buchungen = [konten.zahlung(b, wertstellung) for b in betraege]
    with pytest.raises(ZeileNichtBuchbarError, match=meldung):
        markiere_gebucht(session, haushalt_id=haushalt_id, zeile_id=zeile.id, buchung_ids=buchungen)
    assert zeile.status == "offen"


def test_buchung_mehrfach_genannt(session: Session, haushalt_id: uuid.UUID) -> None:
    konten = Konten(session, haushalt_id)
    zeile = kandidaten(session, camt(session, haushalt_id, umsatz()))[0].zeile
    buchung = konten.zahlung("75.00")
    with pytest.raises(ZeileNichtBuchbarError, match="mehrfach"):
        markiere_gebucht(
            session, haushalt_id=haushalt_id, zeile_id=zeile.id, buchung_ids=[buchung, buchung]
        )


def test_buchung_eines_anderen_haushalts(session: Session, haushalt_id: uuid.UUID) -> None:
    zeile = kandidaten(session, camt(session, haushalt_id, umsatz()))[0].zeile
    fremd = Konten(session, lege_haushalt_an(session, betriebsart="einzel").id).zahlung("150.00")
    with pytest.raises(ZeileNichtBuchbarError, match="im Haushalt nicht"):
        markiere_gebucht(session, haushalt_id=haushalt_id, zeile_id=zeile.id, buchung_ids=[fremd])


def test_stornierte_buchung_und_storno(session: Session, haushalt_id: uuid.UUID) -> None:
    konten = Konten(session, haushalt_id)
    zeile = kandidaten(session, camt(session, haushalt_id, umsatz()))[0].zeile
    buchung = konten.zahlung("150.00")
    storno = storniere(session, buchung_id=buchung).id
    with pytest.raises(ZeileNichtBuchbarError, match="storniert"):
        markiere_gebucht(session, haushalt_id=haushalt_id, zeile_id=zeile.id, buchung_ids=[buchung])
    with pytest.raises(ZeileNichtBuchbarError, match="Storno"):
        markiere_gebucht(session, haushalt_id=haushalt_id, zeile_id=zeile.id, buchung_ids=[storno])


def test_buchung_schon_aus_anderer_zeile(session: Session, haushalt_id: uuid.UUID) -> None:
    konten = Konten(session, haushalt_id)
    erste, zweite = (
        k.zeile
        for k in kandidaten(session, camt(session, haushalt_id, umsatz(), umsatz(zweck="AZ 4712")))
    )
    buchung = konten.zahlung("150.00")
    markiere_gebucht(session, haushalt_id=haushalt_id, zeile_id=erste.id, buchung_ids=[buchung])
    with pytest.raises(ZeileNichtBuchbarError, match="anderen Zeile"):
        markiere_gebucht(
            session, haushalt_id=haushalt_id, zeile_id=zweite.id, buchung_ids=[buchung]
        )


def test_zweimal_gebucht_und_duplikat(session: Session, haushalt_id: uuid.UUID) -> None:
    konten = Konten(session, haushalt_id)
    erste, zweite = (
        k.zeile for k in kandidaten(session, camt(session, haushalt_id, umsatz(), umsatz()))
    )
    markiere_gebucht(
        session, haushalt_id=haushalt_id, zeile_id=erste.id, buchung_ids=[konten.zahlung("150.00")]
    )
    with pytest.raises(ZeileNichtBuchbarError, match="schon gebucht"):
        markiere_gebucht(
            session,
            haushalt_id=haushalt_id,
            zeile_id=erste.id,
            buchung_ids=[konten.zahlung("150.00")],
        )
    with pytest.raises(ZeileNichtBuchbarError, match="Duplikat"):
        markiere_gebucht(
            session,
            haushalt_id=haushalt_id,
            zeile_id=zweite.id,
            buchung_ids=[konten.zahlung("150.00")],
        )


def test_duplikat_aus_offenem_parallellauf(session: Session, haushalt_id: uuid.UUID) -> None:
    """Zwei offene Läufe mit derselben Zeile: Nur eine wird gebucht."""
    konten = Konten(session, haushalt_id)
    erste = kandidaten(session, camt(session, haushalt_id, umsatz()))[0].zeile
    zweite = kandidaten(session, camt(session, haushalt_id, umsatz()))[0].zeile
    markiere_gebucht(
        session, haushalt_id=haushalt_id, zeile_id=zweite.id, buchung_ids=[konten.zahlung("150.00")]
    )
    with pytest.raises(ZeileNichtBuchbarError, match="Duplikat"):
        markiere_gebucht(
            session,
            haushalt_id=haushalt_id,
            zeile_id=erste.id,
            buchung_ids=[konten.zahlung("150.00")],
        )


def test_zeile_eines_anderen_haushalts_ist_unbekannt(
    session: Session, haushalt_id: uuid.UUID
) -> None:
    zeile = kandidaten(session, camt(session, haushalt_id, umsatz()))[0].zeile
    anderer = lege_haushalt_an(session, betriebsart="einzel").id
    with pytest.raises(ZeileUnbekanntError):
        markiere_gebucht(session, haushalt_id=anderer, zeile_id=zeile.id, buchung_ids=[])


# --- Abschließen ------------------------------------------------------------------------------


def test_abschluss_verwirft_zeilen_ohne_buchung(session: Session, haushalt_id: uuid.UUID) -> None:
    """Kap. 8, Datenminimierung: Nicht zugeordnete Zeilen werden verworfen."""
    konten = Konten(session, haushalt_id)
    neu = camt(session, haushalt_id, umsatz(), umsatz("80.00"), umsatz("90.00"))
    gebucht = kandidaten(session, neu)[1].zeile
    markiere_gebucht(
        session, haushalt_id=haushalt_id, zeile_id=gebucht.id, buchung_ids=[konten.zahlung("80.00")]
    )
    abgeschlossen = schliesse_ab(session, haushalt_id, neu.id)
    assert abgeschlossen.abgeschlossen_am is not None
    assert abgeschlossen.abgeschlossen_am.utcoffset() is not None
    assert [k.zeile.id for k in kandidaten(session, neu)] == [gebucht.id]
    assert session.scalar(select(func.count()).select_from(ImportZeile)) == 1
    # Ein zweiter Abschluss ändert nichts.
    assert (
        schliesse_ab(session, haushalt_id, neu.id).abgeschlossen_am
        == abgeschlossen.abgeschlossen_am
    )


def test_abgeschlossener_lauf_nimmt_keine_buchung(session: Session, haushalt_id: uuid.UUID) -> None:
    konten = Konten(session, haushalt_id)
    neu = camt(session, haushalt_id, umsatz(), umsatz("80.00"))
    erste = kandidaten(session, neu)[0].zeile
    markiere_gebucht(
        session, haushalt_id=haushalt_id, zeile_id=erste.id, buchung_ids=[konten.zahlung("150.00")]
    )
    schliesse_ab(session, haushalt_id, neu.id)
    zweiter = camt(session, haushalt_id, umsatz("70.00"))
    zeile = kandidaten(session, zweiter)[0].zeile
    schliesse_ab(session, haushalt_id, zweiter.id)
    with pytest.raises(ZeileUnbekanntError):
        markiere_gebucht(
            session,
            haushalt_id=haushalt_id,
            zeile_id=zeile.id,
            buchung_ids=[konten.zahlung("70.00")],
        )
    with pytest.raises(LaufAbgeschlossenError):
        markiere_gebucht(
            session,
            haushalt_id=haushalt_id,
            zeile_id=erste.id,
            buchung_ids=[konten.zahlung("150.00")],
        )
