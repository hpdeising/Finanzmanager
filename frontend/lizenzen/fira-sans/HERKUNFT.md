<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Fira Sans: Herkunft des Lizenztexts

`@kern-ux/native` liefert die Schrift Fira Sans (Version 4.106) ohne ihren Lizenztext mit.
Die SIL Open Font License 1.1 verlangt, dass der Text mit der Schrift weitergegeben wird.

`OFL.txt` ist unverändert die Datei `LICENSE` aus dem Ursprungsprojekt
<https://github.com/mozilla/Fira>, Commit `fd8c8c0a3d353cd99e8ca1662942d165e6961407`. Ihr
Copyright-Vermerk stimmt mit dem der ausgelieferten Schriftdateien überein (Name-Tabelle,
Eintrag 0: „Digitized data copyright © 2012-2015, The Mozilla Foundation and Telefonica S.A.“;
Eintrag 13: „Licensed under the Open Font License, version 1.1 or later“).

`scripts/kern.mjs` legt `OFL.txt` neben die Schriftdateien ins Bundle, `scripts/lizenzen.mjs`
nimmt den Text in die Seite „Lizenzen“ und in `THIRD-PARTY-LICENSES` auf.
