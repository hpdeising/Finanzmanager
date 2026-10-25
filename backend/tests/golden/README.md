# Golden Files

Hier liegen Testfälle, je Modul in einem eigenen Ordner (`verbindlichkeiten/`), in zwei Sorten mit getrennten Unterordnern:

- `real/` (Kennung `GR-nnnn`): anonymisierte reale Forderungsaufstellungen. Die Erwartungswerte stammen aus der Aufstellung des Gläubigers.
- `konstruiert/` (Kennung `GK-nnnn`): ausgedachte Daten, keine Beträge oder Daten aus realen Aufstellungen. Die Erwartungswerte stammen aus einer Rechentabelle, die der Maintainer geprüft und freigegeben hat.

Neben jeder YAML-Datei können `<id>.rechenweg.csv` und `<id>.anrechnung.csv` liegen; bei konstruierten Fällen sind sie Pflicht (die Anrechnung, sobald es Zahlungen gibt). Format, Spalten und Beispiele: [Fachkonzept, Kapitel 12](../../../docs/fachkonzept.md#12-qualitätssicherung).

Regeln aus [CLAUDE.md](../../../CLAUDE.md):

- Jede Datei nennt ihre Sorte und die Quelle ihrer Erwartungswerte. Rechenweg und Anrechnung in den CSV-Dateien gehören zu den Erwartungswerten.
- Erwartungswerte stammen nie aus dem Programm selbst und ändern ausschließlich Menschen. Eine KI überträgt nur freigegebene Werte, berechnet sie nie mit dem Programm und ändert sie nie ohne neue Freigabe.
- Schlägt ein Fall fehl, wird der Code korrigiert, nicht die Erwartung.
- Keine personenbezogenen Daten: keine Namen, Anschriften, Aktenzeichen oder IBANs.
