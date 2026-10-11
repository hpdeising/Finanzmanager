# SPDX-License-Identifier: AGPL-3.0-or-later
"""Konto, Buchung, Posting (Fachkonzept 4.4).

Die Tabellen sind modulneutral (E-17): Sie verweisen auf keine Tabelle eines Moduls. Die
Invarianten erzwingt PostgreSQL mit den Triggern aus Migration 0001; die Modelle tragen nur
die deklarativen CHECKs, mit denselben Namen.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Literal, get_args

from sqlalchemy import CHAR, CheckConstraint, Date, DateTime, ForeignKey, Text, func, inspect
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.kern.db import Basis, BetragTyp, Xid8
from app.kern.ledger.fehler import BuchungUngueltigError

# Eine der fünf Grundarten des Kerns (Fachkonzept 4.2).
Kontoart = Literal["aktiv", "passiv", "aufwand", "ertrag", "eigenkapital"]
KONTOARTEN: Final[tuple[Kontoart, ...]] = get_args(Kontoart)

# Rollen und Buchungsarten: <modul>.<name> (E-17). In M1 prüft die Datenbank nur das Format.
NAMENSMUSTER: Final = r"^[a-z_]+\.[a-z_]+$"

# Die einzigen Namen, die der Kern selbst kennt (E-17); alle anderen meldet ein Modul an.
KERN_PRAEFIX: Final = "kern."
STORNO: Final = "kern.storno"
EXTERNE_MITTEL: Final = "kern.externe_mittel"


class Konto(Basis):
    __tablename__ = "konto"
    __table_args__ = (
        CheckConstraint(
            "kontoart IN ('aktiv', 'passiv', 'aufwand', 'ertrag', 'eigenkapital')",
            name="kontoart",
        ),
        CheckConstraint(f"rolle ~ '{NAMENSMUSTER}'", name="rolle_format"),
        CheckConstraint("waehrung = 'EUR'", name="nur_eur"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    haushalt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("haushalt.id"), index=True)
    kontoart: Mapped[Kontoart] = mapped_column(Text)
    rolle: Mapped[str] = mapped_column(Text)
    waehrung: Mapped[str] = mapped_column(CHAR(3), server_default=sql_text("'EUR'"))
    bezeichnung: Mapped[str] = mapped_column(Text)


class Buchung(Basis):
    __tablename__ = "buchung"
    __table_args__ = (
        CheckConstraint(f"art ~ '{NAMENSMUSTER}'", name="art_format"),
        CheckConstraint(f"(art = '{STORNO}') = (storno_von IS NOT NULL)", name="storno_art"),
        CheckConstraint("storno_von <> id", name="storno_nicht_selbst"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    haushalt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("haushalt.id"))
    art: Mapped[str] = mapped_column(Text)
    wertstellung: Mapped[date] = mapped_column(Date)
    # Setzt die Datenbank auf den Beginn der Transaktion; ein Wert vom Client wird ersetzt.
    erfasst_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Setzt die Datenbank auf die Nummer der Transaktion, in der die Buchung entsteht. Nur in
    # dieser Transaktion nimmt sie Postings an (Fachkonzept 4.4). Nicht verzögert geladen:
    # Session.merge() sähe sonst keinen alten Wert und schickte ein UPDATE.
    erfasst_txid: Mapped[str] = mapped_column(Xid8())
    storno_von: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buchung.id"), unique=True)
    text: Mapped[str | None] = mapped_column(Text)

    @validates("erfasst_am", "erfasst_txid")
    def _setzt_nur_die_datenbank(self, feld: str, wert: object) -> object:
        """Bei einer neuen Buchung setzt beides die Datenbank (Fachkonzept 4.4).

        Ein Wert vom Client würde vom Trigger ersetzt, das ORM zeigte aber weiter ihn. Hat
        die Buchung schon eine Identität, etwa bei ``Session.merge()``, stammen die Werte aus
        der Datenbank; ändern ließen sie sich ohnehin nicht (kein UPDATE auf buchung).
        """
        if inspect(self).has_identity:
            return wert
        msg = f"{feld} setzt die Datenbank (Fachkonzept 4.4), nicht der Aufrufer."
        raise BuchungUngueltigError(msg)


class Posting(Basis):
    __tablename__ = "posting"
    __table_args__ = (CheckConstraint("betrag <> 0", name="betrag_ungleich_null"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    buchung_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("buchung.id"), index=True)
    konto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("konto.id"), index=True)
    # Soll positiv, Haben negativ (Fachkonzept 4.1).
    betrag: Mapped[Decimal] = mapped_column(BetragTyp())
