// SPDX-License-Identifier: AGPL-3.0-or-later
// Hilfen für Tests der Oberfläche: Antworten der Schnittstelle nachbilden, Barrieren prüfen.
import axe from "axe-core";
import { vi } from "vitest";

type Antworten = Record<string, unknown>;

/** fetch ersetzen: Pfad (ohne Query) → JSON-Antwort; unbekannte Pfade antworten mit 404. */
export function bildeApiNach(antworten: Antworten): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((anfrage: Request) => {
      const pfad = new URL(anfrage.url).pathname;
      const koerper = antworten[pfad];
      const status = koerper === undefined ? 404 : 200;
      return Promise.resolve(
        new Response(JSON.stringify(koerper ?? { detail: "Nicht gefunden." }), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }),
  );
}

/** Verstöße gegen WCAG 2.1 A/AA laut axe-core; Farbkontraste prüft die Testumgebung nicht. */
export async function barrieren(element: Element): Promise<string[]> {
  const ergebnis = await axe.run(element, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
    rules: { "color-contrast": { enabled: false } },
  });
  return ergebnis.violations.map((v) => `${v.id}: ${v.help}`);
}
