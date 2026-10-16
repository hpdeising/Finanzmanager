# Finanzmanager – Fachkonzept v0.1

**Modul in Release 1:** Verbindlichkeiten
**Stand:** 13.10.2026 · **Status:** Entwurf · **Projektlizenz:** AGPL-3.0-or-later
**Rechtsstand der Normzitate:** 11.10.2026. Offene Rechtsfragen stehen in Kapitel 14.

Dieses Dokument ist die fachliche Quelle der Wahrheit. Code, der davon abweicht, ist falsch – oder dieses Dokument wird vorher geändert. Die Software rechnet, erinnert und erzeugt Entwürfe. Sie leistet keine Rechtsberatung im Einzelfall.

---

## 1 Zweck und Abgrenzung

Der Finanzmanager ist eine selbst gehostete, modulare Webanwendung für die private Finanzverwaltung. Ein gemeinsamer Kern (Buchungen, Stammdaten, Dokumente, Import, Sicherheit, Dashboard) trägt Fachmodule, die nacheinander hinzukommen.

Release 1 enthält das Modul **Verbindlichkeiten**. Damit verwalten Privatpersonen eigene Verbindlichkeiten – insbesondere titulierte Altlasten – nachvollziehbar. Dazu gehören Restschuld, Zinsen, Anrechnung von Zahlungen, Fristen, Erledigung und Nachwirkung (Schuldnerverzeichnis, Auskunfteien).

### 1.1 Ziele Release 1

- Akten für Verbindlichkeiten aus Vollstreckungsbescheid, Urteil oder Versäumnisurteil, notarieller Urkunde oder Vergleich sowie nicht titulierten Forderungen
- Zinsberechnung, Anrechnung von Teilzahlungen, Abgleich mit der Forderungsaufstellung des Gläubigers
- Fristen mit Warnungen, abgeleitet aus erfassten Ereignissen
- Import von Zahlungen aus CSV und CAMT.053
- Generierte Schreiben als DOCX und PDF
- Dashboard ab Release 1, erweiterbar für spätere Module
- Einzel- oder Haushaltsbetrieb, Wahl bei der Installation
- Installer für Linux, macOS und Windows; Betrieb nur im Heimnetz

### 1.2 Nicht-Ziele Release 1

- Bankanbindung (FinTS, PSD2) und Zahlungsauslösung
- Gläubigersicht (eigene Forderungen gegen Dritte); Zuschnitt offen, siehe P-11.
- Depot, Sachwerte, Unterkonten
- Mandantenfähigkeit, Fernzugriff
- Insolvenzverfahren und Restschuldbefreiung
- Bewertung von Rechtslagen im Einzelfall

### 1.3 Module

| Modul | Inhalt | Stand |
|---|---|---|
| Kern | Buchungskern, Stammdaten, Dokumente, Import, Sicherheit, Benutzer, Dashboard-Rahmen | Release 1 |
| Verbindlichkeiten | Eigene Schulden und titulierte Altlasten (Schuldnersicht) | Release 1 |
| Forderungen | Eigene Forderungen gegen Dritte (Gläubigersicht) | geplant |
| Konten, Depot, Sachwerte | Weitere Bereiche der Gesamtvision | offen; Zuschnitt wird später entschieden |

Der Kern enthält keine Fachlogik eines Moduls. Module hängen vom Kern ab, nie umgekehrt, und greifen nicht direkt aufeinander zu.

---

## 2 Entscheidungsprotokoll

E-01 bis E-27 vom 11.10.2026; die Präzisierungen in E-25 und E-26 sowie E-28 vom 13.10.2026; E-29 vom 15.10.2026.

| Nr. | Thema | Entscheidung |
|---|---|---|
| E-01 | Lizenz | AGPL-3.0-or-later; Beiträge mit DCO-Sign-off |
| E-02 | Backend | Python, FastAPI |
| E-03 | Frontend | React, TypeScript, KERN-UX |
| E-04 | Datenbank | PostgreSQL; doppelte Buchführung als Fundament, anfangs schmal |
| E-05 | Betrieb | Docker Compose; Installer für Linux, macOS, Windows; nur Heimnetz |
| E-06 | Zahlungen | Import aus CSV und CAMT.053; keine Bankanbindung |
| E-07 | Nutzer | Wahl bei Installation: einzeln, Haushalt mit gemeinsamen Akten, Haushalt mit getrennten Akten |
| E-08 | Schutz | Verschlüsselte Backups, Systemverschlüsselung empfohlen und geprüft, Dokumente in der App verschlüsselt |
| E-09 | Perspektive | Schuldnersicht zuerst, Gläubigersicht später |
| E-10 | Hosting (später) | Eine Instanz pro Kunde |
| E-11 | Qualitätssicherung | Gegenprüfung durch eine zweite KI, Community-Review, Golden Files als Schiedsrichter |
| E-12 | Rechtsprüfung | Durch den Maintainer |
| E-13 | Dashboard | Ab Release 1, Widget-Architektur für spätere Module |
| E-14 | Zeitrahmen | Kein fester Zeitrahmen |
| E-15 | Name und Aufbau | Projektname „Finanzmanager“; modularer Aufbau aus Kern und Fachmodulen; erstes Modul „Verbindlichkeiten“ |
| E-16 | Lizenzen Dritter | PSF-2.0 zusätzlich erlaubt; die CI prüft Lizenzen bei jedem PR; Lizenzhinweise und SBOM entstehen automatisch je Release (Kap. 11.3) |
| E-17 | Kern und Module im Datenmodell | Kern-Tabellen verweisen nur auf Kern-Tabellen; Tabellen eines Moduls dürfen auf Kern-Tabellen verweisen, nie umgekehrt. Einzige Ausnahme ist `audit_log`: Es verweist allgemein über `entitaet_typ` und `entitaet_id`, ohne Fremdschlüssel, weil es jede Tabelle protokollieren muss. `konto` und `buchung` haben deshalb keine Spalte `akte_id`. Das Modul Verbindlichkeiten verknüpft Akten über eigene Tabellen (`akte_konto`, `akte_dokument`); die Buchungen einer Akte ergeben sich aus den Postings auf ihren Konten. Kontorollen und Buchungsarten folgen dem Schema `<modul>.<name>`, z. B. `verbindlichkeiten.hauptforderung`, `kern.externe_mittel`, `kern.storno`. Der Kern kennt nur `kern.externe_mittel` und `kern.storno`; die übrigen Rollen und Arten meldet das Modul an (Kap. 4.2, 4.4, 4.5) |
| E-18 | Storno-Wertstellung | Eine Stornobuchung hat dieselbe Wertstellung wie die Ursprungsbuchung; der Zeitpunkt der Korrektur steht in `erfasst_am`. Zinsen, Anrechnung und Fristen werden aus der Historie berechnet. Eine falsch erfasste Zahlung, die erst ab dem Korrekturtag storniert wäre, würde alle Zinsperioden davor weiter verfälschen. Über `erfasst_am` bleibt nachvollziehbar, was zu welchem Zeitpunkt bekannt war. Ergänzt durch E-26: Liegt die Wertstellung der Ursprungsbuchung in einem festgeschriebenen Zeitraum, bekommt das Storno den Tag der Erfassung als Buchungsdatum; seine Wertstellung bleibt die der Ursprungsbuchung |
| E-19 | Datenbankrollen | Die Eigentümerrolle führt nur die Migrationen aus. Die Anwendung verbindet sich mit einer Laufzeitrolle, die auf `buchung` und `posting` nur lesen und einfügen darf. Die Rollen legt ein eigenes Bootstrap-Skript an, nicht die Migration (Kap. 11.1) |
| E-20 | Lizenzen nativer Bibliotheken | Die Lizenzliste in `CLAUDE.md` gilt auch für native Bibliotheken, die ein Paket mitbringt; zusätzlich erlaubt sind PostgreSQL, OLDAP-2.8 und Public Domain. Maßgeblich ist die Lizenz, die das Ursprungsprojekt für die Bibliothek erklärt; einzelne Dateien darin werden nicht gegen die Liste geprüft, ihre Lizenz- und Hinweistexte kommen vollständig in `THIRD-PARTY-LICENSES`. Für das Betriebssystem des Docker-Basis-Images gelten dessen eigene Lizenzhinweise (Kap. 11.3) |
| E-21 | Zinsen und Anrechnung berechnet statt gebucht | Zinsen und die Anrechnung von Zahlungen werden nicht laufend gebucht, sondern bei jeder Abfrage zum Stichtag neu berechnet, aus Titel, Zahlungen, Ereignissen, Aktenparametern und Stammdaten. Eine Zahlung wird ungeteilt auf das Zahlungskonto der Akte gebucht (Rolle `verbindlichkeiten.zahlungen`, passiv), die Gegenbuchung geht auf Externe Mittel. Gebucht werden Zinsen und Anrechnung nur bei einer Festschreibung (E-25). Ein rückwirkendes Storno (E-18) wirkt damit automatisch richtig, ohne dass Folgebuchungen storniert und neu gebucht werden; betrifft es einen festgeschriebenen Zeitraum, bucht die nächste Festschreibung die Differenz als Korrekturbuchung (E-25). Schließt P-12 (Folgebuchungen nach rückwirkendem Storno): Statt Folgebuchungen automatisch zu stornieren und neu zu buchen, wird berechnet und nur bei Bedarf festgeschrieben (Kap. 4.3, 5.2, 5.3) |
| E-22 | Tageszählung | Voreinstellung `act_365`: Zinstage taggenau, Tagesbasis immer 365 Tage, auch im Schaltjahr. Je Akte umstellbar auf `act_360` oder `30_360`. Schließt P-04 (Kap. 5.1) |
| E-23 | Rundung | Voreinstellung `je_periode`: kaufmännisch auf Cent je Zinsperiode (Kap. 5.2 Schritt 2). Je Akte umstellbar auf `am_ende`. Schließt P-05 (Kap. 5.1) |
| E-24 | Zinsbeginn | Voreinstellung `genannter_tag`: Der als Zinsbeginn genannte Tag („seit dem …“) ist der erste Zinstag. Je Akte umstellbar auf `folgetag`: Erster Zinstag ist der Tag danach. Der Parameter gilt nur für den Beginn der Verzinsung; wechselt die Zinsregel, schließt die neue lückenlos an. Schließt P-06 (Kap. 5.1, 5.2) |
| E-25 | Festschreibung | Festgeschrieben wird nur auf ausdrückliche Anforderung, je Akte und zu einem Stichtag. Der Stichtag liegt nach dem der vorigen Festschreibung und höchstens auf dem Vortag der Festschreibung, gemessen am Tag ihrer Erfassung in der Zeitzone der Installation. Die Festschreibung bucht die bis zum Stichtag berechneten Zinsen und die Anrechnung, soweit sie noch nicht gebucht sind. Ein festgeschriebener Zeitraum ist abgeschlossen: Die Buchungen, die eine Festschreibung erzeugt (Zinsen, Umbuchung der Anrechnung, Korrekturbuchung), werden nie storniert, auch nicht nach Bestätigung; ihr Storno wird auch nicht vorgeschlagen. Die Berechnung bleibt maßgeblich, gebuchte Beträge werden abgezogen. Ändert sich nachträglich die Berechnung für einen festgeschriebenen Zeitraum, fällt die Differenz in den offenen Zeitraum; die nächste Festschreibung bucht sie als Korrekturbuchung mit maschinenlesbarem Bezug auf den korrigierten Zeitraum. Selbst gesetzter Grundsatz in Anlehnung an die Grundsätze ordnungsmäßiger Buchführung, keine Rechtsregel (Kap. 5.2 Schritt 7) |
| E-26 | Buchungsdatum und Wertstellung | Jede Buchung hat zwei Daten. Das Buchungsdatum ordnet sie einem Zeitraum zu und bestimmt die Salden, die Wertstellung bestimmt, ab wann sie fachlich wirkt (Zinsen, Anrechnung, Fristen). Liegt die Wertstellung im offenen Zeitraum der Akte, sind beide gleich. Liegt sie in einem festgeschriebenen Zeitraum der Akte, wird die Buchung im offenen Zeitraum gebucht, mit dem Tag der Erfassung als Buchungsdatum. Das gilt für ein Storno wie für jede neue Buchung (Neubuchung einer Korrektur, nachträglich erfasste Zahlung oder Kosten), nicht aber für die Buchungen einer Festschreibung selbst (E-25). Ein Storno beseitigt einen Erfassungsfehler: Die Buchung war falsch, den gebuchten Vorgang, etwa die Zahlung, hat es nie gegeben. Für Zinsen, Anrechnung und Fristen gilt die stornierte Buchung deshalb ab ihrer ursprünglichen Wertstellung als nie geschehen. Eine Rücklastschrift ist kein Storno, sondern ein tatsächliches Ereignis. Ergänzt E-18 (Kap. 4.1, 4.4, 5.2 Schritt 7) |
| E-27 | Kontosperre | Die Datenbank setzt den Abschluss eines festgeschriebenen Zeitraums selbst durch. Der Kern führt je Konto ein Sperrdatum und kennt dabei weder Akte noch Festschreibung, nur Konto und Datum. Ein Trigger lehnt jedes Posting auf ein gesperrtes Konto ab, dessen Buchungsdatum am oder vor dem Sperrdatum liegt. Das Sperrdatum eines Kontos steigt nur; auch das prüft die Datenbank. Bei jeder Festschreibung setzt das Modul die Sperre für die Konten der Akte auf den Stichtag; gemeinsame Haushaltskonten (die Konten je Haushalt, Kap. 4.2) werden nicht gesperrt. Welches Buchungsdatum eine Buchung bekommt und dass Festschreibungsbuchungen nicht storniert werden, entscheidet das Modul. Zusätzlich prüft der Kern, dass das Buchungsdatum nicht vor der Wertstellung liegt (Kap. 4.4). Ergänzt durch E-28: Das Modul legt Festschreibungsbuchungen mit `stornierbar = false` an, der Storno-Trigger lehnt ihr Storno ab; der Kern prüft zusätzlich, dass das Buchungsdatum eines Stornos nicht vor dem der Ursprungsbuchung liegt. Ergänzt durch E-29: Das Sperrdatum liegt höchstens auf dem heutigen Tag |
| E-28 | Stornoschutz im Kern | Jede Buchung trägt das Merkmal `stornierbar`. Es wird beim Einfügen gesetzt und ist danach unveränderlich. Der Storno-Trigger lehnt das Storno einer Buchung mit `stornierbar = false` ab; der Kern kennt dabei keinen Grund, nur das Merkmal (E-17). Das Modul legt die Buchungen einer Festschreibung mit `stornierbar = false` an, damit setzt auch die Datenbank durch, dass sie nie storniert werden (E-25). Zusätzlich prüft der Kern, dass das Buchungsdatum eines Stornos nicht vor dem der Ursprungsbuchung liegt (E-26). Ergänzt E-27 (Kap. 4.4, 5.2 Schritt 7) |
| E-29 | Sperrdatum höchstens heute | Die Datenbank lehnt eine Kontosperre ab, deren Sperrdatum nach dem heutigen Tag liegt (`gesperrt_bis > current_date`); die Kern-API prüft das vorab. Ein Sperrdatum steigt nur, und keine Sperre wird gelöscht (E-27). Ein Tipp- oder Modulfehler (2062 statt 2026) machte die Konten sonst bis dahin unbebuchbar, reparieren ließe es sich nur durch einen Eingriff am Trigger vorbei. Heute ist `current_date`, der Tag in der Zeitzone der Datenbanksitzung; die Anwendung verbindet sich in UTC. Bewusst „höchstens heute“ und nicht „höchstens Vortag“: So verträgt sich die Regel mit dem Stichtag einer Festschreibung, der höchstens auf dem Vortag in der Zeitzone der Installation liegt (E-25), auch wenn die Sitzung in einer anderen Zeitzone läuft. Dieser Vortag liegt nie nach dem heutigen Tag der Sitzung, solange deren Zeitzone höchstens 24 Stunden hinter der der Installation liegt. Das gilt für jede Sitzung in UTC und bei einer Installation in Deutschland für jede Zeitzone. Ergänzt E-27 (Kap. 4.4) |

---

## 3 Fachbegriffe

| Begriff | Bedeutung |
|---|---|
| Haushalt | Installationseinheit; enthält Benutzer, Akten und Konten |
| Akte | Eine Verbindlichkeit gegenüber einem Gläubiger aus einem Rechtsgrund. Mehrere Titel desselben Gläubigers ergeben mehrere Akten |
| Gläubiger | Inhaber der Forderung. Ein Inkassounternehmen wird als Vertreter erfasst, eine Abtretung als Ereignis |
| Titel | Vollstreckungsbescheid, Urteil, Versäumnisurteil, Vergleich, notarielle Urkunde |
| Bestandteil | Teil der Forderung mit eigener Rechtslogik: Hauptforderung, Zinsen, vorgerichtliche Kosten, Verfahrenskosten, Vollstreckungskosten |
| Zinsregel | Berechnungsvorschrift für die Zinsen eines Bestandteils |
| Ereignis | Datiertes, rechtlich relevantes Geschehen (Zustellung, Rechtskraft, Zahlung, Vollstreckungsantrag …). Fristen werden aus Ereignissen abgeleitet |
| Buchung | Unveränderlicher Geschäftsvorfall aus mindestens zwei Postings, deren Summe null ist; sie betreffen mindestens zwei verschiedene Konten |
| Buchungsdatum | Ordnet eine Buchung einem Zeitraum zu; nach ihm richten sich die Salden (Kap. 4.1) |
| Wertstellung | Tag, ab dem eine Buchung fachlich wirkt; nach ihr richten sich Zinsen, Anrechnung und Fristen (Kap. 4.1) |
| Stichtag | Datum, zu dem Salden und Zinsen berechnet werden |
| Restschuld | Summe der berechneten offenen Beträge der Bestandteile einer Akte zu einem Stichtag (Kap. 4.1) |
| Festschreibung | Abschluss einer Akte zu einem Stichtag, auf ausdrückliche Anforderung. Sie bucht die bis dahin berechneten, noch nicht gebuchten Zinsen und die Anrechnung sowie Korrekturbuchungen und sperrt die Konten der Akte bis zum Stichtag. Der Zeitraum bis einschließlich Stichtag ist danach abgeschlossen (Kap. 5.2 Schritt 7) |
| Korrekturbuchung | Buchung einer Festschreibung, die eine nachträgliche Differenz zwischen Berechnung und gebuchten Beträgen eines früheren festgeschriebenen Zeitraums ausgleicht; sie ist kein Storno und wird nie storniert (Kap. 5.2 Schritt 7) |

---

## 4 Datenmodell

### 4.1 Grundprinzipien

- Kein Saldo wird als Wahrheit gespeichert. Jeder Saldo ist die Summe der Postings eines Kontos mit Buchungsdatum bis einschließlich Stichtag. Saldo-Snapshots sind als Cache zulässig.
- Jede Buchung hat zwei Daten (E-26). Das **Buchungsdatum** ordnet sie einem Zeitraum zu und bestimmt die Salden. Die **Wertstellung** bestimmt, ab wann sie fachlich wirkt; nach ihr rechnen Zinsen, Anrechnung und Fristen. Liegt die Wertstellung im offenen Zeitraum der Akte, sind beide gleich. Liegt sie in einem festgeschriebenen Zeitraum der Akte (Kap. 5.2 Schritt 7), ist das Buchungsdatum der Tag der Erfassung: der Kalendertag von `erfasst_am` in der Zeitzone der Installation, nicht der UTC-Tag. Ausgenommen sind die Buchungen einer Festschreibung selbst; sie haben Buchungsdatum und Wertstellung an deren Stichtag. Das Buchungsdatum liegt nie vor der Wertstellung.
- Buchungen und Postings sind unveränderlich. Ein Erfassungsfehler wird durch Stornobuchung und Neubuchung korrigiert. Ein Storno beseitigt einen Erfassungsfehler: Die Buchung war falsch, den gebuchten Vorgang, etwa die Zahlung, hat es nie gegeben. Eine Rücklastschrift ist deshalb kein Storno, sondern ein tatsächliches Ereignis. Die Stornobuchung hat dieselbe Wertstellung wie die Ursprungsbuchung (E-18). Liegt diese Wertstellung im offenen Zeitraum, übernimmt das Storno das Buchungsdatum der Ursprungsbuchung, sonst ist es der Tag der Erfassung (E-26). Wann korrigiert wurde, steht in `erfasst_am`. Differenzen der Berechnung für festgeschriebene Zeiträume gleicht dagegen eine Korrekturbuchung aus (Kap. 5.2 Schritt 7); sie ist kein Storno.
- Zinsen und die Anrechnung von Zahlungen werden nicht aus Salden abgelesen, sondern bei jeder Abfrage berechnet (E-21). Gebucht werden sie nur bei einer Festschreibung (Kap. 5.2 Schritt 7). Die **Restschuld** einer Akte ist die Summe der berechneten offenen Beträge ihrer Bestandteile zum Stichtag; sie wird nie negativ. Ein Betrag, der sich nicht mehr anrechnen lässt, ergibt eine **Überzahlung**. Sie wird angezeigt; die Festschreibung bucht sie nicht auf Bestandteile um (Prüfpunkt P-20). Die Überzahlung ist ein Rechenergebnis, nicht der Saldo des Zahlungskontos: Dieser enthält bis zur nächsten Festschreibung auch alle noch nicht festgeschriebenen Zahlungen und kann nach einem Storno in einen festgeschriebenen Zeitraum bis zur nächsten Korrekturbuchung sogar das umgekehrte Vorzeichen haben.
- Vorzeichen: Soll positiv, Haben negativ. Die Summe der Postings jeder Buchung ist null; die Datenbank erzwingt das am Ende jeder Transaktion.
- Beträge: `NUMERIC(19,4)`. Währung je Konto; Release 1 kennt nur EUR.

### 4.2 Kontenrahmen

Die Kontoart ist eine der fünf Grundarten des Kerns: `aktiv`, `passiv`, `aufwand`, `ertrag`, `eigenkapital`. Wofür ein Konto dient, sagt seine Rolle. Rollen folgen dem Schema `<modul>.<name>` (E-17); Rollen des Kerns beginnen mit `kern.`.

Beim Anlegen einer Akte legt das Modul Verbindlichkeiten je Bestandteil ein Passivkonto und für die Akte ein Zahlungskonto an und verknüpft sie über seine Tabelle `akte_konto` mit der Akte (Kap. 4.5):

| Konto | Kontoart | Rolle |
|---|---|---|
| Hauptforderung | Passiv | `verbindlichkeiten.hauptforderung` |
| Zinsen (eines je Zinsregel) | Passiv | `verbindlichkeiten.zinsen` |
| Vorgerichtliche Kosten | Passiv | `verbindlichkeiten.kosten_vorgerichtlich` |
| Verfahrenskosten | Passiv | `verbindlichkeiten.kosten_verfahren` |
| Vollstreckungskosten | Passiv | `verbindlichkeiten.kosten_vollstreckung` |
| Zahlungen (eines je Akte) | Passiv | `verbindlichkeiten.zahlungen` |

Auf das Zahlungskonto gehen Zahlungen ungeteilt (E-21). Die Anrechnung auf die Bestandteile wird berechnet und erst mit einer Festschreibung vom Zahlungskonto auf die Bestandteile umgebucht (Kap. 5.2 Schritt 7). Bei jeder Festschreibung sperrt das Modul die Konten der Akte bis zum Stichtag (E-27).

Je Haushalt existieren:

| Konto | Kontoart | Rolle | Angelegt von |
|---|---|---|---|
| Eröffnung Altlasten | Eigenkapital | `verbindlichkeiten.eroeffnung` | Modul Verbindlichkeiten, bei der ersten Akte |
| Zinsaufwand | Aufwand | `verbindlichkeiten.zinsaufwand` | Modul Verbindlichkeiten, bei der ersten Akte |
| Kostenaufwand | Aufwand | `verbindlichkeiten.kostenaufwand` | Modul Verbindlichkeiten, bei der ersten Akte |
| Externe Mittel | Eigenkapital | `kern.externe_mittel` | Kern |

Die drei Konten des Moduls existieren je Haushalt, gehören aber fachlich zum Modul. Von den Rollen kennt der Kern nur `kern.externe_mittel`. Die Konten je Haushalt sperrt eine Festschreibung nicht (E-27).

„Externe Mittel“ steht für Geld, das aus nicht erfassten Konten gezahlt wird. Sobald Bankkonten als Aktivkonten hinzukommen, bucht eine Zahlung gegen das jeweilige Bankkonto statt gegen „Externe Mittel“. Am übrigen Modell ändert sich nichts.

Vorbereitet, nicht implementiert: Bankkonto (Aktiv), Depot (Aktiv), Sachwert (Aktiv), Forderung gegen Dritte (Aktiv, Gläubigersicht). Ihre Rollen tragen das Präfix des Moduls, das sie einführt.

### 4.3 Buchungsarten

| Vorgang | Art | Soll | Haben |
|---|---|---|---|
| Erfassung einer Altlast | `verbindlichkeiten.entstehung` | Eröffnung Altlasten | Hauptforderung (und ggf. Kosten, aufgelaufene Zinsen) |
| Neue Kosten (z. B. Vollstreckung) | `verbindlichkeiten.kosten` | Kostenaufwand | Kosten Vollstreckung |
| Zahlung | `verbindlichkeiten.zahlung` | Zahlungen | Externe Mittel bzw. später Bankkonto |
| Festschreibung der Zinsen bis Stichtag | `verbindlichkeiten.zinslauf` | Zinsaufwand | Zinsen |
| Festschreibung der Anrechnung bis Stichtag | `verbindlichkeiten.anrechnung` | Bestandteile laut Anrechnung (Kap. 5.3) | Zahlungen |
| Korrektur eines Erfassungsfehlers | `kern.storno` | Storno der Ursprungsbuchung | + Neubuchung |

- Zinsen und Anrechnung werden nicht laufend gebucht, sondern nur bei einer Festschreibung (E-21, Kap. 5.2 Schritt 7). Eine Korrekturbuchung für einen festgeschriebenen Zeitraum hat die Art der Buchung, die sie korrigiert (`verbindlichkeiten.zinslauf` oder `verbindlichkeiten.anrechnung`); Soll und Haben richten sich je Konto nach dem Vorzeichen der Differenz.
- Aufgelaufene Zinsen bei der Erfassung einer Altlast sind nur feste Beträge, die Titel oder Aufstellung ausweisen, und nur für Zeiträume, für die keine Zinsregel rechnet. Laufende Zinsen werden nie mit der Entstehung gebucht.
- Verteilt der Schuldner eine Zahlung auf mehrere Akten, entsteht je Akte eine eigene Buchung auf deren Zahlungskonto.

Buchungsarten folgen dem Schema `<modul>.<name>` (E-17). Der Kern kennt nur `kern.storno`; die übrigen Arten meldet das Modul mit seiner Umsetzung beim Kern an. In M1 prüft die Datenbank nur das Format, keine Liste.

### 4.4 Buchungskern (Skizze, nicht ausführbar)

Die Tabellen gehören dem Kern und verweisen auf keine Tabelle eines Moduls (E-17).

```sql
CREATE TABLE haushalt (
  id           uuid PRIMARY KEY,
  betriebsart  text NOT NULL CHECK (betriebsart IN ('einzel','haushalt_gemeinsam','haushalt_getrennt'))
  -- bundesland (Kap. 4.5) folgt mit den Feiertagen (M4)
);

CREATE TABLE konto (
  id           uuid PRIMARY KEY,
  haushalt_id  uuid NOT NULL REFERENCES haushalt,
  kontoart     text NOT NULL CHECK (kontoart IN ('aktiv','passiv','aufwand','ertrag','eigenkapital')),
  rolle        text NOT NULL CHECK (rolle ~ '^[a-z_]+\.[a-z_]+$'),  -- <modul>.<name> (E-17)
  waehrung     char(3) NOT NULL DEFAULT 'EUR' CHECK (waehrung = 'EUR'),  -- Release 1: nur EUR
  bezeichnung  text NOT NULL
);

CREATE TABLE buchung (
  id           uuid PRIMARY KEY,
  haushalt_id  uuid NOT NULL REFERENCES haushalt,
  art          text NOT NULL CHECK (art ~ '^[a-z_]+\.[a-z_]+$'),  -- <modul>.<name>, Kap. 4.3
  wertstellung date NOT NULL,                       -- fachlich wirksam ab (E-26)
  buchungsdatum date NOT NULL,                      -- Zuordnung zum Zeitraum (E-26); setzt das Modul
  erfasst_am   timestamptz NOT NULL DEFAULT now(),  -- setzt ein Trigger, siehe unten
  erfasst_txid xid8 NOT NULL,                       -- setzt ein Trigger, siehe unten
  -- erfasst_von uuid REFERENCES benutzer: Spalte und Fremdschlüssel folgen mit der Tabelle benutzer
  storno_von   uuid UNIQUE REFERENCES buchung,      -- höchstens ein Storno je Buchung
  stornierbar  boolean NOT NULL DEFAULT true,       -- E-28; beim Einfügen gesetzt, unveränderlich
  -- beleg_id uuid REFERENCES dokument: Spalte und Fremdschlüssel folgen mit der Tabelle dokument
  text         text,
  CHECK ((art = 'kern.storno') = (storno_von IS NOT NULL)),
  CHECK (storno_von <> id),
  CHECK (buchungsdatum >= wertstellung)             -- E-27
);

CREATE TABLE posting (
  id           uuid PRIMARY KEY,
  buchung_id   uuid NOT NULL REFERENCES buchung,
  konto_id     uuid NOT NULL REFERENCES konto,
  betrag       numeric(19,4) NOT NULL CHECK (betrag <> 0)
);

CREATE TABLE konto_sperre (                         -- E-27; nur anhängend
  konto_id     uuid NOT NULL REFERENCES konto,
  gesperrt_bis date NOT NULL,                       -- gesperrt bis einschließlich dieses Tags
  erfasst_am   timestamptz NOT NULL DEFAULT now(),  -- setzt ein Trigger, wie bei buchung
  PRIMARY KEY (konto_id, gesperrt_bis)
);
-- Sperrdatum eines Kontos ist das größte gesperrt_bis seiner Zeilen; ohne Zeile ist es nicht gesperrt.
-- Am Ende jeder Transaktion (DEFERRABLE INITIALLY DEFERRED CONSTRAINT TRIGGER) gilt je Buchung:
--   mindestens zwei Postings auf mindestens zwei verschiedenen Konten; SUM(betrag) = 0;
--   alle Konten gehören zum Haushalt der Buchung;
--   ein Storno besteht genau aus den negierten Postings der Ursprungsbuchung.
-- Sofort beim Einfügen (Trigger):
--   erfasst_am setzt ein Trigger auf now(), den Beginn der Transaktion, und erfasst_txid auf
--   pg_current_xact_id(), die Nummer der Transaktion; Werte vom Client werden überschrieben.
--   Postings entstehen nur in der Transaktion, in der auch ihre Buchung entsteht: Ein Posting
--   wird nur angenommen, wenn erfasst_txid seiner Buchung gleich pg_current_xact_id() und ihr
--   erfasst_am gleich now() ist. In derselben Transaktion gilt beides immer; erfasst_am und
--   now() sind beide der Beginn der Transaktion. Die Transaktionsnummer ist nötig, weil now()
--   nicht je Transaktion eindeutig ist: Alle Transaktionen einer Client-Nachricht haben
--   denselben Zeitstempel. Die Nummer ist innerhalb eines Clusters eindeutig und gilt auch in
--   Savepoints, zusammen mit erfasst_am auch über eine Wiederherstellung hinweg: In einem
--   neuen Cluster kann sich die Nummer einer eingespielten Buchung wiederholen, ihr erfasst_am
--   liegt aber in der Vergangenheit (T-03).
--   Storno: Die Ursprungsbuchung existiert, ist selbst kein Storno, gehört zum selben
--   Haushalt, hat dieselbe Wertstellung (E-18) und ist stornierbar (E-28). Das Buchungsdatum
--   des Stornos liegt nicht vor dem der Ursprungsbuchung (E-28).
--   Kontosperre (E-27): Ein Posting wird abgelehnt, wenn das Buchungsdatum seiner Buchung am
--   oder vor dem Sperrdatum seines Kontos liegt. Das gilt auch für ein Storno.
--   Eine neue Zeile in konto_sperre wird nur angenommen, wenn gesperrt_bis größer ist als
--   das bisherige Sperrdatum des Kontos; ihr erfasst_am setzt ein Trigger auf now().
--   gesperrt_bis liegt nicht nach current_date, dem heutigen Tag in der Zeitzone der Sitzung
--   (E-29).
-- Nebenläufigkeit (Kap. 5.2 Schritt 7): Ist eine Sperre committet, ändert sich die Menge der
--   Postings des Kontos mit Buchungsdatum bis zum Sperrdatum nicht mehr, auch nicht durch
--   Transaktionen, die schon vorher liefen. Ab dem Zeitpunkt, zu dem die sperrende
--   Transaktion das Konto hält (ausdrücklich vorab oder mit dem Einfügen der Sperre),
--   scheitert jede andere, die Postings auf das Konto einfügt; umgekehrt scheitert das
--   Halten, solange eine andere Transaktion auf dem Konto bucht; jeweils sofort und ohne zu
--   warten. Was vor dem Halten committet ist, gehört zum gesperrten Zeitraum. Hält eine
--   Festschreibung die Konten, bevor sie rechnet, rechnet sie deshalb auf genau den Postings,
--   die ihre Sperre einfriert.
-- Isolationsstufe: Postings und Sperren gibt es nur in READ COMMITTED; andere Stufen lehnt die
--   Datenbank ab, weil eine Transaktion in REPEATABLE READ oder SERIALIZABLE eine später
--   committete Sperre nicht sähe.
-- Buchungsdatum (E-26 bis E-28): Welches Buchungsdatum eine Buchung bekommt, entscheidet das
--   Modul; der Kern übernimmt es und prüft es gegen die Wertstellung (CHECK oben), gegen die
--   Kontosperre und beim Storno gegen das Buchungsdatum der Ursprungsbuchung. Die Sperre kennt
--   keine Akte und keine Festschreibung, nur Konto und Datum (E-17).
-- UPDATE, DELETE und TRUNCATE auf buchung, posting und konto_sperre sind per Trigger verboten.
-- An konto sind id, haushalt_id, kontoart, rolle und waehrung unveränderlich.
-- Die Trigger feuern immer, auch bei session_replication_role = replica.
-- Rechte (E-19; für konto_sperre diese Skizze): Die Laufzeitrolle darf auf buchung, posting
--   und konto_sperre nur lesen und einfügen; in M1 gilt das auch für haushalt und konto.
-- Buchungsdatum, Kontosperre und stornierbar (E-26 bis E-29) kommen mit Migration 0002.
-- Beträge: NUMERIC(19,4) rundet eine fünfte und jede weitere Nachkommastelle still, und kein
--   Trigger sieht den ursprünglichen Wert. Deshalb lehnt die Anwendung solche Beträge vor dem
--   Speichern ab (kern/geld). Beträge ab 10^15 weist schon die Datenbank zurück (Überlauf); die
--   Anwendung prüft auch das vorher, um einen verständlichen Fehler zu liefern. Der Buchungskern
--   rundet nie; Module runden vorher über kern/geld.
```

### 4.5 Fachtabellen

Kern-Tabellen verweisen nur auf Kern-Tabellen; Tabellen eines Moduls dürfen auf Kern-Tabellen verweisen, nie umgekehrt. Einzige Ausnahme ist `audit_log`, ohne Fremdschlüssel (E-17).

**Kern-Tabellen**

| Tabelle | Wesentliche Felder |
|---|---|
| `haushalt` | Betriebsart (`einzel`, `haushalt_gemeinsam`, `haushalt_getrennt`), Bundesland (für Feiertage) |
| `benutzer` | Haushalt, Anmeldename, Passwort-Hash, umschlossener Dokumentschlüssel |
| `konto`, `buchung`, `posting` | siehe Kap. 4.4 |
| `konto_sperre` | Konto, gesperrt bis, erfasst am; nur anhängend (Kap. 4.4). Umsetzung der Kontosperre (E-27) |
| `dokument` | Art, Dateiname, SHA-256, Größe, Schlüsselversion |
| `import_zeile` | Quelle, Datum, Betrag, Gegen-IBAN, Verwendungszweck, Status; nach der Verarbeitung die erzeugten Buchungen (je Akte eine, Kap. 4.3). Die Zuordnung zur Akte macht das Modul |
| `audit_log` | Wer, wann, welche Entität (`entitaet_typ`, `entitaet_id`, ohne Fremdschlüssel), welche Aktion – ohne Inhaltsdaten; nur anhängend |

**Tabellen des Moduls Verbindlichkeiten**

| Tabelle | Wesentliche Felder |
|---|---|
| `glaeubiger` | Name, Anschrift, IBAN, Vertreter (Inkasso), Kontaktdaten |
| `akte` | Eigentümer, Freigaben, Richtung (`verbindlichkeit`, `forderung`; bis zur Entscheidung über P-11), Gläubiger, Titelart, Verbraucherdarlehen ja/nein, Anrechnungsregel, Tageszählung, Rundung, Zinsbeginn, Status, Aktenzeichen des Gläubigers |
| `akte_konto` | Akte, Konto. Die Buchungen einer Akte ergeben sich aus den Postings auf ihren Konten |
| `akte_dokument` | Akte, Dokument |
| `titel` | Art, Gericht, Aktenzeichen, erlassen am, zugestellt am, rechtskräftig am |
| `bestandteil` | Akte, Art, Konto, Ursprungsbetrag, entstanden am, fällig am |
| `zinsregel` | Bestandteil, Typ, Aufschlag in Prozentpunkten, fester Satz, ab, bis, Quelle (Titel/Vertrag) |
| `ereignis` | Akte, Typ, Datum, Details (JSON), Beleg; bei `zahlung` die zugehörige Buchung (Datum und Neubuchung: Prüfpunkt P-18) |
| `aufgabe` | Akte, Typ, fällig am, erledigt am |
| `festschreibung` | Akte, Stichtag, erfasst am; nur anhängend. Die Stichtage einer Akte steigen streng. Der Zeitraum einer Festschreibung reicht vom Tag nach dem vorigen Stichtag bis einschließlich ihres Stichtags; bei der ersten Festschreibung umfasst er alles bis einschließlich ihres Stichtags. Der offene Zeitraum einer Akte beginnt am Tag nach ihrem letzten Stichtag; ohne Festschreibung ist alles offen. Sie wird auch gespeichert, wenn nichts zu buchen ist (Kap. 5.2 Schritt 7) |
| `festschreibung_buchung` | Festschreibung, Buchung, korrigierter Zeitraum (Verweis auf die Festschreibung, deren Zeitraum die Buchung korrigiert; leer bei den Buchungen des eigenen Zeitraums); nur anhängend |

In Meilenstein M1 entstehen davon nur `haushalt`, `konto`, `buchung` und `posting`.

Ereignistypen in Release 1: `zustellung_mahnbescheid`, `zustellung_vollstreckungsbescheid`, `zustellung_urteil`, `rechtskraft`, `errichtung_titel`, `eintragungsanordnung`, `zahlung`, `vollstreckungsantrag`, `vollstreckungshandlung`, `anerkenntnis`, `glaeubigerwechsel`, `anrechnung_abgelehnt`, `ausgleich`, `quittung_erhalten`, `titel_erhalten`, `loeschung_schuldnerverzeichnis`, `erledigt_gemeldet_auskunftei`, `verjaehrung_eingewandt`.

### 4.6 Erweiterbarkeit

- Neue Module (Forderungen, Konten, Depot, Sachwerte) bringen eigene Rollen, Buchungsarten, Ereignistypen, Stammdaten, Vorlagen und Dashboard-Widgets mit und melden sie beim Kern an. Eine eigene Buchungslogik bringen sie nicht mit.
- Gläubigersicht: Ob sie ein eigenes Modul mit eigenen Tabellen wird oder Teil des Moduls Verbindlichkeiten, ist offen (Prüfpunkt P-11).
- Mandantenfähigkeit ist nicht vorgesehen; jede Instanz ist ein Haushalt. Spätere Mandanten wären eine Spalte über `haushalt`, kein Umbau.

---

## 5 Rechenregeln

### 5.1 Grundsätze

- Intern wird mit `Decimal` ohne Zwischenrundung gerechnet. Gerundet wird kaufmännisch auf Cent, laut Aktenparameter `rundung`: `je_periode` (Default, je Zinsperiode nach Kap. 5.2 Schritt 2) oder `am_ende` (E-23). Was `am_ende` bei Zahlungen innerhalb einer Zinsperiode bedeutet, klärt Prüfpunkt P-13.
- Tageszählung laut Aktenparameter `tageszaehlung`: `act_365` (Default; taggenau, Tagesbasis immer 365, auch im Schaltjahr), `act_360` oder `30_360` (E-22). Welche Variante von `30_360` gilt, klärt Prüfpunkt P-15.
- Zinsbeginn laut Aktenparameter `zinsbeginn`: `genannter_tag` (Default; der als Zinsbeginn genannte Tag „seit dem …“ ist der erste Zinstag) oder `folgetag` (erster Zinstag ist der Tag danach) (E-24).
- Zinsen und Anrechnung werden bei jeder Abfrage neu berechnet (E-21). Eingaben sind Titel, Bestandteile und ihre Zinsregeln, die Buchungen der Akte mit ihrer Wertstellung (ohne stornierte Buchungen samt ihren Stornos und ohne die Buchungen, die eine Festschreibung erzeugt), dazu Ereignisse, Aktenparameter und Stammdaten.
- Die Berechnung ist deterministisch: gleiche Eingaben ergeben dasselbe Ergebnis. Eine Festschreibung ändert kein Rechenergebnis.

### 5.2 Zinsen

| Typ | Satz | Norm |
|---|---|---|
| `gesetzlich_288_1` | Basiszinssatz + 5 Prozentpunkte | § 288 Abs. 1 S. 2 BGB |
| `gesetzlich_288_2` | Basiszinssatz + 9 Prozentpunkte (kein Verbraucher beteiligt; Gläubigersicht) | § 288 Abs. 2 BGB |
| `kostenfestsetzung` | Basiszinssatz + 5 Prozentpunkte ab Eingang des Festsetzungsantrags | § 104 Abs. 1 S. 2 ZPO |
| `basiszins_plus` | Basiszinssatz + x Prozentpunkte | laut Titel oder Vertrag |
| `fest` | fester Jahreszins | laut Titel oder Vertrag |
| `keine` | – | – |

Ablauf:

1. Der Zinslauf je verzinslichem Bestandteil beginnt am `ab`-Datum der Zinsregel und endet am Stichtag. Ob der genannte Tag des Zinsbeginns selbst verzinst wird, bestimmt der Aktenparameter `zinsbeginn` (Kap. 5.1, E-24). Er gilt nur für den Beginn der Verzinsung; wechselt die Zinsregel, schließt die neue lückenlos an die alte an.
2. Perioden werden geteilt an jedem 01.01. und 01.07. (bei basiszinsabhängigen Regeln, § 247 Abs. 1 BGB), an der Wertstellung jeder nicht stornierten Zahlung und bei jeder Änderung der Zinsregel. Der Stichtag einer Festschreibung und eine stornierte Zahlung teilen keine Periode.
3. Zinsbasis ist der offene Betrag des Bestandteils zu Periodenbeginn, nach der berechneten Anrechnung früherer Zahlungen (Kap. 5.3). Ob am Zahlungstag schon die verminderte Basis gilt, klärt Prüfpunkt P-14.
4. Zinsen = Basis × Jahressatz × Tage ÷ Tagesbasis.
5. Keine Zinsen auf Zinsen (§ 289 S. 1 BGB). Zinskonten sind nie verzinslich.
6. Der Satz ist Basiszinssatz plus Aufschlag, auch bei negativem Basiszinssatz. Beispiel: vom 01.07.2016 bis 31.12.2022 lag der Basiszinssatz bei −0,88 %, der Verzugszins nach § 288 Abs. 1 BGB also bei 4,12 %. Altlasten reichen oft in diesen Zeitraum.
7. Zinsen und Anrechnung werden bei jeder Abfrage zum Stichtag neu berechnet, nicht laufend gebucht (E-21). Gebucht wird nur bei einer Festschreibung (E-25):
   - **Anforderung:** Festgeschrieben wird nur auf ausdrückliche Anforderung, je Akte und zu einem Stichtag. Der Stichtag liegt nach dem der vorigen Festschreibung und höchstens auf dem Vortag der Festschreibung, gemessen am Tag ihrer Erfassung wie in Kap. 4.1 (Zeitzone der Installation); ein Abschluss zum 31.12. wird also frühestens am 01.01. angefordert.
   - **Zinsen und Anrechnung eines Zeitraums** sind die Berechnung zu seinem Stichtag abzüglich der Berechnung zum vorigen Stichtag. Für eine angebrochene Zinsperiode zählt der bis zum Stichtag berechnete und gerundete Betrag; die Rundungsdifferenz zur ganzen Periode fällt in den nächsten Zeitraum und ist keine Korrektur.
   - **Halten:** Bevor sie rechnet, hält die Festschreibung die Konten der Akte (Kap. 4.4). Bis zum Commit bucht dann keine andere Transaktion auf ihnen; läuft gerade eine Buchung, scheitert die Festschreibung und wird wiederholt.
   - **Buchungen:** Die Festschreibung bucht mit Buchungsdatum und Wertstellung an ihrem Stichtag die Zinsen des Zeitraums (`verbindlichkeiten.zinslauf`), seine Anrechnung als Umbuchung vom Zahlungskonto auf die Bestandteile (`verbindlichkeiten.anrechnung`) und die Korrekturbuchungen für frühere Zeiträume. Die Regel für nachträgliche Buchungen (E-26) gilt für diese Buchungen nicht. Danach setzt das Modul in derselben Transaktion die Sperre der Konten der Akte auf den Stichtag (E-27). Legt das Modul später ein neues Konto für die Akte an, sperrt es dieses in derselben Transaktion bis zum letzten Stichtag der Akte. Die Festschreibung wird auch gespeichert, wenn nichts zu buchen ist; jede ihrer Buchungen steht in `festschreibung_buchung` (Kap. 4.5).
   - **Abschluss:** Ein festgeschriebener Zeitraum ist abgeschlossen. Die Buchungen, die eine Festschreibung erzeugt (Zinsen, Umbuchung der Anrechnung, Korrekturbuchung), werden nie storniert, auch nicht nach Bestätigung; ihr Storno wird auch nicht vorgeschlagen. Das Modul legt sie mit `stornierbar = false` an, sodass auch die Datenbank ihr Storno ablehnt (E-28). Zahlung, Kosten und Entstehung bleiben stornierbar.
   - **Nachträgliche Buchungen:** Eine Buchung, deren Wertstellung in einem festgeschriebenen Zeitraum liegt, wird im offenen Zeitraum gebucht, mit dem Tag der Erfassung als Buchungsdatum (E-26). Das gilt für ein Storno, für die Neubuchung einer Korrektur und für nachträglich erfasste Zahlungen oder Kosten. Für Zinsen, Anrechnung und Fristen zählt ihre Wertstellung; eine stornierte Buchung gilt ab ihrer ursprünglichen Wertstellung als nie geschehen.
   - **Korrekturbuchung:** Die Berechnung bleibt maßgeblich, gebuchte Beträge werden abgezogen. Als gebuchte Beträge zählen nur die Buchungen, die Festschreibungen erzeugt haben, je Konto und Zeitraum; eine Korrekturbuchung zählt zu dem Zeitraum, den sie korrigiert. Ändert sich die Berechnung für einen festgeschriebenen Zeitraum nachträglich, etwa durch ein Storno, eine nachträgliche Buchung, ein nachgetragenes Ereignis, eine geänderte Zinsregel, einen umgestellten Aktenparameter oder korrigierte Stammdaten, fällt die Differenz in den offenen Zeitraum. Die nächste Festschreibung bucht sie als eigene Korrekturbuchung je betroffenem Zeitraum und Buchungsart (Kap. 4.3). Der Buchungstext nennt den Zeitraum; maschinenlesbar ist der Bezug über `festschreibung_buchung`, sodass sich auch eine zweite Korrektur desselben Zeitraums zuordnen lässt.
   - **Begründung:** Selbst gesetzter Grundsatz in Anlehnung an die Grundsätze ordnungsmäßiger Buchführung: Was festgeschrieben ist, bleibt stehen, Fehler werden im offenen Zeitraum berichtigt. Es ist keine Rechtsregel.

### 5.3 Anrechnung von Zahlungen

| Regel | Reihenfolge | Norm |
|---|---|---|
| `bgb_367` (Default) | Kosten → Zinsen → Hauptforderung | § 367 Abs. 1 BGB |
| `bgb_497` | Kosten der Rechtsverfolgung → Hauptforderung → Zinsen | § 497 Abs. 3 BGB (Verbraucherdarlehen nach Verzug) |
| `individuell` | laut Vereinbarung mit dem Gläubiger | Vereinbarung als Beleg erforderlich |

- Die Anrechnung wird wie die Zinsen bei jeder Abfrage berechnet, aus den nicht stornierten Zahlungen auf dem Zahlungskonto mit ihrer Wertstellung. Gebucht wird sie erst mit einer Festschreibung, als Umbuchung vom Zahlungskonto auf die Bestandteile (E-21, Kap. 5.2 Schritt 7).
- Lässt sich ein Betrag nicht mehr anrechnen, weil die Restschuld null ist, wird er als Überzahlung angezeigt; die Festschreibung bucht ihn nicht auf Bestandteile um. Die Überzahlung ist ein Rechenergebnis, nicht der Saldo des Zahlungskontos (Kap. 4.1). Ob sie auf später entstehende Positionen angerechnet wird, klärt Prüfpunkt P-20.
- Innerhalb einer Gruppe (Kosten, Zinsen) gilt: älteste Position zuerst. Prüfpunkt P-07.
- **Mehrere Akten desselben Gläubigers:** Die Zahlung gilt für die Akte, die der Schuldner bei der Zahlung bestimmt, z. B. im Verwendungszweck (§ 366 Abs. 1 BGB). Fehlt eine Bestimmung, legt Release 1 die Zahlung zur manuellen Zuordnung vor. Die gesetzliche Reihenfolge des § 366 Abs. 2 BGB (fällig → geringere Sicherheit → lästiger → älter → verhältnismäßig) wird als Vorschlag angezeigt, nicht automatisch angewandt.
- **Abweichende Bestimmung des Schuldners:** Lehnt der Gläubiger sie ab (§ 367 Abs. 2 BGB), wird das Ereignis `anrechnung_abgelehnt` erfasst, und es gilt wieder die gesetzliche Reihenfolge.
- **Warnung:** Ist eine Rate kleiner als der Zinszuwachs der Periode, sinkt die Hauptforderung nie. Das Dashboard zeigt das bei jeder betroffenen Akte an.

**Abgleich mit der Forderungsaufstellung:** Der Nutzer erfasst die Positionen der Aufstellung: Stichtag, Hauptforderung, Zinsen je Zeitraum, Kosten je Position, verrechnete Zahlungen. Das System vergleicht positionsweise und nennt mögliche Ursachen für Abweichungen: Zinssatz, Tageszählung, Anrechnungsreihenfolge, unbekannte Kosten, fehlende Zahlungen.

### 5.4 Fristen

- Fristen werden aus Ereignissen abgeleitet und nie gespeichert. Ändert sich ein Ereignis, ändern sich die Fristen. Ein Ereignis `zahlung`, dessen Buchung storniert ist, gilt als nie geschehen (E-26).
- Berechnet wird nach §§ 187, 188 BGB. Bei prozessualen Fristen gilt zusätzlich § 222 Abs. 2 ZPO: Endet die Frist an einem Samstag, Sonntag oder allgemeinen Feiertag, endet sie mit Ablauf des nächsten Werktags. Feiertage richten sich nach dem Bundesland des Haushalts.
- Jede Frist führt: Norm, auslösendes Ereignis, Fristende, Art (Notfrist, prozessual, materiell, Information), Warnstufen.

| Frist | Auslöser | Dauer | Norm | Art |
|---|---|---|---|---|
| Widerspruch gegen Mahnbescheid | Zustellung Mahnbescheid | 2 Wochen; danach möglich, solange kein Vollstreckungsbescheid verfügt ist | § 692 Abs. 1 Nr. 3, § 694 Abs. 1 ZPO | prozessual |
| Einspruch gegen Vollstreckungsbescheid | Zustellung | 2 Wochen | § 700 Abs. 1, § 339 Abs. 1 ZPO | Notfrist |
| Einspruch gegen Versäumnisurteil | Zustellung | 2 Wochen | § 339 Abs. 1 ZPO | Notfrist |
| Berufung | Zustellung Urteil | 1 Monat; nur bei Beschwer über 600 € oder Zulassung | §§ 511, 517 ZPO | Notfrist |
| Widerspruch gegen Eintragungsanordnung | Bekanntgabe | 2 Wochen | § 882d Abs. 1 ZPO | prozessual |
| Löschung im Schuldnerverzeichnis | Tag der Eintragungsanordnung | 3 Jahre, von Amts wegen | § 882e Abs. 1 ZPO | Information |
| Vorzeitige Löschung | Ausgleich und Nachweis | auf Antrag | § 882e Abs. 3 Nr. 1 ZPO | Aufgabe |
| Löschung erledigter Auskunftei-Einträge | Ausgleich | 36 Monate; 18 Monate bei Erfüllung der Bedingungen der 100-Tage-Regel | Verhaltensregeln der Auskunfteien (Code of Conduct) | Information |
| Verjährung | siehe 5.5 | | | materiell |

Warnstufen: Notfristen 7, 3 und 1 Tag vor Ablauf; prozessuale Fristen 7 und 3 Tage; Informationen 30 Tage. Fehlt bei einer Zustellung das Datum, warnt das System sofort, denn ohne Zustellungsdatum gibt es keine Frist.

### 5.5 Verjährung

| Fall | Frist | Beginn | Norm |
|---|---|---|---|
| Nicht titulierte Forderung | 3 Jahre | Schluss des Jahres der Entstehung und Kenntnis des Gläubigers | §§ 195, 199 Abs. 1 BGB |
| Rechtskräftig festgestellt (Urteil, Vollstreckungsbescheid) | 30 Jahre | Rechtskraft | § 197 Abs. 1 Nr. 3, § 201 BGB; § 700 Abs. 1 ZPO |
| Vollstreckbarer Vergleich, vollstreckbare Urkunde | 30 Jahre | Errichtung des Titels | § 197 Abs. 1 Nr. 4, § 201 BGB |
| Kosten der Zwangsvollstreckung | 30 Jahre | Entstehung | § 197 Abs. 1 Nr. 6, § 201 BGB |
| Titulierte, künftig fällig werdende wiederkehrende Leistungen (laufende Zinsen nach Titulierung) | 3 Jahre | Schluss des Jahres der Fälligkeit | § 197 Abs. 2, §§ 195, 199 BGB |
| Verbraucherdarlehen: Zinsen nach Titulierung | 30 Jahre; § 197 Abs. 2 BGB gilt nicht | Rechtskraft bzw. Errichtung | § 497 Abs. 3 BGB |

**Hemmung und Neubeginn:**

- **Hemmung durch Mahnbescheid:** Die Zustellung des Mahnbescheids hemmt die Verjährung (§ 204 Abs. 1 Nr. 3 BGB). Die Hemmung endet sechs Monate nach rechtskräftiger Entscheidung oder anderweitiger Beendigung des Verfahrens (§ 204 Abs. 2 BGB).
- **Hemmung bei Verbraucherdarlehen:** Ab Eintritt des Verzugs bis zur Titulierung ist die Verjährung gehemmt, höchstens zehn Jahre ab Entstehung (§ 497 Abs. 3 BGB).
- **Neubeginn:**
  - durch Anerkenntnis, ausdrücklich auch durch Abschlagszahlung, Zinszahlung oder Sicherheitsleistung (§ 212 Abs. 1 Nr. 1 BGB);
  - durch Vornahme oder Beantragung einer Vollstreckungshandlung (§ 212 Abs. 1 Nr. 2 BGB).
- **Umsetzung Release 1:** Jede erfasste Zahlung, deren Buchung nicht storniert ist (E-26), und jede erfasste Vollstreckungshandlung löst den Neubeginn für alle Bestandteile der Akte aus. Abweichungen klärt Prüfpunkt P-02. Ob das auch für eine Zahlung gilt, die per Rücklastschrift zurückgegeben wurde, legt dieses Dokument nicht fest (Prüfpunkt P-17).

**Pflichthinweis in der Oberfläche:** „Verjährung tritt nicht von selbst ein, sie muss als Einrede erhoben werden (§ 214 Abs. 1 BGB). Die Berechnung ist eine Näherung auf Grundlage der erfassten Ereignisse. Fehlt ein Ereignis, ist das Ergebnis falsch.“

---

## 6 Statusmodell

**Status (Lebenszyklus):** `offen` → `mahnverfahren` → `tituliert` → `ausgeglichen` → `nachwirkung` → `geschlossen`

**Merkmale (unabhängig vom Status):** `ratenplan_aktiv`, `vollstreckung_aktiv`, `bestritten`, `schuldnerverzeichnis_eingetragen`, `verjaehrung_eingewandt`

| Von | Nach | Auslöser |
|---|---|---|
| `offen` | `mahnverfahren` | Ereignis `zustellung_mahnbescheid` |
| `mahnverfahren` | `tituliert` | Ereignis `zustellung_vollstreckungsbescheid` |
| `offen` | `tituliert` | Urteil, Vergleich oder Urkunde erfasst |
| jeder außer `geschlossen` | `ausgeglichen` | Restschuld (Kap. 4.1) = 0,00 € |
| `ausgeglichen` | `nachwirkung` | automatisch; Nachwirkungs-Aufgaben werden angelegt |
| `nachwirkung` | `geschlossen` | alle Aufgaben erledigt bzw. Informationsfristen abgelaufen |
| `ausgeglichen`, `nachwirkung` | vorheriger Status | Storno einer Zahlung oder neue Kosten; weitere Auslöser: Prüfpunkt P-19 |

**Nachwirkungs-Aufgaben bei Ausgleich:**

1. Quittung anfordern (§ 368 BGB).
2. Titel herausverlangen (§ 371 BGB analog). Bei Zahlung an den Gerichtsvollzieher liefert dieser den Titel aus (§ 757 Abs. 1 ZPO).
3. Falls eingetragen: vorzeitige Löschung im Schuldnerverzeichnis beantragen (§ 882e Abs. 3 Nr. 1 ZPO).
4. Erledigungsmeldung bei Auskunfteien prüfen, per Datenkopie nach Art. 15 DSGVO, frühestens vier Wochen nach Ausgleich.
5. Löschdatum der Auskunftei überwachen.

**Eskalation bei verweigerter Titelherausgabe:** Frist setzen. Vollstreckt der Gläubiger trotz Erfüllung weiter, zeigt das System einen Hinweis auf die Vollstreckungsabwehrklage (§ 767 ZPO) und die einstweilige Einstellung (§ 769 ZPO) und empfiehlt anwaltliche Hilfe. Die Software formuliert diese Schritte nicht selbst.

---

## 7 Stammdaten

Stammdaten liegen versioniert im Repository unter `stammdaten/`. Jede Datei nennt Gültigkeit, Quelle und Prüfer. Die Anwendung lädt sie beim Start. Fehlt für einen Stichtag ein gültiger Eintrag, rechnet sie nicht, sondern meldet einen Fehler. Lieber keine Zahl als eine falsche.

```yaml
# stammdaten/basiszinssatz.yaml
quelle: Deutsche Bundesbank, Bekanntgabe nach § 247 Abs. 2 BGB
geprueft_von: "<Name>"
hinweis: Vollständige Reihe ab 2002-01-01 aus der Bundesbank-Zeitreihe ergänzen
eintraege:
  - gueltig_ab: 2025-07-01
    satz: "1.27"
  - gueltig_ab: 2026-01-01
    satz: "1.27"
  - gueltig_ab: 2026-07-01
    satz: "1.52"
```

```yaml
# stammdaten/pfaendungsfreigrenzen.yaml
quelle: Pfändungsfreigrenzenbekanntmachung 2026, BGBl. 2026 I Nr. 80
geprueft_von: "<Name>"
eintraege:
  - gueltig_ab: 2026-07-01
    gueltig_bis: 2027-06-30
    grundfreibetrag_monat: "1587.40"
    erhoehung_erste_person: "597.42"
    erhoehung_weitere_person: "332.83"   # 2. bis 5. unterhaltsberechtigte Person
    vollpfaendung_ab: "4866.30"
    p_konto_grundfreibetrag_monat: "1590.00"   # auf volle 10 € aufgerundet
```

Weitere Dateien in Release 1:
- `feiertage.yaml` (je Bundesland)
- `vollstreckungsgerichte.yaml` (Schleswig-Holstein: Zentrales Vollstreckungsgericht beim Amtsgericht Schleswig)
- `auskunfteien.yaml` (Löschfristen)

Die Pfändungsfreigrenzen dienen in Release 1 nur der Information auf dem Dashboard.

**CI-Prüfung:** Liegt der jüngste Basiszins-Eintrag mehr als sechs Monate zurück oder läuft die Pfändungstabelle in weniger als 30 Tagen aus, schlägt der Build fehl.

---

## 8 Import von Zahlungen

- **Formate:**
  - CSV mit Profilen je Bank (Trennzeichen, Datumsformat, Spaltenzuordnung konfigurierbar)
  - CAMT.053 (ISO 20022); welches Datum des Auszugs die Wertstellung wird, klärt Prüfpunkt P-16
- **Ablauf:**
  1. Datei hochladen.
  2. Belastungen werden als Zahlungskandidaten erkannt.
  3. Duplikate werden über einen Hash aus Datum, Betrag, Gegen-IBAN und Verwendungszweck erkannt.
  4. Das System macht einen Zuordnungsvorschlag.
  5. Der Nutzer bestätigt.
  6. Erst dann entstehen je Akte eine Buchung und ein Ereignis `zahlung`.
- **Zuordnungsregeln:** Gegen-IBAN des Gläubigers, Aktenzeichen im Verwendungszweck, Betrag entspricht der vereinbarten Rate.
- **Ohne Bestätigung wird nichts gebucht.**
- **Datenminimierung:** Nicht zugeordnete Zeilen werden nach dem Import verworfen. Die Importdatei wird nicht aufbewahrt.

---

## 9 Schreiben

Grundlage sind Word-Vorlagen unter `vorlagen/verbindlichkeiten/*.docx` mit Platzhaltern (docxtpl). PDFs erzeugt Gotenberg. Vorlagen lassen sich ohne Programmierkenntnisse in Word pflegen.

| Nr. | Schreiben | Empfänger | Grundlage |
|---|---|---|---|
| V-01 | Anforderung einer Forderungsaufstellung | Gläubiger, Inkasso | – |
| V-02 | Ratenzahlungsangebot mit Tilgungsbestimmung | Gläubiger | § 366 Abs. 1 BGB |
| V-03 | Anforderung von Quittung und Herausgabe des Titels | Gläubiger | §§ 368, 371 BGB analog |
| V-04 | Antrag auf vorzeitige Löschung aus dem Schuldnerverzeichnis | Zentrales Vollstreckungsgericht | § 882e Abs. 3 Nr. 1 ZPO |
| V-05 | Antrag auf Datenkopie | Auskunftei | Art. 15 DSGVO |
| V-06 | Erhebung der Einrede der Verjährung | Gläubiger | § 214 Abs. 1 BGB |

Jeder Entwurf trägt den Vermerk „Vor Versand prüfen“. V-06 wird nur nach ausdrücklicher Bestätigung erzeugt und enthält einen Hinweis auf Schuldnerberatung und anwaltliche Hilfe.

---

## 10 Dashboard (Release 1)

| Widget | Inhalt |
|---|---|
| Restschuld | Summe über alle Akten, aufgeteilt in Hauptforderung, Zinsen, Kosten |
| Fristen | Nächste Fristen mit Ampel; Notfristen stehen immer oben |
| Raten | Fortschritt je Akte, Warnung „Rate deckt Zinszuwachs nicht“ |
| Zinszuwachs | Zinszuwachs pro Monat über alle Akten |
| Status | Akten nach Status |
| Nachwirkung | Offene Aufgaben, Löschdaten |

Architektur: Widgets sind registrierte Komponenten mit eigener API-Abfrage. Spätere Module melden eigene Widgets an, ohne dass das Dashboard geändert wird. Jedes Diagramm hat eine gleichwertige Tabellenansicht (Barrierefreiheit).

---

## 11 Sicherheit und Betrieb

### 11.1 Sicherheit

- **Netz:** Standardmäßig ist die Anwendung nur an `127.0.0.1` gebunden. Optional gibt es einen Heimnetz-Modus mit HTTPS über einen Reverse Proxy und eine lokale Zertifizierungsstelle (Prüfpunkt T-01). Ports werden nie ins Internet freigegeben.
- **Anmeldung:** Passwörter mit Argon2id, serverseitige Sitzungen, CSRF-Schutz, Sperre nach Fehlversuchen.
- **Rechte:** Jede Akte hat einen Eigentümer und optionale Freigaben (lesen, bearbeiten). Im Modus `haushalt_gemeinsam` sind alle Akten für alle Benutzer freigegeben.
- **Dokumente:** AES-256-GCM mit einem Haushaltsschlüssel (DEK).
  - Der DEK ist je Benutzer mit einem aus dessen Passwort abgeleiteten Schlüssel (Argon2id) umschlossen und zusätzlich mit dem Recovery-Key.
  - Ein Passwortwechsel umschließt den DEK nur neu.
  - Wer Passwort und Recovery-Key verliert, verliert die Dokumente.
- **Datenbank:** Nicht feldverschlüsselt. Geschützt wird sie über Systemverschlüsselung (BitLocker, FileVault, LUKS). Der Installer prüft das und warnt, wenn sie fehlt.
- **Datenbankrollen (E-19):**
  - Die Eigentümerrolle besitzt die Tabellen und führt nur die Migrationen aus.
  - Die Anwendung verbindet sich mit der Laufzeitrolle. Sie darf auf `buchung`, `posting` und `konto_sperre` (Kap. 4.4) nur lesen und einfügen, also kein UPDATE, DELETE oder TRUNCATE, und kann keine Trigger abschalten.
  - Die Rollen legt ein eigenes Bootstrap-Skript an, nicht die Migration, weil Rollen für den ganzen Datenbank-Cluster gelten. CI, Tests und Installer nutzen dasselbe Skript.
  - Die Tests laufen als Laufzeitrolle; ein Test weist nach, dass sie Trigger nicht abschalten kann.
  - Das schützt gegen eigenen Code, auch KI-generierten, der Buchungen ändern will. Gegen den Superuser der Datenbank schützt es nicht und soll es nicht.
- **Backups:** Täglich, bestehend aus Datenbank-Dump und Dokumenten, verschlüsselt. Das Ziel ist frei wählbar (externe Platte, NAS). Der Installer führt eine Wiederherstellungsprobe durch.
- **Protokolle:** Keine personenbezogenen Inhalte, also keine Namen, IBANs oder Aktenzeichen.
- **Audit-Log:** Nur anhängend. Es hält fest, wer wann welche Entität geändert hat.
- **AGPL § 13:** Die Fußzeile verlinkt auf den Quellcode der laufenden Version und auf die Lizenzhinweise der verwendeten Fremdkomponenten.

### 11.2 Installer

| System | Form | Voraussetzung |
|---|---|---|
| Linux | `install.sh` | Docker Engine und Compose; werden bei Bedarf installiert |
| macOS | Installationsskript | Docker Desktop oder OrbStack; wird geprüft, Download wird angeboten |
| Windows | PowerShell-Skript | Docker Desktop mit WSL2; wird geprüft, bei fehlender Virtualisierung folgt eine Anleitung |

**Ablauf der Installation:**
1. Voraussetzungen prüfen.
2. Betriebsart wählen.
3. Geheimnisse erzeugen.
4. Container starten.
5. Ersten Benutzer anlegen.
6. Recovery-Key anzeigen; der Nutzer muss die Sicherung bestätigen.
7. Backup-Ziel festlegen.
8. Systemverschlüsselung prüfen.

**Ablauf eines Updates:**
1. Backup.
2. Neue Images laden.
3. Migrationen ausführen.
4. Funktionsprüfung.
5. Bei Fehler Rückkehr zur Vorversion.

### 11.3 Lizenzhinweise Dritter

Die Lizenzen der Abhängigkeiten verlangen, dass ihre Lizenztexte und Copyright-Vermerke mitgeliefert werden, sobald ihr Code weitergegeben wird. Das Repository selbst gibt keinen fremden Code weiter; ausgelieferte Pakete schon.

- **Automatisch erzeugt, nie von Hand gepflegt:** Bei jedem Build entsteht eine Datei `THIRD-PARTY-LICENSES` mit den vollständigen Lizenztexten und den Inhalten von `NOTICE`-Dateien (Apache-2.0).
- **Docker-Images:** enthalten die Datei für alle Python-Abhängigkeiten.
- **Frontend-Bundle:** enthält die Datei für alle npm-Abhängigkeiten, weil das Bündeln die Lizenzkommentare im Code entfernt.
- **Oberfläche:** eine Seite „Lizenzen“, verlinkt neben dem Quellcode-Link.
- **Native Bibliotheken (E-20):** Bringt ein Python-Paket native Bibliotheken mit (z. B. libpq und OpenSSL in `psycopg-binary`), gilt die Lizenzliste auch für sie, und sie gehören in `THIRD-PARTY-LICENSES`. Maßgeblich ist die Lizenz, die das Ursprungsprojekt für die Bibliothek erklärt; Lizenzen einzelner Dateien darin werden nicht gegen die Liste geprüft, ihre Lizenz- und Hinweistexte aber vollständig übernommen. Der Lizenztest liest nur Python-Metadaten; deshalb nennt der Pull Request ihre Lizenzen. Für das Betriebssystem des Docker-Basis-Images gelten dessen eigene Lizenzhinweise (Debian: `/usr/share/doc/*/copyright`). Sie werden mit dem Image ausgeliefert und nicht gegen die Liste geprüft.
- **Release:** Zu jedem Release gehört eine SBOM (CycloneDX oder SPDX).
- **Prüfung:** Erlaubte Lizenzen stehen in `CLAUDE.md`; die CI prüft sie bei jedem Pull Request.

---

## 12 Qualitätssicherung

- **Golden Files** (`tests/golden/<modul>/*.yaml`, hier `tests/golden/verbindlichkeiten/`): je Fall eine anonymisierte reale Forderungsaufstellung. Die Erwartungswerte stammen aus der Aufstellung des Gläubigers oder aus manueller Prüfung, nie aus dem Programm selbst. Nur Menschen ändern Erwartungswerte. Ziel: 10 bis 20 Fälle vor Release 1, verteilt auf alle Titelarten und beide Anrechnungsregeln.
- **Property-Tests:**
  - Summe der Postings je Buchung = 0
  - Die Anrechnung verteilt exakt den Zahlbetrag, höchstens bis zur Restschuld; der Rest ist die berechnete Überzahlung
  - Zinskonten erzeugen keine Zinsen
  - Storno plus Neubuchung ergibt denselben Saldo wie die korrigierte Buchung: bei Wertstellung im offenen Zeitraum zu jedem Stichtag, bei Wertstellung in einem festgeschriebenen Zeitraum zu jedem Stichtag ab dem Tag der Erfassung. Zinsen, Anrechnung und Fristen ergeben zu jedem Stichtag dasselbe wie mit der korrigierten Buchung
  - Eine stornierte Zahlung ergibt dieselben Zinsen, dieselbe Anrechnung und dieselben Fristen einschließlich Verjährung wie ein Fall, in dem es die Zahlung nie gab
  - Eine Festschreibung ändert kein Rechenergebnis
  - Nach dem Setzen einer Kontosperre ändert sich der Saldo des Kontos bis zum Sperrdatum nicht mehr
- **Statische Prüfung:** Ruff, Pyright im Strict-Modus, Verbot von `float` in Fachmodulen.
- **Review:** Jeder Pull Request wird von einer zweiten KI gegen dieses Dokument, `CLAUDE.md` und den Diff geprüft. Das Ergebnis erscheint als PR-Kommentar.
- **Community:** `SECURITY.md` mit Meldeweg für Sicherheitslücken; Issue-Vorlage für fachliche Fehler mit anonymisiertem Beispiel.

Beispiel für ein Golden File:

```yaml
id: GF-0001
beschreibung: Vollstreckungsbescheid, Verbraucher, gesetzlicher Verzugszins, zwei Raten
quelle: anonymisierte Forderungsaufstellung, Stand 2026-09-30
geprueft_von: "<Name>"
akte:
  titelart: vollstreckungsbescheid
  verbraucherdarlehen: false
  anrechnung: bgb_367
  tageszaehlung: act_365
  rundung: je_periode
  zinsbeginn: genannter_tag
bestandteile:
  - art: hauptforderung
    betrag: "<aus Aufstellung>"
    zinsregel:
      typ: gesetzlich_288_1
      ab: "<aus Titel>"
  - art: kosten_verfahren
    betrag: "<aus Aufstellung>"
    zinsregel:
      typ: keine
zahlungen:
  - datum: "<aus Kontoauszug>"
    betrag: "<aus Kontoauszug>"
erwartung:
  stichtag: 2026-09-30
  hauptforderung: "<aus Aufstellung>"
  zinsen: "<aus Aufstellung>"
  kosten: "<aus Aufstellung>"
  gesamt: "<aus Aufstellung>"
toleranz: "0.00"
```

---

## 13 Meilensteine (ohne Termine)

| Nr. | Meilenstein | Ergebnis |
|---|---|---|
| M0 | Repo-Fundament | Lizenz, `CLAUDE.md`, CI (Ruff, Pyright, pytest), DCO-Prüfung, `SECURITY.md`, Issue-Vorlagen |
| M1 | Buchungskern | Konten, Buchungen, Postings, Invarianten, Storno |
| M2 | Stammdaten und Zinsen | Basiszinsreihe, Zins-Engine, erste Golden Files |
| M3 | Anrechnung | Regeln nach § 367 und § 497 BGB, Abgleich mit der Forderungsaufstellung |
| M4 | Fristen und Status | Fristenkatalog, Verjährung, Statusmodell, Nachwirkungs-Aufgaben |
| M5 | Oberfläche | API, KERN-Grundgerüst, Akten, Dashboard, Seite „Lizenzen“, Lizenzhinweise im Frontend-Bundle |
| M6 | Import | CSV-Profile, CAMT.053, Zuordnung |
| M7 | Schreiben | V-01 bis V-06, PDF |
| M8 | Dokumente und Backup | Verschlüsselung, Recovery-Key, Backup und Restore |
| M9 | Installer | Linux, dann macOS, dann Windows; Docker-Images mit `THIRD-PARTY-LICENSES` |
| M10 | Release 0.1 | Öffentliche Beta mit SBOM |

---

## 14 Offene Prüfpunkte

Geschlossene Prüfpunkte stehen im Entscheidungsprotokoll (Kap. 2); ihre Nummern werden nicht neu vergeben. Geschlossen sind P-04 (E-22), P-05 (E-23), P-06 (E-24) und P-12 (E-21).

| Nr. | Frage | Auswirkung |
|---|---|---|
| P-01 | Gilt § 193 BGB für das Ende der Verjährungsfrist? | Fristende an Wochenenden und Feiertagen |
| P-02 | Wirkt der Neubeginn durch Teilzahlung (§ 212 Abs. 1 Nr. 1 BGB) für alle Bestandteile oder nur für den angerechneten? | Verjährungsberechnung |
| P-03 | Verzinsung von Verfahrenskosten aus dem Mahnverfahren: ab wann, zu welchem Satz? | Zinsregel für Kosten |
| P-07 | Reihenfolge innerhalb der Kosten bei § 367 Abs. 1 BGB | Anrechnung |
| P-08 | Plausibilitätsprüfung der Höhe von Inkassokosten: Release 1 oder später? | Häufigste Abweichungsquelle |
| P-09 | Wortlaut von Disclaimer und Abgrenzung zur Rechtsdienstleistung | Haftung |
| P-10 | Löschkonzept: Wie werden eine irrtümlich angelegte Akte oder ein ganzer Haushalt endgültig gelöscht, obwohl Buchungen unveränderlich sind? Entscheidung spätestens mit M8 | Unveränderlichkeit der Buchungen, Datenschutz |
| P-11 | Gläubigersicht: eigenes Modul mit eigenen Tabellen, oder Teil des Moduls Verbindlichkeiten (dann mit `akte.richtung`)? Wie wird die gemeinsame Rechenlogik (Zinsen, Anrechnung) genutzt, ohne E-17 zu verletzen? Entscheidung vor Beginn der Gläubigersicht | Zuschnitt der Module, Tabelle `akte` |
| P-13 | Rundung `am_ende` (E-23): Was bedeutet sie bei Zahlungen innerhalb einer Zinsperiode? Ist das Ende der Stichtag der Abfrage bzw. der Festschreibung? Wird der Zinsbetrag gerundet, auf den eine Zahlung angerechnet wird? Entscheidung vor der Umsetzung (M2/M3) | Rundung bei `am_ende`; wird der Zinsbetrag nicht gerundet, entstehen in der Anrechnungsbuchung Beträge unter einem Cent |
| P-14 | Zinsbasis am Zahlungstag: Gilt am Tag der Zahlung schon die verminderte Zinsbasis oder erst ab dem Folgetag? | Zinstage je Zinsperiode (Kap. 5.2 Schritte 2 und 3) |
| P-15 | Tageszählung `30_360` (E-22): Welche Variante ist gemeint (z. B. deutsche Methode, US/ISDA)? | Zinsberechnung bei `30_360` |
| P-16 | Import aus CAMT.053 (M6): Welches Datum des Kontoauszugs wird die Wertstellung der Buchung, Buchungstag oder Valuta? | Wertstellung importierter Zahlungen und damit Zinsen, Anrechnung und Fristen |
| P-17 | Rücklastschrift und zurückgegebene Zahlungen: Zählt eine zurückgegebene Zahlung für den Neubeginn der Verjährung (§ 212 Abs. 1 Nr. 1 BGB) noch? Das ist eine Rechtsfrage, die das Fachkonzept nicht beantwortet. Wie wird eine Rücklastschrift erfasst und gebucht? Fest steht nur: Sie ist kein Storno, sondern ein tatsächliches Ereignis (E-26) | Verjährung (Kap. 5.5), Ereignistypen, Buchungsarten |
| P-18 | Ereignis `zahlung` und Buchung: Sind das Datum des Ereignisses und die Wertstellung der Buchung immer gleich? Kap. 3 richtet Fristen nach der Wertstellung, Kap. 5.4 und 5.5 leiten sie aus dem Ereignis ab. Bekommt die Neubuchung nach Storno und Neubuchung ein eigenes Ereignis `zahlung`? Ohne Ereignis gäbe es keinen Neubeginn der Verjährung. Welches Datum für den Neubeginn der Verjährung zählt, berührt eine Rechtsfrage | Fristen, Verjährung |
| P-19 | Rückweg im Statusmodell: Jede Ursache aus Kap. 5.2 Schritt 7 kann die Restschuld wieder über 0,00 € heben (nachgetragenes Ereignis, geänderte Zinsregel, umgestellter Aktenparameter, korrigierte Stammdaten). Soll der Auslöser des Rückwegs aus `ausgeglichen` und `nachwirkung` „Restschuld > 0,00 €“ heißen statt nur „Storno einer Zahlung oder neue Kosten“? | Statusmodell (Kap. 6), Nachwirkungs-Aufgaben |
| P-20 | Überzahlung: Wird eine Überzahlung auf Positionen angerechnet, die später entstehen, z. B. neue Vollstreckungskosten? Wenn ja, ab welcher Wertstellung? | Anrechnung, Restschuld, Status |
| T-01 | Heimnetz-Modus: lokale Zertifizierungsstelle oder nur `localhost`? | Bedienbarkeit gegen Sicherheit |
| T-02 | Docker-Image (M9): psycopg gegen die libpq des Debian-Basis-Images bauen statt das Binary-Wheel `psycopg-binary` zu nutzen? Die nativen Bibliotheken kämen dann aus Debians Hauptarchiv, dessen Lizenzprüfung auf Dateiebene stattfindet | Einzelne Dateien in den gebündelten Bibliotheken des Wheels stehen unter Lizenzen, die nicht auf der Liste stehen (RSA-MD, Brian-Gladman-3-Clause, OLDAP-2.0.1) oder haben keine eigene Lizenzerteilung (`rc4.c` in krb5) |
| T-03 | Wiederherstellung aus einer Sicherung: Werden nur die Daten in ein schon migriertes Schema eingespielt, greifen die Trigger auf `buchung`, `posting` und `konto_sperre`. `erfasst_am` und `erfasst_txid` würden überschrieben (`erfasst_am` auch in `konto_sperre`); damit ginge die Historie verloren, wann etwas bekannt war. Postings würden abgelehnt, wenn `buchung` und `posting` in getrennten Transaktionen eingespielt werden oder `konto_sperre` vor `posting` kommt. Dazu kommt die Prüfung der Isolationsstufe. Ein vollständiger Dump legt die Trigger dagegen erst nach den Daten an (post-data); beim Einspielen greift dann keiner von ihnen. Gelöst ist die Wiederholung der Transaktionsnummer: Im neuen Cluster beginnt der Zähler wieder unten, sodass die Nummer einer eingespielten Buchung wieder vorkommen kann. Die Posting-Prüfung verlangt deshalb zusätzlich `erfasst_am = now()` (Kap. 4.4). Zu klären bis M8: Wie laufen Backup und Restore? Zum Beispiel als Eigentümerrolle in einer Transaktion mit abgeschalteten Triggern, danach ein Prüflauf aller Invarianten | Backup und Wiederherstellungsprobe des Installers (Kap. 11) |
