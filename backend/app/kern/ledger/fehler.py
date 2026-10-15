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


class KontoGesperrtError(BuchungUngueltigError):
    """Ein Konto der Buchung ist bis zu einem Datum gesperrt (E-27).

    Das Buchungsdatum muss nach dem Sperrdatum liegen. Für eine Buchung, deren Wertstellung
    im gesperrten Zeitraum liegt, gibt das Modul den Tag der Erfassung an (E-26).
    """


class SperreUngueltigError(EingabeUngueltigError):
    """Eine Kontosperre verletzt eine Regel, etwa ein Sperrdatum, das nicht steigt (E-27)."""


class StornoNichtMoeglichError(LedgerError):
    """Die Buchung ist selbst ein Storno, wurde schon storniert oder ist nicht stornierbar."""


class KontoBelegtError(LedgerError):
    """Eine gleichzeitige Transaktion sperrt das Konto oder bucht darauf (Fachkonzept 4.4).

    Die Datenbank hat sofort abgelehnt, ohne zu warten (SQLSTATE 55P03). Vorab prüfen lässt
    sich das nicht. Die Transaktion ist danach abgebrochen; der Aufrufer rollt zurück und
    versucht es erneut.
    """
