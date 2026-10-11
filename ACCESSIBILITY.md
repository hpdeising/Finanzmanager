# Barrierefreiheit

## Ziel

Die Oberfläche des Finanzmanagers soll für alle nutzbar sein: mit Tastatur, Screenreader, Vergrößerung und hohem Kontrast. Maßstab sind die Web Content Accessibility Guidelines (WCAG) 2.1, Konformitätsstufe AA; wo möglich wird WCAG 2.2 AA angestrebt.

Die Barrierefreie-Informationstechnik-Verordnung (BITV 2.0) gilt für öffentliche Stellen, nicht für dieses private Projekt. Wir orientieren uns trotzdem an ihr, weil Menschen in finanziell schwierigen Lagen sich keine zusätzlichen Hürden leisten sollen.

## Wie wir das erreichen wollen

- Bedienelemente aus dem Designsystem [KERN-UX](https://www.kern-ux.de/), das auf Barrierefreiheit ausgelegt ist
- Zu jedem Diagramm eine gleichwertige Tabellenansicht
- Fristen, Warnungen und Status werden nie nur über Farbe vermittelt, sondern immer auch über Text oder Symbol
- Formulare mit sichtbaren Beschriftungen und verständlichen Fehlermeldungen
- Verständliche Sprache; Fachbegriffe werden in der Oberfläche erklärt
- Automatische Barrierefreiheitsprüfungen in der CI, sobald es eine Oberfläche gibt, und vor jedem Release ein manueller Test mit Tastatur und Screenreader

## Aktueller Stand

Das Projekt ist in der Konzeptphase. Es gibt noch keine Oberfläche, deshalb ist noch keine Aussage zur Konformität möglich. Diese Erklärung wird spätestens vor Release 0.1 aktualisiert und nennt dann bekannte Einschränkungen.

## Barrieren melden

- Öffne ein Issue mit der Vorlage „Fehler“ und schreib „Barriere“ in den Titel.
- Falls GitHub selbst für dich schwer zugänglich ist: schreib eine E-Mail an **hpdeising@mailme.guru**.

Hilfreich sind die betroffene Seite oder Funktion, das verwendete Hilfsmittel (z. B. Screenreader und Browser) und eine kurze Beschreibung, woran es scheitert.
