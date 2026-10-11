# CLAUDE.md – Arbeitsregeln für den Finanzmanager

Diese Datei gilt für jede KI, die in diesem Repository Code schreibt oder prüft. Fachliche Quelle der Wahrheit ist `docs/fachkonzept.md`.

- Widersprechen sich Fachkonzept und Code, ist der Code falsch.
- Widersprechen sich Fachkonzept und deine Überzeugung, hältst du an und fragst nach. Nicht improvisieren.

## Projekt in einem Satz

Selbst gehostete, modulare Finanzverwaltung für Privatpersonen (AGPL-3.0-or-later). Ein Kern trägt Fachmodule; das erste Modul „Verbindlichkeiten“ verwaltet eigene Schulden und titulierte Altlasten: Restschuld, Zinsen, Anrechnung, Fristen, Erledigung.

## Stack (verbindlich)

| Bereich | Technik |
|---|---|
| Backend | Python ≥ 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (typisiert), Alembic |
| Datenbank | PostgreSQL ≥ 16 |
| Frontend | React, TypeScript (strict), KERN-UX |
| API-Typen | OpenAPI aus FastAPI; Frontend-Typen werden daraus generiert, nie von Hand geschrieben |
| Dokumente | docxtpl, Gotenberg für PDF |
| Tests | pytest, hypothesis |
| Qualität | Ruff (Lint und Format), Pyright strict, import-linter (Modulgrenzen), pre-commit |
| Betrieb | Docker Compose |

Neue Frameworks oder Bibliotheken nur mit Begründung im Pull Request.

## Unverhandelbare Regeln

### Modulgrenzen

- Der Kern (`backend/app/kern/`) enthält keine Fachlogik eines Moduls.
- Module (`backend/app/module/<name>/`) hängen vom Kern ab, nie umgekehrt.
- Module importieren sich nicht gegenseitig. Austausch nur über Kern-Schnittstellen und Ereignisse.
- Ein Modul meldet seine Kontoarten, Rollen, Ereignistypen, Stammdaten, Vorlagen und Dashboard-Widgets beim Kern an.
- Die CI prüft diese Grenzen mit import-linter. Die Regeln dort werden nicht gelockert, um einen Build grün zu bekommen.

### Geld

- Beträge ausschließlich als `decimal.Decimal`. `float` ist in `backend/app/` verboten.
- Datenbank: `NUMERIC(19,4)`. JSON: Beträge als String (`"125.30"`), nie als Zahl.
- Gerundet wird nur über die zentrale Funktion in `kern/geld`. Nirgends sonst `quantize`.

### Datum und Fristen

- Fachliche Daten als `datetime.date`. Zeitstempel als `datetime` mit Zeitzone UTC.
- Fristen werden aus Ereignissen berechnet, nie gespeichert.

### Buchungen

- Buchungen und Postings werden nie geändert oder gelöscht. Korrekturen nur durch Storno und Neubuchung.
- Die Summe der Postings je Buchung ist null. Der Datenbank-Constraint dafür wird nie entfernt, deaktiviert oder umgangen.

### Recht

- Rechtsregeln werden nur so umgesetzt, wie sie im Fachkonzept stehen. Keine Normen erfinden, keine Normen aus dem Gedächtnis ergänzen.
- Jede Funktion, die eine Rechtsregel umsetzt, nennt die Norm im Docstring (z. B. `§ 367 Abs. 1 BGB`).
- Offene Prüfpunkte (P-xx im Fachkonzept) nicht eigenmächtig entscheiden. Sie werden konfigurierbar umgesetzt, mit dem Default aus dem Fachkonzept.

### Stammdaten

- Basiszinssatz, Pfändungsfreigrenzen, Feiertage, Gerichte und Löschfristen kommen nur aus `stammdaten/*.yaml`. Nie im Code hartkodieren.
- Fehlt ein gültiger Stammdatensatz für einen Stichtag: Fehler werfen, nicht schätzen.

### Golden Files

- `tests/golden/<modul>/` enthält anonymisierte reale Fälle. Erwartungswerte ändern ausschließlich Menschen.
- Schlägt ein Golden-File-Test fehl, wird der Code korrigiert, nie die Erwartung. Hältst du die Erwartung für falsch: anhalten, Begründung schreiben, auf Entscheidung warten.
- Tests nicht überspringen, nicht als `xfail` markieren, Toleranzen nicht erhöhen.

### Sicherheit und Datenschutz

- Keine Secrets im Repository. Konfiguration über Umgebungsvariablen; Vorlage ist `.env.example`.
- Standardbindung an `127.0.0.1`. Compose-Dateien veröffentlichen keine Ports nach außen.
- Passwörter mit Argon2id. Dokumente mit AES-256-GCM nach dem Schlüsselmodell im Fachkonzept (Kapitel 11).
- Keine eigene Kryptografie, nur etablierte Bibliotheken (`cryptography`, `argon2-cffi`).
- Logs enthalten keine personenbezogenen Daten: keine Namen, IBANs, Aktenzeichen, keine Beträge mit Personenbezug.
- In Tests, Fixtures und Beispielen nur erfundene oder anonymisierte Daten.

### Lizenzen

- Jede Quelldatei beginnt mit `SPDX-License-Identifier: AGPL-3.0-or-later`.
- Erlaubte Lizenzen für Abhängigkeiten: MIT, BSD, ISC, Apache-2.0, MPL-2.0, PSF-2.0, PostgreSQL, OLDAP-2.8, Public Domain, LGPL, GPL-3.0, AGPL-3.0. KERN-UX (EUPL-1.2) nur unverändert.
- Die Liste gilt für alle Abhängigkeiten des Projekts, einschließlich der nativen Bibliotheken, die ein Paket mitbringt (z. B. libpq in `psycopg-binary`). Sie gilt nicht für das Betriebssystem des Docker-Basis-Images; dafür gelten dessen eigene Lizenzhinweise (Debian: `/usr/share/doc/*/copyright`), die mit dem Image ausgeliefert und nicht gegen die Liste geprüft werden.
- Bringt ein Paket native Bibliotheken mit, nennt der Pull Request deren Lizenzen, weil der Lizenztest nur die Python-Metadaten liest. Die Bibliotheken gehören in die `THIRD-PARTY-LICENSES` (Fachkonzept 11.3).
- Verbotene Lizenzen für Abhängigkeiten: proprietär, SSPL, BUSL, Commons Clause, Creative Commons mit NC, GPL-2.0-only, unklare Lizenz.
- Die CI prüft die Lizenzen aller Python-Abhängigkeiten gegen diese Liste (`tests/test_lizenzen.py`). Neue Lizenzen kommen nur durch eine Änderung dieser Liste dazu, nie durch eine Ausnahme im Test.
- AGPL § 13: Die Oberfläche verlinkt auf den Quellcode der laufenden Version. Dieser Link wird nicht entfernt.

## Arbeitsweise

- Rechenlogik: erst den Test (aus dem Fachkonzept oder einem Golden File), dann den Code.
- Ein Thema pro Pull Request. Keine Umbauten nebenbei.
- Vor jedem Commit müssen diese Prüfungen grün sein: `ruff check`, `ruff format --check`, `pyright`, `pytest`.
- Commits nach Conventional Commits, mit DCO-Sign-off (`git commit -s`).
- KI-Beteiligung wird über `Co-Authored-By` angegeben. Commit-Nachrichten und PR-Beschreibungen enthalten keine Sitzungslinks (z. B. `Claude-Session: …`).
- Bezeichner: Fachbegriffe deutsch wie im Fachkonzept (`Akte`, `Bestandteil`, `Anrechnung`, `Zinsregel`), technische Begriffe englisch. Keine Umlaute in Bezeichnern (`glaeubiger`).
- Datenbankänderungen nur über Alembic-Migrationen. Gemergte Migrationen werden nie geändert.
- Bei Unklarheit fragen statt raten. Annahmen im Pull Request ausdrücklich nennen.

## Verzeichnisstruktur

```
backend/
  app/
    api/              # FastAPI-App, Registrierung der Router
    kern/
      db/             # Basis der Modelle, Betragstyp, Engine, Sitzung, Bootstrap der Datenbankrollen
      geld/           # Decimal-Hilfen, zentrale Rundung
      haushalt/       # Haushalt als Installationseinheit
      ledger/         # Konten, Buchungen, Postings, Invarianten
      stammdaten/     # Laden und Validieren der YAML-Dateien
      import_/        # CSV, CAMT.053
      dokumente/      # Vorlagen, PDF, Verschlüsselung
      sicherheit/
      dashboard/      # Widget-Registrierung
    module/
      verbindlichkeiten/
        domain/       # Akte, Bestandteil, Ereignis, Status
        zinsen/
        anrechnung/
        fristen/
        api/
  migrations/
  tests/
    kern/
    module/
      verbindlichkeiten/
    property/
    golden/
      verbindlichkeiten/
frontend/
  src/
    kern/
    module/
      verbindlichkeiten/
stammdaten/
vorlagen/
  verbindlichkeiten/
installer/
  linux/
  macos/
  windows/
docs/
```

## Prüfauftrag für Reviews (zweite KI, Community)

Prüfe den Pull Request gegen `docs/fachkonzept.md` und diese Datei. Melde mindestens:

1. `float` oder Rundung außerhalb von `kern/geld`
2. Rechtsregel ohne Normzitat oder abweichend vom Fachkonzept
3. Geänderte Erwartungswerte in `tests/golden/`
4. Änderung bestehender Buchungen statt Storno
5. Hartkodierte Stammdaten (Zinssätze, Freigrenzen, Stichtage)
6. Personenbezogene Daten in Logs, Tests oder Beispielen
7. Neue Abhängigkeit ohne Lizenzangabe oder mit verbotener Lizenz
8. Offene Ports, Secrets, eigene Kryptografie
9. Geänderte Rechenlogik ohne passenden Test
10. Verletzte Modulgrenzen: Kern importiert ein Modul, Module importieren sich gegenseitig, Fachlogik im Kern

Ordne jeden Fund als „blockierend“ oder „Hinweis“ ein. Keine Zusammenfassung des Pull Requests, kein Lob, nur Funde mit Datei und Zeile.
