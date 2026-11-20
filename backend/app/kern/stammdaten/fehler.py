# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fehler beim Laden und Abfragen der Stammdaten.

Meldungen nennen Datei, Feld und Stichtag, aber keine Werte aus der Datei.
"""


class StammdatenError(Exception):
    """Basis aller Fehler der Stammdaten."""


class StammdatenUngueltigError(StammdatenError, ValueError):
    """Eine Stammdatendatei fehlt, ist kein gültiges YAML oder verletzt ihr Format."""


class StammdatenFehlenError(StammdatenError, LookupError):
    """Für einen Stichtag gibt es keinen gültigen Eintrag. Es wird nicht geschätzt."""
