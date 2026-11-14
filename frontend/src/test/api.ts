/** Fake API for tests: a fetch stub that answers by route, and response builders. */
import { vi } from "vitest";

import type { ModelCatalog, Questionnaire } from "../types/questionnaire";

export const API_KEY = "gk_acme_secret";

export const CATALOG: ModelCatalog = {
  default_model: "gemini-flash",
  providers: [
    {
      id: "gemini",
      label: "Google Gemini",
      description: "Proveedor principal.",
      models: [
        {
          id: "gemini-flash",
          label: "Gemini 3.8 Flash",
          description: "Rápido.",
          vision: true,
          free: false,
          is_default: true,
        },
      ],
    },
    {
      id: "openai",
      label: "OpenAI (ChatGPT)",
      description: "OpenAI.",
      models: [
        {
          id: "gpt-terra",
          label: "GPT-6.1 Terra",
          description: "Visual.",
          vision: true,
          free: false,
          is_default: false,
        },
      ],
    },
  ],
};

export const QUESTIONNAIRE: Questionnaire = {
  titulo: "Verifica di geografia",
  idioma: "it",
  total_items: 2,
  items: [
    {
      numero: 1,
      enunciado: "Quale è la capitale d'Italia?",
      tipo: "seleccion_multiple",
      alternativas: [
        { valor: "A", texto: "Milano" },
        { valor: "B", texto: "Roma" },
      ],
      premisas: [],
      respuesta_correcta: ["B"],
    },
    {
      numero: 2,
      enunciado: "Descrivi il fiume Po.",
      tipo: "desarrollo",
      alternativas: [],
      premisas: [],
      respuesta_correcta: null,
    },
  ],
};

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export function apiError(
  code: string,
  status: number,
  headers: Record<string, string> = {},
): Response {
  return json({ error: { code, message: `${code} detail`, request_id: "req-1" } }, status, headers);
}

export type Route = (init: RequestInit) => Response | Promise<Response>;

/** Replaces fetch; each route answers `GET /api/v1/models` or `POST /api/v1/questionnaires`. */
export function stubApi(routes: { models?: Route; extract?: Route }): ReturnType<typeof vi.fn> {
  const fetchStub = vi.fn((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = input instanceof Request ? input.url : String(input);
    const route = url.endsWith("/api/v1/models") ? routes.models : routes.extract;
    if (route === undefined) {
      return Promise.reject(new TypeError(`No fake route for ${url}`));
    }
    return Promise.resolve(route(init));
  });
  vi.stubGlobal("fetch", fetchStub);
  return fetchStub;
}

/** A response that only settles when the request is aborted, like a slow extraction. */
export function untilAborted(init: RequestInit): Promise<Response> {
  return new Promise((_, reject) => {
    init.signal?.addEventListener("abort", () => {
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}
