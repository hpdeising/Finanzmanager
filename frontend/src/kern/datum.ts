// SPDX-License-Identifier: AGPL-3.0-or-later
// Fachliche Daten kommen als YYYY-MM-DD (CLAUDE.md, Datum) und werden nur als Text umgeformt.

/** "2025-03-17" → "17.03.2025"; ohne Datum ein Gedankenstrich. */
export function formatiereDatum(text: string | null | undefined): string {
  if (!text) {
    return "–";
  }
  const [jahr, monat, tag] = text.split("-");
  return jahr && monat && tag ? `${tag}.${monat}.${jahr}` : text;
}

/** Heutiges Datum in der Zeitzone des Browsers als YYYY-MM-DD. */
export function heute(): string {
  const jetzt = new Date();
  const monat = String(jetzt.getMonth() + 1).padStart(2, "0");
  const tag = String(jetzt.getDate()).padStart(2, "0");
  return `${jetzt.getFullYear()}-${monat}-${tag}`;
}
