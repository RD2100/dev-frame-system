import { createRoot } from "react-dom/client";

import { Button } from "@tutti-os/ui-system";
import "@tutti-os/ui-system/styles.css";
import "./style.css";

export function FixtureApp() {
  return (
    <main className="fixture-shell">
      <section className="fixture-panel" aria-labelledby="fixture-title">
        <p className="fixture-kicker">External Vite fixture</p>
        <h1 id="fixture-title">Tutti UI System</h1>
        <p className="fixture-copy">
          This app consumes the stable package entrypoints and renders a real UI
          system button.
        </p>
        <Button type="button">Rendered with Button</Button>
      </section>
    </main>
  );
}

const rootElement = document.getElementById("root");

if (rootElement === null) {
  throw new Error("Fixture root element was not found");
}

createRoot(rootElement).render(<FixtureApp />);
