// SPDX-License-Identifier: AGPL-3.0-or-later
// Beträge kommen und gehen als Text (CLAUDE.md, Geld). Hier wird nur Text umgeformt, nie mit
// Zahlen gerechnet: Kein Betrag wird zur JavaScript-Zahl.

const BETRAG = /^(-?)(\d+)(?:\.(\d+))?$/;

/** "1234.5" → "1.234,50 €"; mehr als zwei Nachkommastellen bleiben erhalten. */
export function formatiereBetrag(text: string): string {
  const treffer = BETRAG.exec(text);
  if (treffer === null) {
    return text;
  }
  const [, vorzeichen = "", ganz = "0", nachkomma = ""] = treffer;
  const gruppen = ganz.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const stellen = nachkomma.padEnd(2, "0");
  return `${vorzeichen === "-" ? "−" : ""}${gruppen},${stellen} €`;
}

const EINGABE = /^\d{1,15}(?:,\d{1,4})?$/;

/**
 * Eingabe wie "1.234,56" oder "1234,56" in den Text der Schnittstelle ("1234.56") umformen.
 * Liefert null, wenn die Eingabe kein Betrag ist.
 */
export function betragAusEingabe(eingabe: string): string | null {
  const ohneLeer = eingabe.replace(/\s|€/g, "");
  const ohnePunkte = /^\d{1,3}(\.\d{3})+(,\d+)?$/.test(ohneLeer)
    ? ohneLeer.replace(/\./g, "")
    : ohneLeer;
  if (!EINGABE.test(ohnePunkte)) {
    return null;
  }
  return ohnePunkte.replace(",", ".");
}
