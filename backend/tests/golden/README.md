# Golden Files

Hier liegen Testfälle, je Modul in einem eigenen Ordner (`verbindlichkeiten/`), in zwei Sorten mit getrennten Unterordnern:

- `real/` (Kennung `GR-nnnn`): anonymisierte reale Forderungsaufstellungen. Die Erwartungswerte stammen aus der Aufstellung des Gläubigers. Wo sie nachweislich falsch rechnet, gilt der vom Maintainer nachgerechnete Wert; die YAML-Datei vermerkt jede solche Abweichung im Block `abweichungen`.
- `konstruiert/` (Kennung `GK-nnnn`): ausgedachte Daten, keine Daten aus realen Aufstellungen. Die Erwartungswerte berechnet eine KI außerhalb der Sitzung, die den Programmcode schreibt, auf zwei voneinander unabhängigen Wegen, etwa Tabellenkalkulation mit Formeln und exakte Dezimalrechnung. Beide müssen centgenau übereinstimmen, `zins_ungerundet` in allen angegebenen Stellen. Nie mit dem Programm. Eine Prüfung oder Freigabe durch den Maintainer ist nicht nötig; die YAML-Datei nennt stattdessen `berechnet_am` und die beiden Rechenwege unter `verfahren`.

Neben jeder YAML-Datei können `<id>.rechenweg.csv` und `<id>.anrechnung.csv` liegen; bei konstruierten Fällen sind sie Pflicht (die Anrechnung, sobald es Zahlungen gibt). Format, Spalten, Abweichungen und Beispiele: [Fachkonzept, Kapitel 12](../../../docs/fachkonzept.md#12-qualitätssicherung).

Regeln aus [CLAUDE.md](../../../CLAUDE.md) und dem Fachkonzept:

- Jede YAML-Datei nennt ihre Sorte und die Quelle ihrer Erwartungswerte. Rechenweg und Anrechnung in den CSV-Dateien tragen dieselbe Kennung und gehören zu den Erwartungswerten, ebenso der Block `abweichungen`.
- Erwartungswerte stammen nie aus dem Programm selbst.
- Das Programm bildet Rechenfehler von Gläubigern nicht nach: Der Golden-Test prüft gegen den nachgerechneten Wert, nicht gegen den falschen aus der Aufstellung.
- Erwartungswerte realer Fälle ändern ausschließlich Menschen. Eine KI überträgt nur freigegebene Werte, berechnet sie nie mit dem Programm und ändert sie nie ohne neue Freigabe.
- Erwartungswerte konstruierter Fälle ändern sich nur durch eine neue Berechnung auf beiden Wegen wie oben, mit Begründung im Pull Request.
- Schlägt ein Fall fehl, wird der Code korrigiert, nicht die Erwartung.
- Keine personenbezogenen Daten: keine Namen, Anschriften, Aktenzeichen oder IBANs.
