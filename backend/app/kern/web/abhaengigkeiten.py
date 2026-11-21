# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gemeinsame Abhängigkeiten der Routen von Kern und Modulen.

Die Anwendung legt Sitzungsfabrik und Stammdaten beim Start in ``app.state`` ab
(``app.api.erzeuge_app``). Eine Anfrage bekommt eine Sitzung, die bei Erfolg committet und
bei einem Fehler zurückrollt.

Der Haushalt ist die Installationseinheit (Fachkonzept 3): Es gibt höchstens einen. Bis es
Benutzer und Anmeldung gibt, arbeitet jede Anfrage in diesem Haushalt.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.kern.haushalt import Haushalt
from app.kern.stammdaten import Basiszinsreihe, Feiertagskalender


@dataclass(frozen=True, slots=True)
class Stammdaten:
    """Beim Start geladene Stammdaten (Fachkonzept Kap. 7)."""

    basiszinsreihe: Basiszinsreihe
    feiertage: Feiertagskalender


def sitzung(request: Request) -> Iterator[Session]:
    """Sitzung der Laufzeitrolle für eine Anfrage."""
    fabrik: sessionmaker[Session] = request.app.state.sitzungen
    with fabrik() as session:
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise


Sitzung = Annotated[Session, Depends(sitzung)]


def installierter_haushalt(session: Session) -> Haushalt | None:
    """Der Haushalt dieser Installation, falls schon eingerichtet."""
    return session.scalars(select(Haushalt).order_by(Haushalt.id).limit(1)).first()


def haushalt(session: Sitzung) -> Haushalt:
    """Haushalt der Installation; 409, solange er nicht eingerichtet ist."""
    gefunden = installierter_haushalt(session)
    if gefunden is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Der Haushalt ist noch nicht eingerichtet.")
    return gefunden


def haushalt_id(eingerichtet: Annotated[Haushalt, Depends(haushalt)]) -> uuid.UUID:
    return eingerichtet.id


HaushaltId = Annotated[uuid.UUID, Depends(haushalt_id)]


def stammdaten(request: Request) -> Stammdaten:
    return request.app.state.stammdaten


StammdatenAbh = Annotated[Stammdaten, Depends(stammdaten)]
