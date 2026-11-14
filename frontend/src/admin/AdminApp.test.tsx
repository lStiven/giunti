import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { apiError, json } from "../test/api";
import type { ClientView, IssuedKey } from "./api";
import AdminApp from "./AdminApp";

const ADMIN_KEY = "gk_admin_secret";

function client(overrides: Partial<ClientView> = {}): ClientView {
  return {
    id: "colegio",
    name: "Colegio San José",
    active: true,
    is_admin: false,
    per_minute_limit: 10,
    daily_limit: 100,
    used_today: 3,
    created_at: "2026-11-14T10:00:00Z",
    key_created_at: "2026-11-14T10:00:00Z",
    last_used_at: null,
    ...overrides,
  };
}

const ADMIN = client({ id: "admin", name: "Administración", is_admin: true, used_today: 0 });

function issued(view: ClientView): IssuedKey {
  return {
    client: view,
    api_key: `gk_${view.id}_new`,
    invite_url: `https://app.example/#clave=gk_${view.id}_new`,
  };
}

type Handler = (method: string, path: string, body: unknown) => Response;

function stubAdminApi(handler: Handler): ReturnType<typeof vi.fn> {
  const fetchStub = vi.fn((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = input instanceof Request ? input.url : input.toString();
    const path = url.replace(/^.*\/api\/v1\/admin/, "");
    const body: unknown = typeof init.body === "string" ? JSON.parse(init.body) : null;
    return Promise.resolve(handler(init.method ?? "GET", path, body));
  });
  vi.stubGlobal("fetch", fetchStub);
  return fetchStub;
}

function openWithInvitation(): void {
  window.history.replaceState(null, "", `/admin#clave=${ADMIN_KEY}`);
}

describe("AdminApp", () => {
  it("signs in from the admin link, lists clients and shows a new invitation once", async () => {
    openWithInvitation();
    stubAdminApi((method, _path, body) => {
      if (method === "POST") {
        const name = (body as { name: string }).name;
        return json(issued(client({ id: "liceo", name, used_today: 0 })), 201);
      }
      return json([client(), ADMIN]);
    });
    const user = userEvent.setup();
    render(<AdminApp />);

    expect(await screen.findByText("Colegio San José")).toBeDefined();
    expect(window.location.hash).toBe("");
    expect(window.localStorage.getItem("giunti.adminKey")).toBe(ADMIN_KEY);
    expect(screen.getByText("3 de 100")).toBeDefined();

    await user.type(screen.getByLabelText("Nombre del cliente"), "Liceo Nº 5");
    await user.click(screen.getByRole("button", { name: "Crear invitación" }));

    expect(
      await screen.findByRole("heading", { name: "Invitación lista para Liceo Nº 5" }),
    ).toBeDefined();
    expect(screen.getByText("https://app.example/#clave=gk_liceo_new")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Clientes (3)" })).toBeDefined();

    await user.click(screen.getByRole("button", { name: "Listo" }));
    expect(screen.queryByText("https://app.example/#clave=gk_liceo_new")).toBeNull();
    expect(screen.getByLabelText("Nombre del cliente")).toBeDefined();
  });

  it("rejects a key without administrator rights and forgets it", async () => {
    openWithInvitation();
    stubAdminApi(() => apiError("FORBIDDEN", 403));
    render(<AdminApp />);

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Esta clave no es de administrador o está desactivada.",
    );
    expect(window.localStorage.getItem("giunti.adminKey")).toBeNull();
    expect(screen.getByLabelText("Clave de administrador")).toBeDefined();
  });

  it("deactivates a client and keeps administrators out of the panel's actions", async () => {
    openWithInvitation();
    stubAdminApi((method) =>
      method === "PATCH" ? json(client({ active: false })) : json([client(), ADMIN]),
    );
    const user = userEvent.setup();
    render(<AdminApp />);

    const card = (await screen.findByText("Colegio San José")).closest("li");
    if (card === null) {
      throw new Error("Client card not found");
    }
    await user.click(within(card).getByRole("button", { name: "Desactivar" }));

    expect(await within(card).findByText("Desactivado")).toBeDefined();
    expect(within(card).getByRole("button", { name: "Activar" })).toBeDefined();
    expect(screen.getByText("Los administradores se gestionan desde la terminal.")).toBeDefined();
  });

  it("asks for confirmation before replacing a client's invitation", async () => {
    openWithInvitation();
    const fetchStub = stubAdminApi((method) =>
      method === "POST" ? json(issued(client())) : json([client()]),
    );
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValue(true);
    const user = userEvent.setup();
    render(<AdminApp />);
    const button = await screen.findByRole("button", { name: "Nueva invitación" });

    await user.click(button);
    expect(fetchStub).toHaveBeenCalledOnce();

    await user.click(button);
    expect(
      await screen.findByRole("heading", { name: "Invitación lista para Colegio San José" }),
    ).toBeDefined();
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it("deletes a client after confirmation and removes it from the list", async () => {
    openWithInvitation();
    const other = client({ id: "liceo", name: "Liceo Nº 5" });
    const fetchStub = stubAdminApi((method) =>
      method === "DELETE" ? new Response(null, { status: 204 }) : json([client(), other]),
    );
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValue(true);
    const user = userEvent.setup();
    render(<AdminApp />);
    const card = (await screen.findByText("Colegio San José")).closest("li");
    if (card === null) {
      throw new Error("client card not found");
    }
    const button = within(card).getByRole("button", { name: "Eliminar" });

    await user.click(button);
    expect(fetchStub).toHaveBeenCalledOnce();

    await user.click(button);
    expect(await screen.findByRole("heading", { name: "Clientes (1)" })).toBeDefined();
    expect(screen.queryByText("Colegio San José")).toBeNull();
    expect(screen.getByText("Liceo Nº 5")).toBeDefined();
    expect(fetchStub).toHaveBeenLastCalledWith(
      expect.stringMatching(/\/api\/v1\/admin\/clients\/colegio$/),
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(confirm).toHaveBeenCalledTimes(2);
  });
});
