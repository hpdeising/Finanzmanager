# SPDX-License-Identifier: AGPL-3.0-or-later
"""Saldo zum Stichtag (Fachkonzept 4.1).

Kein Saldo wird als Wahrheit gespeichert. Der Saldo ist die Summe der Postings eines Kontos
mit Wertstellung bis einschließlich Stichtag, exakt und ungerundet. Stornos tragen die
Wertstellung der Ursprungsbuchung (E-18) und wirken deshalb auf denselben Stichtag zurück.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.kern.ledger.fehler import KontoUnbekanntError
from app.kern.ledger.modelle import Buchung, Konto, Posting


def saldo(session: Session, *, konto_id: uuid.UUID, stichtag: date) -> Decimal:
    """Summe der Postings von ``konto_id`` mit Wertstellung bis einschließlich ``stichtag``.

    Soll positiv, Haben negativ; ohne Postings ``Decimal(0)``.
    """
    if type(stichtag) is not date:
        msg = "Stichtag muss ein datetime.date sein."
        raise TypeError(msg)
    if session.get(Konto, konto_id) is None:
        raise KontoUnbekanntError(str(konto_id))
    summe = session.scalar(
        select(func.sum(Posting.betrag))
        .join(Buchung, Posting.buchung_id == Buchung.id)
        .where(Posting.konto_id == konto_id, Buchung.wertstellung <= stichtag)
    )
    return summe if summe is not None else Decimal(0)
