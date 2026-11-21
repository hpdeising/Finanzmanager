// SPDX-License-Identifier: AGPL-3.0-or-later
// Lizenzen der npm-Pakete gegen die Liste in CLAUDE.md prüfen (dieselbe Logik wie
// backend/tests/test_lizenzen.py). Neue Lizenzen kommen nur durch eine Änderung der Liste
// in CLAUDE.md dazu, nie durch eine Ausnahme hier.

/** SPDX-Kennung → Lizenzfamilie aus CLAUDE.md. */
export const SPDX_FAMILIE = {
  MIT: "MIT",
  "BSD-2-Clause": "BSD",
  "BSD-3-Clause": "BSD",
  ISC: "ISC",
  "Apache-2.0": "Apache-2.0",
  "MPL-2.0": "MPL-2.0",
  "PSF-2.0": "PSF-2.0",
  "Python-2.0": "PSF-2.0",
  PostgreSQL: "PostgreSQL",
  "OLDAP-2.8": "OLDAP-2.8",
  "LGPL-2.1-only": "LGPL",
  "LGPL-2.1-or-later": "LGPL",
  "LGPL-3.0-only": "LGPL",
  "LGPL-3.0-or-later": "LGPL",
  "GPL-2.0-or-later": "GPL-3.0",
  "GPL-3.0-only": "GPL-3.0",
  "GPL-3.0-or-later": "GPL-3.0",
  "AGPL-3.0-only": "AGPL-3.0",
  "AGPL-3.0-or-later": "AGPL-3.0",
};

/** KERN-UX (EUPL-1.2) ist nur unverändert erlaubt (CLAUDE.md) und nur für diese Pakete. */
export const KERN_UX = /^@kern-ux\//;

/** Liste „Erlaubte Lizenzen für Abhängigkeiten“ aus dem Text von CLAUDE.md. */
export function erlaubteFamilien(claudeMd) {
  const treffer = /Erlaubte Lizenzen für Abhängigkeiten: (.+?)\.\s/.exec(claudeMd);
  if (treffer === null) {
    throw new Error("CLAUDE.md enthält keine Liste „Erlaubte Lizenzen für Abhängigkeiten“.");
  }
  return new Set(treffer[1].split(",").map((name) => name.trim()));
}

/**
 * SPDX-Ausdruck prüfen. Reiner OR-Ausdruck: eine erlaubte Alternative genügt. Alles andere
 * (AND, Klammern, WITH): jede genannte Kennung muss erlaubt sein.
 */
export function erlaubtNachSpdx(roh, erlaubt, paket = "") {
  // Äußere Klammern um den ganzen Ausdruck ändern nichts: "(MIT OR CC0-1.0)".
  const ausdruck = /^\([^()]*\)$/.test(roh.trim()) ? roh.trim().slice(1, -1) : roh;
  const kennungen = (ausdruck.match(/[A-Za-z0-9.+-]+/g) ?? []).filter(
    (k) => k !== "AND" && k !== "OR",
  );
  if (kennungen.length === 0) {
    return false;
  }
  const zulaessig = kennungen.map(
    (k) => erlaubt.has(SPDX_FAMILIE[k]) || (k === "EUPL-1.2" && KERN_UX.test(paket)),
  );
  const nurOder = ausdruck.includes(" OR ") && !ausdruck.includes(" AND ") && !ausdruck.includes("(");
  return nurOder ? zulaessig.some(Boolean) : zulaessig.every(Boolean);
}

/** Lizenzangabe aus package.json: ``license`` oder das alte Feld ``licenses``. */
export function lizenzangabe(paketJson) {
  if (typeof paketJson.license === "string") {
    return paketJson.license;
  }
  if (Array.isArray(paketJson.licenses)) {
    return paketJson.licenses.map((l) => l.type ?? l).join(" OR ");
  }
  return "";
}
