// SPDX-License-Identifier: AGPL-3.0-or-later
// Seitenwahl über den Hash der Adresse: #/ ist die Aktenliste, #/akten/<id> eine Akte,
// #/lizenzen die Lizenzen (auch vor der Einrichtung erreichbar).
import { useCallback, useEffect, useState } from "react";

import { api } from "./kern/api/client";
import { Einrichtung } from "./kern/Einrichtung";
import { Lizenzen } from "./kern/Lizenzen";
import { Rahmen } from "./kern/Rahmen";
import { Akte } from "./module/verbindlichkeiten/Akte";
import { Aktenliste } from "./module/verbindlichkeiten/Aktenliste";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const neu = () => setHash(window.location.hash);
    window.addEventListener("hashchange", neu);
    return () => window.removeEventListener("hashchange", neu);
  }, []);
  return hash;
}

export function App() {
  const hash = useHash();
  const [eingerichtet, setEingerichtet] = useState<boolean | null>(null);

  const pruefe = useCallback(() => {
    void api.GET("/api/haushalt").then(({ response }) => setEingerichtet(response.ok));
  }, []);
  useEffect(pruefe, [pruefe]);

  const akte = /^#\/akten\/([0-9a-f-]{36})$/.exec(hash);
  let seite = <Aktenliste />;
  if (hash === "#/lizenzen") {
    seite = <Lizenzen />;
  } else if (eingerichtet === null) {
    seite = <p className="kern-body">Lädt …</p>;
  } else if (!eingerichtet) {
    seite = <Einrichtung fertig={pruefe} />;
  } else if (akte?.[1]) {
    seite = <Akte id={akte[1]} />;
  }
  return <Rahmen>{seite}</Rahmen>;
}
