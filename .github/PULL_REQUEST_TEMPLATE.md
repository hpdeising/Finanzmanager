## Worum geht es?

<!-- Ein bis zwei Sätze. Bezug: Issue #… -->

## Was wurde geändert?

## Annahmen und offene Punkte

<!-- Annahmen ausdrücklich nennen. Berührt der PR einen Prüfpunkt P-xx aus dem Fachkonzept? -->

## Checkliste

- [ ] Ein Thema pro Pull Request
- [ ] Alle Commits mit DCO-Sign-off
- [ ] `ruff check`, `ruff format --check`, `pyright`, `pytest` grün (sobald es Code gibt)
- [ ] Rechenlogik: Test vor Code, Normzitat im Docstring
- [ ] Kein `float` und keine Rundung außerhalb von `kern/geld`
- [ ] Keine geänderten Erwartungswerte in `tests/golden/`
- [ ] Keine hartkodierten Stammdaten
- [ ] Keine echten personenbezogenen Daten in Code, Tests, Logs oder Beispielen
- [ ] Neue Abhängigkeiten mit Lizenz genannt, Lizenz laut CLAUDE.md erlaubt
- [ ] Modulgrenzen eingehalten
- [ ] Falls KI-gestützt: Werkzeug genannt
