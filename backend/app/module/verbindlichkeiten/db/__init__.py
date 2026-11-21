# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tabellen des Moduls Verbindlichkeiten."""

from app.module.verbindlichkeiten.db.modelle import (
    QUELLEN_ZINSREGEL,
    RICHTUNGEN,
    Akte,
    AkteKonto,
    AkteTeilungstag,
    BestandteilZeile,
    EreignisZeile,
    Glaeubiger,
    ZinsregelZeile,
)

__all__ = [
    "QUELLEN_ZINSREGEL",
    "RICHTUNGEN",
    "Akte",
    "AkteKonto",
    "AkteTeilungstag",
    "BestandteilZeile",
    "EreignisZeile",
    "Glaeubiger",
    "ZinsregelZeile",
]
