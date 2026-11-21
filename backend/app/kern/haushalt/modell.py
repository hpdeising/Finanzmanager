# SPDX-License-Identifier: AGPL-3.0-or-later
"""Haushalt: die Installationseinheit (Fachkonzept 3, 4.5; Betriebsart nach E-07).

Das Bundesland bestimmt die Feiertage, wenn bei einem Ereignis kein Gericht erfasst ist
(Kap. 5.4). Es fehlt, bis der Nutzer es einträgt; ohne Bundesland gibt es keine Fristen.
"""

import uuid
from typing import Final, Literal, get_args

from sqlalchemy import CheckConstraint, Text, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.kern.db import Basis
from app.kern.stammdaten import LAENDER

Betriebsart = Literal["einzel", "haushalt_gemeinsam", "haushalt_getrennt"]
BETRIEBSARTEN: Final[tuple[Betriebsart, ...]] = get_args(Betriebsart)


class Haushalt(Basis):
    __tablename__ = "haushalt"
    __table_args__ = (
        CheckConstraint(
            "betriebsart IN ('einzel', 'haushalt_gemeinsam', 'haushalt_getrennt')",
            name="betriebsart",
        ),
        CheckConstraint(
            "bundesland IN (" + ", ".join(f"'{land}'" for land in sorted(LAENDER)) + ")",
            name="bundesland",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    betriebsart: Mapped[Betriebsart] = mapped_column(Text)
    # Land nach ISO 3166-2:DE ohne Präfix, z. B. SH (Kap. 4.5, 5.4).
    bundesland: Mapped[str | None] = mapped_column(Text)


def lege_haushalt_an(
    session: Session, *, betriebsart: Betriebsart, bundesland: str | None = None
) -> Haushalt:
    """Haushalt anlegen und in die Datenbank schreiben (ohne Commit)."""
    if betriebsart not in BETRIEBSARTEN:
        msg = f"Unbekannte Betriebsart; zulässig sind {', '.join(BETRIEBSARTEN)}."
        raise ValueError(msg)
    if bundesland is not None and bundesland not in LAENDER:
        msg = "Unbekanntes Bundesland."
        raise ValueError(msg)
    haushalt = Haushalt(betriebsart=betriebsart, bundesland=bundesland)
    session.add(haushalt)
    session.flush()
    return haushalt
