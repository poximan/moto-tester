import "@servicoop/frontend-foundation/tokens.css";
import "@servicoop/frontend-foundation/base.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("Falta el elemento obligatorio #root");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
