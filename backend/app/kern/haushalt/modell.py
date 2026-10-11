# SPDX-License-Identifier: AGPL-3.0-or-later
"""Haushalt: die Installationseinheit (Fachkonzept 3, 4.5; Betriebsart nach E-07).

Das Bundesland (für Feiertage) folgt mit Meilenstein M4.
"""

import uuid
from typing import Final, Literal, get_args

from sqlalchemy import CheckConstraint, Text, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.kern.db import Basis

Betriebsart = Literal["einzel", "haushalt_gemeinsam", "haushalt_getrennt"]
BETRIEBSARTEN: Final[tuple[Betriebsart, ...]] = get_args(Betriebsart)


class Haushalt(Basis):
    __tablename__ = "haushalt"
    __table_args__ = (
        CheckConstraint(
            "betriebsart IN ('einzel', 'haushalt_gemeinsam', 'haushalt_getrennt')",
            name="betriebsart",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    betriebsart: Mapped[Betriebsart] = mapped_column(Text)


def lege_haushalt_an(session: Session, *, betriebsart: Betriebsart) -> Haushalt:
    """Haushalt anlegen und in die Datenbank schreiben (ohne Commit)."""
    if betriebsart not in BETRIEBSARTEN:
        msg = f"Unbekannte Betriebsart; zulässig sind {', '.join(BETRIEBSARTEN)}."
        raise ValueError(msg)
    haushalt = Haushalt(betriebsart=betriebsart)
    session.add(haushalt)
    session.flush()
    return haushalt
