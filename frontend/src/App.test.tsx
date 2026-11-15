import { render, screen, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import { API_KEY, CATALOG, QUESTIONNAIRE, apiError, json, stubApi, untilAborted } from "./test/api";

const PDF = new File(["%PDF-1.4"], "verifica.pdf", { type: "application/pdf" });

function setup(): UserEvent {
  render(<App />);
  return userEvent.setup({ applyAccept: false });
}

async function enterKey(user: UserEvent): Promise<void> {
  await user.type(screen.getByLabelText("Clave de acceso"), API_KEY);
  await user.click(screen.getByRole("button", { name: "Continuar" }));
}

async function chooseFile(user: UserEvent, file: File = PDF): Promise<void> {
  await user.upload(await screen.findByLabelText(/Arrastra tu cuestionario/), file);
}

describe("App", () => {
  it("asks for the key the first time, then extracts and shows the questionnaire", async () => {
    stubApi({
      models: () => json(CATALOG),
      extract: () =>
        json(QUESTIONNAIRE, 200, {
          "X-LLM-Model": "gpt-terra",
          "X-Extraction-Warnings": '["Pages 2 have no text layer"]',
        }),
    });
    const user = setup();

    await enterKey(user);
    await chooseFile(user);
    await user.click(screen.getByRole("radio", { name: /GPT-6.1 Terra/ }));
    await user.click(screen.getByRole("button", { name: "Extraer preguntas" }));

    expect(await screen.findByRole("heading", { name: "Encontramos 2 preguntas" })).toBeDefined();
    expect(window.localStorage.getItem("giunti.apiKey")).toBe(API_KEY);
    const correct = screen.getByText("Respuesta correcta").closest("li");
    expect(correct?.textContent).toContain("Roma");
    expect(screen.getByText("GPT-6.1 Terra")).toBeDefined();
    expect(screen.getByText("1 aviso: revisa este punto")).toBeDefined();
  });

  it("offers the fast and precise modes and sends the chosen one", async () => {
    let sentMode: FormDataEntryValue | null = null;
    stubApi({
      models: () => json(CATALOG),
      extract: (init) => {
        sentMode = init.body instanceof FormData ? init.body.get("mode") : null;
        return json(QUESTIONNAIRE, 200, { "X-LLM-Model": "gemini-flash", "X-LLM-Mode": "precise" });
      },
    });
    const user = setup();

    await enterKey(user);
    await chooseFile(user);
    expect(screen.getByRole("radio", { name: /^Rápido/ })).toHaveProperty("checked", true);
    await user.click(screen.getByRole("radio", { name: /^Preciso/ }));
    await user.click(screen.getByRole("button", { name: "Extraer preguntas" }));

    expect(await screen.findByText("Gemini 3.8 Flash · Preciso")).toBeDefined();
    expect(sentMode).toBe("precise");
  });

  it("hides the mode choice for models that only read in precise mode", async () => {
    stubApi({ models: () => json(CATALOG) });
    const user = setup();

    await enterKey(user);
    expect(await screen.findByRole("group", { name: "Modo de lectura" })).toBeDefined();
    await user.click(screen.getByRole("radio", { name: /GPT-6.1 Terra/ }));

    expect(screen.queryByRole("group", { name: "Modo de lectura" })).toBeNull();
  });

  it("signs in from an invitation link and removes the key from the address bar", async () => {
    window.history.replaceState(null, "", `/#clave=${API_KEY}`);
    const fetchStub = stubApi({ models: () => json(CATALOG) });
    setup();

    expect(await screen.findByText("Clave de acceso guardada en este navegador")).toBeDefined();
    expect(window.location.hash).toBe("");
    expect(window.localStorage.getItem("giunti.apiKey")).toBe(API_KEY);
    expect(fetchStub.mock.calls[0]?.[1]).toMatchObject({ headers: { "X-API-Key": API_KEY } });
  });

  it("uses a remembered key without asking for it", async () => {
    window.localStorage.setItem("giunti.apiKey", API_KEY);
    const fetchStub = stubApi({ models: () => json(CATALOG) });
    setup();

    expect(await screen.findByText("Clave de acceso guardada en este navegador")).toBeDefined();
    expect(fetchStub).toHaveBeenCalledOnce();
  });

  it("forgets a remembered key that is no longer valid and asks for a new one", async () => {
    window.localStorage.setItem("giunti.apiKey", "gk_acme_revoked");
    stubApi({ models: () => apiError("UNAUTHENTICATED", 401) });
    setup();

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      expect.stringContaining("La clave de acceso no es válida") as string,
    );
    expect(window.localStorage.getItem("giunti.apiKey")).toBeNull();
    expect(screen.getByLabelText("Clave de acceso")).toBeDefined();
  });

  it("explains a server without models and lets the user retry", async () => {
    const models = vi
      .fn()
      .mockReturnValueOnce(apiError("NO_MODELS_AVAILABLE", 503))
      .mockReturnValueOnce(json(CATALOG));
    stubApi({ models });
    const user = setup();

    await enterKey(user);
    expect(await screen.findByText("El servicio no tiene modelos configurados")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByLabelText(/Arrastra tu cuestionario/)).toBeDefined();
  });

  it("rejects an unsupported file before uploading anything", async () => {
    const fetchStub = stubApi({ models: () => json(CATALOG) });
    const user = setup();

    await enterKey(user);
    await chooseFile(user, new File(["x"], "notas.doc"));

    expect(screen.getByRole("alert").textContent).toContain("Formato no admitido");
    expect(screen.getByRole("button", { name: "Extraer preguntas" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(fetchStub).toHaveBeenCalledOnce();
  });

  it("goes back to the form, keeping the file, when the user cancels the wait", async () => {
    stubApi({ models: () => json(CATALOG), extract: untilAborted });
    const user = setup();
    await enterKey(user);
    await chooseFile(user);
    await user.click(screen.getByRole("button", { name: "Extraer preguntas" }));

    await user.click(await screen.findByRole("button", { name: "Cancelar" }));

    expect(screen.getByText("verifica.pdf")).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: "Extraer preguntas" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("explains a server error in Spanish, with what to do and the request code", async () => {
    stubApi({
      models: () => json(CATALOG),
      extract: () => apiError("RATE_LIMITED", 429, { "Retry-After": "120" }),
    });
    const user = setup();
    await enterKey(user);
    await chooseFile(user);

    await user.click(screen.getByRole("button", { name: "Extraer preguntas" }));

    const notice = await screen.findByRole("heading", { name: "Alcanzaste el límite de uso" });
    const section = notice.closest("section");
    if (section === null) {
      throw new Error("The error notice is not inside a section");
    }
    const details = within(section);
    expect(details.getByText("Podrás intentarlo de nuevo en 2 minutos.")).toBeDefined();
    expect(details.getByText("Código de solicitud: req-1")).toBeDefined();
  });

  it("keeps working when the browser blocks localStorage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("Blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Blocked", "SecurityError");
    });
    stubApi({ models: () => json(CATALOG) });
    const user = setup();

    await enterKey(user);

    expect(await screen.findByLabelText(/Arrastra tu cuestionario/)).toBeDefined();
  });
});
