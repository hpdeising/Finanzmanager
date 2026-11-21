# SPDX-License-Identifier: AGPL-3.0-or-later
"""Routen des Kerns: Angaben zur laufenden Version und Einrichtung des Haushalts.

Die Angaben zur Version enthalten den Link auf den Quellcode der laufenden Version
(AGPL-3.0 § 13). Die Oberfläche zeigt ihn an; er wird nicht entfernt (CLAUDE.md, Lizenzen).
"""

import os
from importlib.metadata import PackageNotFoundError, version
from typing import Final, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.kern.haushalt import BETRIEBSARTEN, Betriebsart, lege_haushalt_an
from app.kern.stammdaten import LAENDER
from app.kern.web.abhaengigkeiten import Sitzung, installierter_haushalt

QUELLCODE_VARIABLE: Final = "FINANZMANAGER_QUELLCODE_URL"
QUELLCODE_STANDARD: Final = "https://github.com/hpdeising/Finanzmanager"
LIZENZ: Final = "AGPL-3.0-or-later"

router = APIRouter(prefix="/api", tags=["kern"])


class Info(BaseModel):
    version: str
    lizenz: Literal["AGPL-3.0-or-later"]
    quellcode: str


class HaushaltEingabe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    betriebsart: Betriebsart = "einzel"
    bundesland: str


class HaushaltAusgabe(BaseModel):
    betriebsart: Betriebsart
    bundesland: str | None


def laufende_version() -> str:
    try:
        return version("finanzmanager")
    except PackageNotFoundError:
        return "unbekannt"


@router.get("/info")
def info() -> Info:
    """Version, Lizenz und Link auf den Quellcode der laufenden Version (AGPL-3.0 § 13)."""
    return Info(
        version=laufende_version(),
        lizenz=LIZENZ,
        quellcode=os.environ.get(QUELLCODE_VARIABLE) or QUELLCODE_STANDARD,
    )


@router.get("/haushalt")
def lies_haushalt(session: Sitzung) -> HaushaltAusgabe:
    haushalt = installierter_haushalt(session)
    if haushalt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Der Haushalt ist noch nicht eingerichtet.")
    return HaushaltAusgabe(betriebsart=haushalt.betriebsart, bundesland=haushalt.bundesland)


@router.post("/haushalt", status_code=status.HTTP_201_CREATED)
def richte_haushalt_ein(eingabe: HaushaltEingabe, session: Sitzung) -> HaushaltAusgabe:
    """Haushalt einrichten; es gibt genau einen je Installation (Fachkonzept 3)."""
    if installierter_haushalt(session) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Der Haushalt ist schon eingerichtet.")
    if eingabe.betriebsart not in BETRIEBSARTEN or eingabe.bundesland not in LAENDER:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unbekanntes Bundesland.")
    haushalt = lege_haushalt_an(
        session, betriebsart=eingabe.betriebsart, bundesland=eingabe.bundesland
    )
    return HaushaltAusgabe(betriebsart=haushalt.betriebsart, bundesland=haushalt.bundesland)
