# SPDX-License-Identifier: AGPL-3.0-or-later
"""CAMT.053 (ISO 20022), Fachkonzept Kap. 8. Alle Daten sind erfunden."""

from datetime import date
from decimal import Decimal

import pytest

from app.kern.import_ import ImportUngueltigError, Richtung, lies_camt053


def eintrag(
    *,
    betrag: str = "150.00",
    ind: str = "DBIT",
    buchung: str = "2025-02-03",
    valuta: str | None = "2025-02-04",
    gegen: str = "Cdtr",
    status: str = "<Sts>BOOK</Sts>",
    storno: str = "",
    details: str | None = None,
) -> str:
    valuta_xml = f"<ValDt><Dt>{valuta}</Dt></ValDt>" if valuta else ""
    konto = f"{gegen}Acct"
    tx = details or (
        "<TxDtls><RltdPties>"
        f"<{gegen}><Nm>Muster Inkasso GmbH</Nm></{gegen}>"
        f"<{konto}><Id><IBAN>DE02120300000000202051</IBAN></Id></{konto}>"
        "</RltdPties><RmtInf><Ustrd>AZ 4711</Ustrd><Ustrd>Rate 2</Ustrd></RmtInf></TxDtls>"
    )
    return (
        f'<Ntry><Amt Ccy="EUR">{betrag}</Amt><CdtDbtInd>{ind}</CdtDbtInd>{storno}{status}'
        f"<BookgDt><Dt>{buchung}</Dt></BookgDt>{valuta_xml}<NtryDtls>{tx}</NtryDtls></Ntry>"
    )


def auszug(*eintraege: str, version: str = "camt.053.001.02") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:{version}">'
        "<BkToCstmrStmt><Stmt>" + "".join(eintraege) + "</Stmt></BkToCstmrStmt></Document>"
    ).encode()


def test_belastung_mit_beiden_daten() -> None:
    """P-16: Der Leser liefert Buchungstag und Valuta; welches die Wertstellung wird, ist eine
    Einstellung (wertstellung)."""
    (umsatz,) = lies_camt053(auszug(eintrag()))
    assert (umsatz.buchungstag, umsatz.valuta) == (date(2025, 2, 3), date(2025, 2, 4))
    assert (umsatz.betrag, umsatz.richtung) == (Decimal("150.00"), Richtung.BELASTUNG)
    assert (umsatz.gegen_name, umsatz.gegen_iban) == (
        "Muster Inkasso GmbH",
        "DE02120300000000202051",
    )
    assert umsatz.verwendungszweck == "AZ 4711 Rate 2"
    assert umsatz.ist_kandidat


def test_gutschrift_nennt_den_zahlenden() -> None:
    (umsatz,) = lies_camt053(auszug(eintrag(ind="CRDT", gegen="Dbtr")))
    assert umsatz.richtung is Richtung.GUTSCHRIFT
    assert umsatz.gegen_name == "Muster Inkasso GmbH"
    assert not umsatz.ist_kandidat


def test_neuere_version_mit_party_und_status_code() -> None:
    """camt.053.001.08: Name unter Pty, Status als Code."""
    details = (
        "<TxDtls><RltdPties><Cdtr><Pty><Nm>Muster Inkasso GmbH</Nm></Pty></Cdtr>"
        "<CdtrAcct><Id><IBAN>DE02120300000000202051</IBAN></Id></CdtrAcct></RltdPties>"
        "<RmtInf><Ustrd>AZ 4711</Ustrd></RmtInf></TxDtls>"
    )
    xml = auszug(
        eintrag(status="<Sts><Cd>BOOK</Cd></Sts>", details=details), version="camt.053.001.08"
    )
    (umsatz,) = lies_camt053(xml)
    assert umsatz.gegen_name == "Muster Inkasso GmbH"
    assert umsatz.verwendungszweck == "AZ 4711"


def test_sammelbuchung_wird_in_einzelumsaetze_geteilt() -> None:
    details = "".join(
        f'<TxDtls><Amt Ccy="EUR">{b}</Amt><RmtInf><Ustrd>{z}</Ustrd></RmtInf></TxDtls>'
        for b, z in (("100.00", "AZ 1"), ("50.00", "AZ 2"))
    )
    umsaetze = lies_camt053(auszug(eintrag(details=details)))
    assert [(u.betrag, u.verwendungszweck) for u in umsaetze] == [
        (Decimal("100.00"), "AZ 1"),
        (Decimal("50.00"), "AZ 2"),
    ]


def test_vorgemerkte_umsaetze_zaehlen_nicht() -> None:
    assert lies_camt053(auszug(eintrag(status="<Sts>PDNG</Sts>"))) == []


def test_rueckbuchung_ist_kein_kandidat() -> None:
    """Eine Rückbuchung der Bank ist kein Zahlungskandidat; P-17 bleibt offen."""
    (umsatz,) = lies_camt053(auszug(eintrag(storno="<RvslInd>true</RvslInd>")))
    assert umsatz.rueckbuchung
    assert not umsatz.ist_kandidat


def test_ohne_valuta() -> None:
    (umsatz,) = lies_camt053(auszug(eintrag(valuta=None)))
    assert umsatz.valuta is None


def test_nur_euro() -> None:
    with pytest.raises(ImportUngueltigError, match="EUR"):
        lies_camt053(auszug(eintrag()).replace(b'Ccy="EUR"', b'Ccy="USD"'))


@pytest.mark.parametrize(
    "xml",
    [
        b"kein xml",
        b"<Document><Andere/></Document>",
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]>'
        b"<Document>&b;</Document>",
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        b"<Document>&x;</Document>",
    ],
    ids=["kaputt", "kein_auszug", "entitaeten", "externe_entitaet"],
)
def test_ungueltige_oder_gefaehrliche_dateien(xml: bytes) -> None:
    """defusedxml verbietet Entitäten; keine Datei des Servers gelangt in den Import."""
    with pytest.raises(ImportUngueltigError):
        lies_camt053(xml)
