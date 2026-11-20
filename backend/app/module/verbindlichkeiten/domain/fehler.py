# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fehler des Moduls Verbindlichkeiten.

Meldungen nennen keine Beträge und keine Bezeichnungen; sie können in Logs landen
(CLAUDE.md, Sicherheit).
"""


class EingabeUngueltigError(ValueError):
    """Eine Eingabe der Berechnung verletzt eine Regel des Fachkonzepts."""
