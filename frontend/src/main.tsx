import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles.css";

// Loaded only on /admin, so clients never download the admin panel.
const AdminApp = lazy(() => import("./admin/AdminApp"));

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("Root element #root not found");
}

const isAdminPage = window.location.pathname.replace(/\/+$/, "") === "/admin";

createRoot(rootElement).render(
  <StrictMode>
    {isAdminPage ? (
      <Suspense fallback={null}>
        <AdminApp />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
);
