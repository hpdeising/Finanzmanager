// SPDX-License-Identifier: AGPL-3.0-or-later
// Prüft die Lizenzen aller installierten npm-Pakete gegen CLAUDE.md und schreibt die
// Lizenzhinweise der Pakete, die im Bundle landen (Fachkonzept 11.3), beide erzeugt und nicht
// eingecheckt:
// - src/kern/lizenzen/drittanbieter.json für die Seite „Lizenzen“,
// - public/THIRD-PARTY-LICENSES, die Vite unverändert ins Bundle kopiert.
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { erlaubtNachSpdx, erlaubteFamilien, lizenzangabe } from "./lizenzpruefung.mjs";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
const ZIEL = join(FRONTEND, "src", "kern", "lizenzen", "drittanbieter.json");
const TEXTDATEI = join(FRONTEND, "public", "THIRD-PARTY-LICENSES");
const LIZENZDATEI = /^(licen[cs]e|copying|notice)(\.|$)/i;

const erlaubt = erlaubteFamilien(readFileSync(join(FRONTEND, "..", "CLAUDE.md"), "utf8"));
const lock = JSON.parse(readFileSync(join(FRONTEND, "package-lock.json"), "utf8"));

const verstoesse = [];
const hinweise = [];
for (const [pfad, eintrag] of Object.entries(lock.packages)) {
  // Geprüft wird, wovon das Projekt abhängt:
  // - Nicht installierte Pakete fehlen, etwa Plattformpakete anderer Systeme.
  // - Optionale Peer-Abhängigkeiten (peer und optional, etwa jsdom bei vitest) verlangt das
  //   Projekt nicht; manche npm-Versionen installieren sie trotzdem. Braucht das Projekt eins
  //   davon, steht es in package.json und ist dann kein optionaler Peer mehr.
  if (
    pfad === "" ||
    (eintrag.peer && eintrag.optional) ||
    !existsSync(join(FRONTEND, pfad, "package.json"))
  ) {
    continue;
  }
  const paket = JSON.parse(readFileSync(join(FRONTEND, pfad, "package.json"), "utf8"));
  const lizenz = lizenzangabe(paket) || "keine Angabe";
  if (!erlaubtNachSpdx(lizenz, erlaubt, paket.name)) {
    verstoesse.push(`${paket.name}@${paket.version}: ${lizenz}`);
  }
  if (!eintrag.dev) {
    const datei = readdirSync(join(FRONTEND, pfad)).find((name) => LIZENZDATEI.test(name));
    hinweise.push({
      name: paket.name,
      version: paket.version,
      lizenz,
      text: datei ? readFileSync(join(FRONTEND, pfad, datei), "utf8") : "",
    });
  }
}

// Fira Sans liegt in @kern-ux/native, steht aber unter einer eigenen Lizenz (OFL-1.1); das Paket
// liefert ihren Text nicht mit (lizenzen/fira-sans/HERKUNFT.md).
const kern = JSON.parse(
  readFileSync(join(FRONTEND, "node_modules", "@kern-ux", "native", "package.json"), "utf8"),
);
if (!erlaubtNachSpdx("OFL-1.1", erlaubt)) {
  verstoesse.push("Fira Sans (in @kern-ux/native): OFL-1.1");
}
hinweise.push({
  name: "Fira Sans (Schrift in @kern-ux/native)",
  version: `aus @kern-ux/native ${kern.version}`,
  lizenz: "OFL-1.1",
  text: readFileSync(join(FRONTEND, "lizenzen", "fira-sans", "OFL.txt"), "utf8"),
});
if (verstoesse.length > 0) {
  process.stderr.write(`Lizenzen nicht in CLAUDE.md erlaubt:\n${verstoesse.join("\n")}\n`);
  process.exit(1);
}
hinweise.sort((a, b) => a.name.localeCompare(b.name));
mkdirSync(dirname(ZIEL), { recursive: true });
writeFileSync(ZIEL, `${JSON.stringify(hinweise, null, 2)}\n`);
mkdirSync(dirname(TEXTDATEI), { recursive: true });
writeFileSync(
  TEXTDATEI,
  [
    "Lizenzhinweise der npm-Pakete im Bundle der Oberfläche des Finanzmanagers.",
    "Automatisch erzeugt beim Build (frontend/scripts/lizenzen.mjs); nicht von Hand ändern.",
    ...hinweise.map(
      (h) => `\n${"=".repeat(78)}\n${h.name} ${h.version} (${h.lizenz})\n${"=".repeat(78)}\n\n${h.text || "Kein Lizenztext im Paket enthalten."}`,
    ),
  ].join("\n") + "\n",
);
process.stdout.write(`Lizenzen geprüft; ${hinweise.length} Pakete im Bundle.\n`);
