# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixtures für die Tests des Buchungskerns."""

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session

from app.kern.haushalt import lege_haushalt_an
from app.kern.ledger import Kontoart, lege_konto_an


@dataclass(frozen=True)
class Konten:
    """Ein Haushalt mit drei Konten; Rollen mit neutralem Präfix ``test``."""

    haushalt_id: uuid.UUID
    eroeffnung: uuid.UUID
    hauptforderung: uuid.UUID
    zinsaufwand: uuid.UUID


def lege_konten_an(session: Session) -> Konten:
    haushalt = lege_haushalt_an(session, betriebsart="einzel")

    def konto(kontoart: Kontoart, rolle: str, bezeichnung: str) -> uuid.UUID:
        return lege_konto_an(
            session,
            haushalt_id=haushalt.id,
            kontoart=kontoart,
            rolle=rolle,
            bezeichnung=bezeichnung,
        ).id

    return Konten(
        haushalt_id=haushalt.id,
        eroeffnung=konto("eigenkapital", "test.eroeffnung", "Eröffnung"),
        hauptforderung=konto("passiv", "test.hauptforderung", "Hauptforderung"),
        zinsaufwand=konto("aufwand", "test.zinsaufwand", "Zinsaufwand"),
    )


@pytest.fixture
def konten(session: Session) -> Konten:
    return lege_konten_an(session)
