# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fehler beim Speichern und Laden von Akten."""


class AkteUnbekanntError(LookupError):
    """Die Akte gibt es nicht, oder sie gehört zu einem anderen Haushalt."""


class GlaeubigerUnbekanntError(LookupError):
    """Den Gläubiger gibt es nicht, oder er gehört zu einem anderen Haushalt."""


class EreignisUnbekanntError(LookupError):
    """Das Ereignis gibt es nicht, oder es gehört zu einer anderen Akte."""
