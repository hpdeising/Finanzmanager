# SPDX-License-Identifier: AGPL-3.0-or-later
"""CAMT.053 (ISO 20022, Kontoauszug), Fachkonzept Kap. 8.

Gelesen werden gebuchte Einträge (``Sts`` ``BOOK``) in Euro, unabhängig von der Version
(``camt.053.001.02`` bis ``.08``) über die lokalen Namen der Elemente. Eine Sammelbuchung mit
mehreren ``TxDtls`` mit eigenem Betrag ergibt je Teil einen Umsatz. Der Leser liefert
Buchungstag und Valuta; welches die Wertstellung wird, entscheidet die Einstellung zu P-16.

Die Datei wird mit ``defusedxml`` gelesen: keine Entitäten, keine externen Verweise.
"""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

from app.kern.geld import betrag as kanonischer_betrag
from app.kern.import_.umsatz import ImportUngueltigError, Richtung, Umsatz, iban_normiert

WAEHRUNG = "EUR"


def lies_camt053(daten: bytes) -> list[Umsatz]:
    """Umsätze eines CAMT.053-Auszugs.

    Raises:
        ImportUngueltigError: wenn die Datei kein lesbarer Auszug ist, Entitäten enthält oder
            ein Betrag nicht in Euro steht.
    """
    try:
        wurzel = fromstring(daten)
    except (ParseError, DefusedXmlException) as fehler:
        msg = "Die Datei ist kein lesbares XML oder enthält verbotene Entitäten."
        raise ImportUngueltigError(msg) from fehler
    auszuege = list(_alle(wurzel, "Stmt"))
    if _name(wurzel) != "Document" or not auszuege:
        msg = "Die Datei ist kein CAMT.053-Kontoauszug."
        raise ImportUngueltigError(msg)
    umsaetze: list[Umsatz] = []
    for nummer, eintrag in enumerate(
        (e for auszug in auszuege for e in _kinder(auszug, "Ntry")), start=1
    ):
        if _status(eintrag) != "BOOK":
            continue
        umsaetze.extend(_umsaetze(eintrag, nummer))
    return umsaetze


def _umsaetze(eintrag: Element, nummer: int) -> list[Umsatz]:
    richtung = {"DBIT": Richtung.BELASTUNG, "CRDT": Richtung.GUTSCHRIFT}.get(
        _text(_kind(eintrag, "CdtDbtInd"))
    )
    if richtung is None:
        msg = f"Eintrag {nummer}: CdtDbtInd fehlt oder ist unbekannt."
        raise ImportUngueltigError(msg)
    buchungstag = _datum(_kind(eintrag, "BookgDt"), nummer, "BookgDt")
    if buchungstag is None:
        msg = f"Eintrag {nummer}: BookgDt fehlt."
        raise ImportUngueltigError(msg)
    valuta = _datum(_kind(eintrag, "ValDt"), nummer, "ValDt")
    rueckbuchung = _text(_kind(eintrag, "RvslInd")).lower() == "true"
    details = [tx for d in _kinder(eintrag, "NtryDtls") for tx in _kinder(d, "TxDtls")]
    gesamt = _betrag(_kind(eintrag, "Amt"), nummer)
    if not details:
        details_mit_betrag: list[tuple[Element | None, Decimal]] = [(None, gesamt)]
    elif len(details) == 1 or any(_kind(tx, "Amt") is None for tx in details):
        details_mit_betrag = [(details[0], gesamt)]
    else:
        details_mit_betrag = [(tx, _betrag(_kind(tx, "Amt"), nummer)) for tx in details]
    seite = "Cdtr" if richtung is Richtung.BELASTUNG else "Dbtr"
    return [
        Umsatz(
            buchungstag=buchungstag,
            valuta=valuta,
            betrag=betrag,
            richtung=richtung,
            gegen_name=_gegen_name(tx, seite),
            gegen_iban=_gegen_iban(tx, seite),
            verwendungszweck=_zweck(tx),
            rueckbuchung=rueckbuchung,
        )
        for tx, betrag in details_mit_betrag
    ]


def _status(eintrag: Element) -> str:
    status = _kind(eintrag, "Sts")
    if status is None:
        return "BOOK"
    code = _kind(status, "Cd")
    return _text(code if code is not None else status)


def _betrag(element: Element | None, nummer: int) -> Decimal:
    if element is None:
        msg = f"Eintrag {nummer}: Amt fehlt."
        raise ImportUngueltigError(msg)
    if element.get("Ccy") != WAEHRUNG:
        msg = f"Eintrag {nummer}: Betrag nicht in {WAEHRUNG}; Release 1 kennt nur Euro."
        raise ImportUngueltigError(msg)
    try:
        ergebnis = kanonischer_betrag(_text(element))
    except (TypeError, ValueError) as fehler:
        msg = f"Eintrag {nummer}: Amt ungültig."
        raise ImportUngueltigError(msg) from fehler
    if ergebnis <= 0:
        msg = f"Eintrag {nummer}: Amt muss positiv sein."
        raise ImportUngueltigError(msg)
    return ergebnis


def _datum(element: Element | None, nummer: int, feld: str) -> date | None:
    if element is None:
        return None
    tag = _kind(element, "Dt")
    zeit = _kind(element, "DtTm")
    text = _text(tag) if tag is not None else _text(zeit)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as fehler:
        msg = f"Eintrag {nummer}: {feld} ungültig."
        raise ImportUngueltigError(msg) from fehler


def _gegen_name(tx: Element | None, seite: str) -> str | None:
    partei = _pfad(tx, "RltdPties", seite)
    if partei is None:
        return None
    name = next((n for n in _alle(partei, "Nm")), None)
    return _text(name) or None


def _gegen_iban(tx: Element | None, seite: str) -> str | None:
    konto = _pfad(tx, "RltdPties", f"{seite}Acct")
    iban = next(_alle(konto, "IBAN"), None) if konto is not None else None
    return iban_normiert(_text(iban))


def _zweck(tx: Element | None) -> str:
    rmt = _pfad(tx, "RmtInf")
    if rmt is None:
        return ""
    return " ".join(_text(u) for u in _kinder(rmt, "Ustrd") if _text(u))


# --- XML ohne Namensraum ------------------------------------------------------------------------


def _name(element: Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _kinder(element: Element, name: str) -> Iterator[Element]:
    return (k for k in element if _name(k) == name)


def _kind(element: Element, name: str) -> Element | None:
    return next(_kinder(element, name), None)


def _alle(element: Element, name: str) -> Iterator[Element]:
    return (e for e in element.iter() if _name(e) == name)


def _pfad(element: Element | None, *namen: str) -> Element | None:
    for name in namen:
        if element is None:
            return None
        element = _kind(element, name)
    return element


def _text(element: Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""
