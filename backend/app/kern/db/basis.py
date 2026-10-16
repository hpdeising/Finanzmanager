# SPDX-License-Identifier: AGPL-3.0-or-later
"""Grundlage aller ORM-Modelle: Metadaten mit festen Namen und ein Betragstyp, der nie rundet.

Die Namenskonvention legt die Namen aller Constraints fest. Migrationen, Modelle und die
Fehlerbehandlung beziehen sich auf dieselben Namen (z. B. ``uq_buchung_storno_von``).
"""

from decimal import Decimal
from typing import Any, Final

from sqlalchemy import MetaData, Numeric
from sqlalchemy.engine import Dialect
from sqlalchemy.exc import DontWrapMixin
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator, UserDefinedType

from app.kern.geld import speicherbar

NAMENSKONVENTION: Final = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(column_0_label)s",
}


class Basis(DeclarativeBase):
    """Basisklasse der ORM-Modelle von Kern und Modulen."""

    metadata = MetaData(naming_convention=NAMENSKONVENTION)


class BetragNichtSpeicherbarError(ValueError, DontWrapMixin):
    """Ein Betrag passt nicht exakt in ``NUMERIC(19,4)``.

    SQLAlchemy reicht diesen Fehler unverpackt durch (``DontWrapMixin``), statt ihn in einen
    ``StatementError`` zu hüllen.
    """


class BetragTyp(TypeDecorator[Decimal]):
    """``NUMERIC(19,4)`` (CLAUDE.md, Geld), das nie still rundet.

    PostgreSQL rundet zusätzliche Nachkommastellen beim Speichern still. Deshalb läuft jeder
    gebundene Wert vorher durch ``speicherbar()``. Das gilt auch für Vergleichswerte und für
    SQL mit eingesetzten Literalen, weil SQLAlchemy dafür ebenfalls ``process_bind_param``
    nutzt.
    """

    impl = Numeric(19, 4)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        try:
            return speicherbar(value)
        except (TypeError, ValueError) as fehler:
            raise BetragNichtSpeicherbarError(str(fehler)) from fehler


class Xid8(UserDefinedType[str]):
    """PostgreSQL ``xid8``: 64-Bit-Transaktionsnummer, innerhalb eines Clusters eindeutig.

    Nach einem Restore in einen neuen Cluster kann sich die Nummer einer eingespielten Zeile
    wiederholen (Fachkonzept 4.4, T-03). SQLAlchemy kennt den Typ nicht; psycopg liefert ihn
    als Text.
    """

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "xid8"
