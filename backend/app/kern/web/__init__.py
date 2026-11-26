# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bausteine der JSON-Schnittstelle, die Kern und Module gemeinsam nutzen."""

from app.kern.web.abhaengigkeiten import (
    HaushaltId,
    Sitzung,
    Stammdaten,
    StammdatenAbh,
    installierter_haushalt,
)
from app.kern.web.importe import router as import_router
from app.kern.web.router import router
from app.kern.web.typen import Betragstext, Dezimaltext

__all__ = [
    "Betragstext",
    "Dezimaltext",
    "HaushaltId",
    "Sitzung",
    "Stammdaten",
    "StammdatenAbh",
    "import_router",
    "installierter_haushalt",
    "router",
]
