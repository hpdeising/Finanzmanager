# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fehler des Buchungskerns.

Meldungen nennen nie Beträge, Texte oder Bezeichnungen; sie können in Logs landen
(CLAUDE.md, Sicherheit).
"""


class LedgerError(Exception):
    """Basis aller Fehler des Buchungskerns."""


class EingabeUngueltigError(LedgerError, ValueError):
    """Eine Eingabe verletzt eine Regel des Buchungskerns."""


class KontoUngueltigError(EingabeUngueltigError):
    pass


class BuchungUngueltigError(EingabeUngueltigError):
    pass


class HaushaltUnbekanntError(LedgerError, LookupError):
    pass


class KontoUnbekanntError(LedgerError, LookupError):
    pass


class BuchungUnbekanntError(LedgerError, LookupError):
    pass


class StornoNichtMoeglichError(LedgerError):
    """Die Buchung ist selbst ein Storno oder wurde schon storniert."""
