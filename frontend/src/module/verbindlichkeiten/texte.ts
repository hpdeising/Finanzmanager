// SPDX-License-Identifier: AGPL-3.0-or-later
// Anzeigenamen der Fachbegriffe. Die Typen erzwingen einen Namen für jeden Wert der
// Schnittstelle; ein neuer Wert im Backend fällt so schon bei der Typprüfung auf.
import type { Schemas } from "../../kern/api/client";

export const STATUS: Record<Schemas["Status"], string> = {
  offen: "Offen",
  mahnverfahren: "Mahnverfahren",
  tituliert: "Tituliert",
  nachwirkung: "Nachwirkung",
  ausgeglichen: "Ausgeglichen",
  geschlossen: "Geschlossen",
};

export const MERKMAL: Record<Schemas["Merkmal"], string> = {
  ratenplan_aktiv: "Ratenplan aktiv",
  vollstreckung_aktiv: "Vollstreckung aktiv",
  bestritten: "Bestritten",
  schuldnerverzeichnis_eingetragen: "Im Schuldnerverzeichnis eingetragen",
  verjaehrung_eingewandt: "Verjährung eingewandt",
};

export const BESTANDTEILART: Record<Schemas["Bestandteilart"], string> = {
  hauptforderung: "Hauptforderung",
  zinsen: "Zinsen (fester Betrag)",
  kosten_vorgerichtlich: "Vorgerichtliche Kosten",
  kosten_verfahren: "Verfahrenskosten",
  kosten_vollstreckung: "Vollstreckungskosten",
};

export const ZINSREGELTYP: Record<Schemas["Zinsregeltyp"], string> = {
  gesetzlich_288_1: "Basiszinssatz + 5 Prozentpunkte (§ 288 Abs. 1 S. 2 BGB)",
  gesetzlich_288_2: "Basiszinssatz + 9 Prozentpunkte (§ 288 Abs. 2 BGB)",
  kostenfestsetzung: "Kostenfestsetzung: Basiszinssatz + 5 Prozentpunkte (§ 104 Abs. 1 S. 2 ZPO)",
  basiszins_plus: "Basiszinssatz + Aufschlag laut Titel oder Vertrag",
  fest: "Fester Jahreszins laut Titel oder Vertrag",
  keine: "Keine Zinsen (Pause)",
};

export const EREIGNISTYP: Record<Schemas["Ereignistyp"], string> = {
  zustellung_mahnbescheid: "Mahnbescheid zugestellt",
  zustellung_vollstreckungsbescheid: "Vollstreckungsbescheid zugestellt",
  zustellung_urteil: "Urteil zugestellt",
  rechtskraft: "Rechtskraft",
  errichtung_titel: "Titel errichtet (Vergleich, Urkunde)",
  eintragungsanordnung: "Eintragungsanordnung (Schuldnerverzeichnis)",
  zahlung: "Zahlung",
  vollstreckungsantrag: "Vollstreckungsantrag",
  vollstreckungshandlung: "Vollstreckungshandlung",
  anerkenntnis: "Anerkenntnis",
  glaeubigerwechsel: "Gläubigerwechsel",
  anrechnung_abgelehnt: "Anrechnung abgelehnt",
  ausgleich: "Ausgleich",
  quittung_erhalten: "Quittung erhalten",
  titel_erhalten: "Titel erhalten",
  loeschung_schuldnerverzeichnis: "Löschung im Schuldnerverzeichnis",
  erledigt_gemeldet_auskunftei: "Erledigung bei Auskunftei gemeldet",
  verjaehrung_eingewandt: "Verjährung eingewandt",
  einspruch: "Einspruch",
  mahnverfahren_ohne_titel_beendet: "Mahnverfahren ohne Titel beendet",
  letzte_verfahrenshandlung: "Letzte Verfahrenshandlung",
  verzug_eingetreten: "Verzug eingetreten",
  zustellung_kostenfestsetzungsbeschluss: "Kostenfestsetzungsbeschluss zugestellt",
  akte_geschlossen: "Akte geschlossen",
  ratenplan_vereinbart: "Ratenplan vereinbart",
  ratenplan_beendet: "Ratenplan beendet",
  vollstreckungsmassnahme_begonnen: "Vollstreckungsmaßnahme begonnen",
  vollstreckungsmassnahme_aufgehoben: "Vollstreckungsmaßnahme aufgehoben",
  forderung_bestritten: "Forderung bestritten",
  bestreiten_beendet: "Bestreiten beendet",
  sofortige_beschwerde: "Sofortige Beschwerde (gegen Kostenfestsetzung)",
};

export const FRISTART: Record<Schemas["Fristart"], string> = {
  notfrist: "Notfrist",
  prozessual: "Prozessuale Frist",
  materiell: "Materielle Frist",
  information: "Information",
  aufgabe: "Aufgabe",
};

export const AUFGABE: Record<Schemas["Aufgabentyp"], string> = {
  quittung_anfordern: "Quittung anfordern",
  titel_herausverlangen: "Titel herausverlangen",
  vorzeitige_loeschung: "Vorzeitige Löschung im Schuldnerverzeichnis beantragen",
  auskunftei_pruefen: "Erledigungsmeldung bei Auskunfteien prüfen",
  auskunftei_loeschdatum_ueberwachen: "Löschdatum der Auskunftei überwachen",
};
