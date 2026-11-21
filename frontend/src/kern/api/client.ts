// SPDX-License-Identifier: AGPL-3.0-or-later
// Client der JSON-Schnittstelle. Die Typen stammen aus openapi.json (npm run api:typen) und
// werden nie von Hand geschrieben (CLAUDE.md, Stack).
import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  // Erst beim Aufruf nachschlagen, damit Tests fetch ersetzen können.
  fetch: (anfrage: Request) => globalThis.fetch(anfrage),
});

/** Lesbare Meldung aus einer Fehlerantwort von FastAPI. */
export function fehlertext(fehler: unknown): string {
  if (typeof fehler === "object" && fehler !== null && "detail" in fehler) {
    const detail = (fehler as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((eintrag: unknown) =>
          typeof eintrag === "object" && eintrag !== null && "msg" in eintrag
            ? String((eintrag as { msg: unknown }).msg)
            : String(eintrag),
        )
        .join(" ");
    }
  }
  return "Die Anfrage ist fehlgeschlagen.";
}
