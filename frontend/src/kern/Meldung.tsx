// SPDX-License-Identifier: AGPL-3.0-or-later
// Hinweise und Fehler als KERN-Alert; die Art steht immer auch im Text, nie nur in der Farbe.
import type { ReactNode } from "react";

type Art = "info" | "success" | "warning" | "danger";

const TITEL: Record<Art, string> = {
  info: "Hinweis",
  success: "Erledigt",
  warning: "Achtung",
  danger: "Fehler",
};

export function Meldung({ art, children }: { art: Art; children: ReactNode }) {
  return (
    <div className={`kern-alert kern-alert--${art}`} role={art === "danger" ? "alert" : "status"}>
      <div className="kern-alert__header">
        <span className="kern-title">{TITEL[art]}</span>
      </div>
      <div className="kern-alert__body">
        <p className="kern-body">{children}</p>
      </div>
    </div>
  );
}
