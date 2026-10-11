# Sicherheitsrichtlinie

## Sicherheitslücken melden

Bitte melde Sicherheitslücken **nicht** über öffentliche Issues, Pull Requests oder Diskussionen.

Nutze stattdessen die vertrauliche Meldefunktion von GitHub:
[Sicherheitslücke melden](https://github.com/hpdeising/Finanzmanager/security/advisories/new)

Hilfreich sind:

- betroffene Version oder Commit
- Beschreibung der Lücke und mögliche Auswirkungen
- Schritte zum Nachvollziehen

Bitte keine echten personenbezogenen Daten oder Finanzdaten in die Meldung aufnehmen.

## Was danach passiert

- Meldungen werden vertraulich behandelt und vorrangig bearbeitet.
- Das Projekt wird ehrenamtlich gepflegt. Feste Reaktionszeiten können wir nicht zusagen.
- Details werden erst veröffentlicht, wenn eine Korrektur verfügbar ist. Auf Wunsch wirst du im Advisory genannt.

## Unterstützte Versionen

Es gibt noch keine Releases. Bis Version 1.0 wird nur der aktuelle Stand von `main` unterstützt.

## Geltungsbereich

| Gehört dazu | Gehört nicht dazu |
|---|---|
| Code in diesem Repository | Lücken in fremden Abhängigkeiten; bitte beim jeweiligen Projekt melden, ein Hinweis an uns ist willkommen |
| Installer und Docker-Konfiguration | Betrieb entgegen der Dokumentation, z. B. mit ins Internet freigegebenen Ports |
| Verschlüsselung, Anmeldung, Rechteprüfung | Rechenfehler bei Zinsen, Anrechnung oder Fristen; dafür gibt es die Issue-Vorlage „Rechenfehler“ |
