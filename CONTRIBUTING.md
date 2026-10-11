# Mitwirken am Finanzmanager

Das Projekt steht in der Konzeptphase. Fachliche Grundlage ist [docs/fachkonzept.md](docs/fachkonzept.md). Die Arbeitsregeln in [CLAUDE.md](CLAUDE.md) gelten für Menschen genauso wie für KI. Für den Umgang miteinander gilt der [Verhaltenskodex](CODE_OF_CONDUCT.md).

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
4. Vor dem Push müssen alle Prüfungen grün sein (siehe unten).
5. Pull Request mit ausgefüllter Vorlage öffnen.
6. Gemergt wird per Squash, nachdem die CI grün ist und alle Review-Kommentare erledigt sind.

Workflows aus Forks laufen erst nach Freigabe durch den Maintainer.

## Entwicklungsumgebung

Voraussetzung ist [uv](https://docs.astral.sh/uv/). Es installiert die passende Python-Version und alle Werkzeuge in den Versionen aus `backend/uv.lock`.

```bash
cd backend
uv sync
uv run ruff check          # Lint
uv run ruff format --check # Formatierung
uv run pyright             # Typprüfung (strict)
uv run lint-imports        # Modulgrenzen
uv run pytest              # Tests, einschließlich der Regeln aus CLAUDE.md
```

Optional führt [pre-commit](https://pre-commit.com/) dieselben Prüfungen vor jedem Commit aus: `uv tool install pre-commit`, dann im Repository `pre-commit install`.

### Test-Datenbank

Die Tests laufen gegen echtes PostgreSQL 16, weil die Datenbank die Regeln des Buchungskerns selbst erzwingt. Ohne Datenbank schlagen `pytest` und der pre-commit-Hook fehl; Datenbanktests werden nicht übersprungen.

1. PostgreSQL 16 starten, nur an `127.0.0.1`, mit Passwort-Anmeldung. Entweder ein lokal installiertes PostgreSQL 16 oder:

   ```bash
   docker run --rm -d --name fm-test-db -p 127.0.0.1:5432:5432 \
     -e POSTGRES_PASSWORD=<selbst gewählt> postgres:16.15
   ```

2. Die Adresse eines Superusers setzen (Vorlage: `.env.example`):

   ```bash
   export FINANZMANAGER_TEST_ADMIN_DATABASE_URL=postgresql+psycopg://postgres:<passwort>@127.0.0.1:5432/postgres
   ```

Jede Testsitzung legt über das Bootstrap-Skript die Rollen `finanzmanager_owner` und `finanzmanager_app` sowie eine eigene Datenbank `fm_test_<zufall>` an und löscht die Datenbank am Ende wieder. Die Tests laufen als Laufzeitrolle `finanzmanager_app`. Rollen gelten für den ganzen Cluster; deshalb nicht zwei Testläufe gleichzeitig gegen denselben Server starten.

Die Property-Tests mit Datenbank laufen lokal gründlich (Profil `db-gruendlich`); die CI setzt `FINANZMANAGER_HYPOTHESIS_DB_PROFIL=db-ci` mit weniger Beispielen.

## Testfälle (Golden Files)

Die Testfälle unter `tests/golden/` beruhen auf echten, anonymisierten Forderungsaufstellungen. Erwartungswerte ändert nur der Maintainer. Wenn du einen Fall beisteuern möchtest, nutze die Issue-Vorlage „Rechenfehler“ und entferne vorher alle personenbezogenen Daten.

## Sprache

Issues, Pull Requests und Dokumentation auf Deutsch. Im Code: Fachbegriffe deutsch, technische Begriffe englisch, keine Umlaute in Bezeichnern (siehe [CLAUDE.md](CLAUDE.md)).

## Lizenz

Mit deinem Beitrag stimmst du zu, dass er unter der GNU Affero General Public License, Version 3 oder später, veröffentlicht wird.
