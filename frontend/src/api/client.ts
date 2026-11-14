/**
 * API client: `GET /api/v1/models` and `POST /api/v1/questionnaires`.
 *
 * Every failure becomes an `ApiRequestError` with a stable code: the backend's codes, plus
 * NETWORK_ERROR (no response), INVALID_RESPONSE (unexpected body), ABORTED (cancelled),
 * TIMED_OUT (the connection dropped after a long wait, usually a proxy limit) and HTTP_<status>
 * (an error page from something in front of the API).
 */
import type { ExtractionResult, ModelCatalog, RunInfo } from "../types/questionnaire";
import {
  apiErrorBody,
  isModelCatalog,
  isQuestionnaire,
  parseNotices,
  type ErrorDetails,
} from "./guards";

export const API_URL: string = import.meta.env.VITE_API_URL ?? "";
export const API_KEY_HEADER = "X-API-Key";

/** A wait this long before the connection drops means a timeout, not a network problem. */
export const LONG_REQUEST_MS = 60_000;

const GATEWAY_STATUSES = new Set([502, 503, 504]);

export interface ErrorExtra {
  reason?: string | null;
  details?: ErrorDetails;
  /** How long the request ran before failing. */
  elapsedMs?: number | null;
}

export class ApiRequestError extends Error {
  readonly reason: string | null;
  readonly details: ErrorDetails;
  readonly elapsedMs: number | null;

  constructor(
    readonly code: string,
    message: string,
    readonly status: number | null = null,
    readonly requestId: string | null = null,
    readonly retryAfterSeconds: number | null = null,
    extra: ErrorExtra = {},
  ) {
    super(message);
    this.name = "ApiRequestError";
    this.reason = extra.reason ?? null;
    this.details = extra.details ?? {};
    this.elapsedMs = extra.elapsedMs ?? null;
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
  const started = Date.now();
  let response: Response;
  try {
    response = await send(`${API_URL}/api/v1/questionnaires`, {
      method: "POST",
      headers: { [API_KEY_HEADER]: request.apiKey },
      body: form,
      ...(request.signal ? { signal: request.signal } : {}),
    });
  } catch (error) {
    throw explainLongFailure(error, Date.now() - started);
  }
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
    { reason: body?.reason ?? null, details: body?.details ?? {} },
  );
}

/**
 * A dropped connection or a gateway error page after a long wait is almost always a proxy
 * cutting a slow extraction, not a problem with the user's network.
 */
export function explainLongFailure(error: unknown, elapsedMs: number): unknown {
  if (!(error instanceof ApiRequestError)) {
    return error;
  }
  const fromGateway = error.code.startsWith("HTTP_") && GATEWAY_STATUSES.has(error.status ?? 0);
  if ((error.code === "NETWORK_ERROR" || fromGateway) && elapsedMs >= LONG_REQUEST_MS) {
    return new ApiRequestError(
      "TIMED_OUT",
      "The connection was closed before the extraction finished.",
      error.status,
      error.requestId,
      null,
      { elapsedMs },
    );
  }
  return error;
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
  const notices = parseNotices(headers.get("X-Extraction-Warnings"));
  return {
    model: headers.get("X-LLM-Model") ?? "",
    durationMs: count("X-LLM-Duration-Ms"),
    inputTokens: count("X-LLM-Input-Tokens"),
    outputTokens: count("X-LLM-Output-Tokens"),
    parts: count("X-Extraction-Parts"),
    warnings: notices.map((notice) => notice.message),
    notices,
    dailyRemaining: remaining === null ? null : Number(remaining),
  };
}
