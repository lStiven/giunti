/**
 * API client: `GET /api/v1/models` and `POST /api/v1/questionnaires`.
 *
 * Every failure becomes an `ApiRequestError` with a stable code: the backend's codes, plus
 * NETWORK_ERROR (no response), INVALID_RESPONSE (unexpected body) and ABORTED (cancelled).
 */
import type { ExtractionResult, ModelCatalog, RunInfo } from "../types/questionnaire";
import { apiErrorBody, isModelCatalog, isQuestionnaire, parseWarnings } from "./guards";

export const API_URL: string = import.meta.env.VITE_API_URL ?? "";
export const API_KEY_HEADER = "X-API-Key";

export class ApiRequestError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number | null = null,
    readonly requestId: string | null = null,
    readonly retryAfterSeconds: number | null = null,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export async function fetchModels(apiKey: string, signal?: AbortSignal): Promise<ModelCatalog> {
  const response = await send(`${API_URL}/api/v1/models`, {
    headers: { [API_KEY_HEADER]: apiKey },
    ...(signal ? { signal } : {}),
  });
  const body = await readJson(response);
  if (!isModelCatalog(body)) {
    throw invalidResponse(response);
  }
  return body;
}

export interface ExtractionRequest {
  apiKey: string;
  file: File;
  model: string | null;
  signal?: AbortSignal;
}

export async function extractQuestionnaire(request: ExtractionRequest): Promise<ExtractionResult> {
  const form = new FormData();
  form.append("file", request.file);
  if (request.model !== null) {
    form.append("model", request.model);
  }
  const response = await send(`${API_URL}/api/v1/questionnaires`, {
    method: "POST",
    headers: { [API_KEY_HEADER]: request.apiKey },
    body: form,
    ...(request.signal ? { signal: request.signal } : {}),
  });
  const body = await readJson(response);
  if (!isQuestionnaire(body)) {
    throw invalidResponse(response);
  }
  return { questionnaire: body, run: runInfo(response.headers) };
}

/** Fetch that turns every failure (network, HTTP status) into an `ApiRequestError`. */
export async function send(url: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiRequestError("ABORTED", "The request was cancelled.");
    }
    throw new ApiRequestError("NETWORK_ERROR", "The server could not be reached.");
  }
  if (!response.ok) {
    throw await errorFrom(response);
  }
  return response;
}

async function errorFrom(response: Response): Promise<ApiRequestError> {
  const body = apiErrorBody(await readJson(response).catch(() => null));
  const retryAfter = Number(response.headers.get("Retry-After"));
  return new ApiRequestError(
    body?.code ?? `HTTP_${String(response.status)}`,
    body?.message ?? response.statusText,
    response.status,
    body?.request_id ?? response.headers.get("X-Request-ID"),
    Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
  );
}

export async function readJson(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    throw invalidResponse(response);
  }
}

export function invalidResponse(response: Response): ApiRequestError {
  return new ApiRequestError(
    "INVALID_RESPONSE",
    "The server sent an unexpected response.",
    response.status,
    response.headers.get("X-Request-ID"),
  );
}

function runInfo(headers: Headers): RunInfo {
  const count = (name: string): number => Number(headers.get(name) ?? 0) || 0;
  const remaining = headers.get("X-RateLimit-Remaining-Day");
  return {
    model: headers.get("X-LLM-Model") ?? "",
    durationMs: count("X-LLM-Duration-Ms"),
    inputTokens: count("X-LLM-Input-Tokens"),
    outputTokens: count("X-LLM-Output-Tokens"),
    parts: count("X-Extraction-Parts"),
    warnings: parseWarnings(headers.get("X-Extraction-Warnings")),
    dailyRemaining: remaining === null ? null : Number(remaining),
  };
}
