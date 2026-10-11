# Finanzmanager

Selbst gehostete, modulare Finanzverwaltung für Privatpersonen.

> **Status: Konzeptphase.** Es gibt noch keinen lauffähigen Code. Die Software ist nicht für den Einsatz bereit.

## Worum es geht

Der Finanzmanager besteht aus einem gemeinsamen Kern und Fachmodulen. Das erste Modul **Verbindlichkeiten** hilft Privatpersonen, eigene Schulden und titulierte Altlasten nachvollziehbar zu verwalten:

- Restschuld, aufgeteilt in Hauptforderung, Zinsen und Kosten
- Zinsberechnung mit historischem Basiszinssatz
- Anrechnung von Teilzahlungen nach § 367 BGB bzw. § 497 Abs. 3 BGB
- Fristen und Verjährung, abgeleitet aus erfassten Ereignissen
- Abgleich mit der Forderungsaufstellung des Gläubigers
- Nachwirkung nach dem Ausgleich: Titelherausgabe, Schuldnerverzeichnis, Auskunfteien
- Schreiben als DOCX und PDF

Weitere Module (Forderungen, Konten, Depot, Sachwerte) sind geplant bzw. noch offen.

## Grundsätze

- Selbst gehostet, Betrieb nur im eigenen Netz, keine Cloud
- Keine Bankanbindung im ersten Release; Zahlungen kommen per CSV- oder CAMT.053-Import
- Doppelte Buchführung als Fundament
- Barrierearme Oberfläche auf Basis von KERN-UX

## Wichtiger Hinweis

Der Finanzmanager rechnet, erinnert und erstellt Entwürfe. Er leistet **keine Rechtsberatung**. Berechnungen sind Näherungen auf Grundlage der erfassten Daten; maßgeblich sind Titel und Forderungsaufstellung des Gläubigers. Bei Schulden beraten anerkannte Schuldnerberatungsstellen der Wohlfahrtsverbände und Kommunen, in der Regel kostenlos.

## Dokumentation

- [Fachkonzept](docs/fachkonzept.md): fachliche Quelle der Wahrheit
- [CLAUDE.md](CLAUDE.md): verbindliche Arbeitsregeln für KI-gestützte Entwicklung und Reviews

## Mitwirken

Siehe [CONTRIBUTING.md](CONTRIBUTING.md). Jeder Commit braucht einen DCO-Sign-off.

## Sicherheit

Sicherheitslücken bitte nicht als öffentliches Issue melden, sondern wie in [SECURITY.md](SECURITY.md) beschrieben.

## Lizenz

Copyright © 2026 hpdeising und Mitwirkende.

GNU Affero General Public License, Version 3 oder später ([LICENSE](LICENSE)). Wer den Finanzmanager verändert und anderen über ein Netzwerk bereitstellt, muss ihnen den geänderten Quellcode zugänglich machen.
