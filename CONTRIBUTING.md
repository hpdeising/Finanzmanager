# Mitwirken am Finanzmanager

Das Projekt steht in der Konzeptphase. Fachliche Grundlage ist [docs/fachkonzept.md](docs/fachkonzept.md). Die Arbeitsregeln in [CLAUDE.md](CLAUDE.md) gelten für Menschen genauso wie für KI.

## Bevor du loslegst

- Für alles, was über einen Tippfehler hinausgeht: erst ein Issue, dann ein Pull Request.
- Fachliche Fragen (Zinsen, Anrechnung, Fristen, Verjährung) werden im Fachkonzept entschieden, nicht im Code. Änderungen daran bitte zuerst als Issue vorschlagen.
- Keine echten personenbezogenen Daten oder Finanzdaten in Issues, Pull Requests, Tests oder Beispielen.

## Developer Certificate of Origin (DCO)

Jeder Commit braucht einen Sign-off. Damit bestätigst du nach dem [Developer Certificate of Origin 1.1](https://developercertificate.org/), dass du den Beitrag einreichen darfst und er unter der Projektlizenz steht.

```bash
git commit -s -m "feat(verbindlichkeiten): Zinsregel für Kostenfestsetzung"
```

Das ergänzt die Zeile `Signed-off-by: Vorname Nachname <mail@example.org>`. Name und E-Mail müssen zum Autor des Commits passen, sonst schlägt die DCO-Prüfung im Pull Request fehl.

Sign-off vergessen?

- letzter Commit: `git commit --amend -s --no-edit`
- mehrere Commits: `git rebase --signoff main`

Danach den eigenen Branch mit `git push --force-with-lease` aktualisieren.

**KI-gestützte Beiträge** sind willkommen. Den Sign-off gibst trotzdem du, und damit trägst du die Verantwortung für den Inhalt. Nenne das verwendete Werkzeug in der Beschreibung des Pull Requests.

## Ablauf

1. Repository forken, Branch von `main` anlegen.
2. Ein Thema pro Pull Request.
3. Commit-Nachrichten nach [Conventional Commits](https://www.conventionalcommits.org/), z. B. `fix(kern): …`, `docs: …`.
4. Vor dem Push müssen grün sein, sobald es Code gibt: `ruff check`, `ruff format --check`, `pyright`, `pytest`.
5. Pull Request mit ausgefüllter Vorlage öffnen.
6. Gemergt wird per Squash, nachdem alle Review-Kommentare erledigt sind.

Workflows aus Forks laufen erst nach Freigabe durch den Maintainer.

## Testfälle (Golden Files)

Die Testfälle unter `tests/golden/` beruhen auf echten, anonymisierten Forderungsaufstellungen. Erwartungswerte ändert nur der Maintainer. Wenn du einen Fall beisteuern möchtest, nutze die Issue-Vorlage „Rechenfehler“ und entferne vorher alle personenbezogenen Daten.

## Sprache

Issues, Pull Requests und Dokumentation auf Deutsch. Im Code: Fachbegriffe deutsch, technische Begriffe englisch, keine Umlaute in Bezeichnern (siehe [CLAUDE.md](CLAUDE.md)).

## Lizenz

Mit deinem Beitrag stimmst du zu, dass er unter der GNU Affero General Public License, Version 3 oder später, veröffentlicht wird.
