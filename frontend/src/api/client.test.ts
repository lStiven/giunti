import { describe, expect, it, vi } from "vitest";

import { API_KEY, CATALOG, QUESTIONNAIRE, apiError, json, stubApi } from "../test/api";
import { ApiRequestError, extractQuestionnaire, fetchModels } from "./client";

const FILE = new File(["%PDF-1.4"], "test.pdf", { type: "application/pdf" });

async function failure(promise: Promise<unknown>): Promise<ApiRequestError> {
  const error: unknown = await promise.then(
    () => null,
    (reason: unknown) => reason,
  );
  expect(error).toBeInstanceOf(ApiRequestError);
  return error as ApiRequestError;
}

describe("extractQuestionnaire", () => {
  it("returns the questionnaire and the run details from the headers", async () => {
    stubApi({
      extract: () =>
        json(QUESTIONNAIRE, 200, {
          "X-LLM-Model": "gemini-flash",
          "X-LLM-Duration-Ms": "1500",
          "X-Extraction-Parts": "2",
          "X-Extraction-Warnings": '["Pages 3 have no text layer"]',
          "X-RateLimit-Remaining-Day": "7",
        }),
    });

    const result = await extractQuestionnaire({ apiKey: API_KEY, file: FILE, model: null });

    expect(result.questionnaire).toEqual(QUESTIONNAIRE);
    expect(result.run).toMatchObject({
      model: "gemini-flash",
      durationMs: 1500,
      parts: 2,
      warnings: ["Pages 3 have no text layer"],
      dailyRemaining: 7,
    });
  });

  it("sends the key and the chosen model, and omits the model when none is chosen", async () => {
    const fetchStub = stubApi({ extract: () => json(QUESTIONNAIRE) });

    await extractQuestionnaire({ apiKey: API_KEY, file: FILE, model: "gpt-terra" });
    await extractQuestionnaire({ apiKey: API_KEY, file: FILE, model: null });

    const [withModel, withoutModel] = fetchStub.mock.calls.map(
      (call) => (call as [string, RequestInit])[1],
    );
    expect(withModel?.headers).toEqual({ "X-API-Key": API_KEY });
    expect((withModel?.body as FormData).get("model")).toBe("gpt-terra");
    expect((withoutModel?.body as FormData).has("model")).toBe(false);
  });

  it("treats a malformed warnings header as no warnings", async () => {
    stubApi({ extract: () => json(QUESTIONNAIRE, 200, { "X-Extraction-Warnings": "not json" }) });

    const result = await extractQuestionnaire({ apiKey: API_KEY, file: FILE, model: null });

    expect(result.run.warnings).toEqual([]);
    expect(result.run.dailyRemaining).toBeNull();
  });

  it("turns the backend error body into a coded error with the wait time", async () => {
    stubApi({ extract: () => apiError("RATE_LIMITED", 429, { "Retry-After": "120" }) });

    const error = await failure(extractQuestionnaire({ apiKey: API_KEY, file: FILE, model: null }));

    expect(error.code).toBe("RATE_LIMITED");
    expect(error.status).toBe(429);
    expect(error.requestId).toBe("req-1");
    expect(error.retryAfterSeconds).toBe(120);
  });

  it("handles error pages that are not JSON, such as a proxy timeout", async () => {
    stubApi({
      extract: () =>
        new Response("<html>Bad gateway</html>", {
          status: 502,
          headers: { "X-Request-ID": "proxy-1" },
        }),
    });

    const error = await failure(extractQuestionnaire({ apiKey: API_KEY, file: FILE, model: null }));

    expect(error.code).toBe("HTTP_502");
    expect(error.requestId).toBe("proxy-1");
  });

  it("rejects a successful response with an unexpected shape", async () => {
    stubApi({ extract: () => json({ items: "not a list" }) });

    const error = await failure(extractQuestionnaire({ apiKey: API_KEY, file: FILE, model: null }));

    expect(error.code).toBe("INVALID_RESPONSE");
  });

  it("reports an unreachable server as a network error", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));

    const error = await failure(extractQuestionnaire({ apiKey: API_KEY, file: FILE, model: null }));

    expect(error.code).toBe("NETWORK_ERROR");
  });

  it("reports a cancelled request as aborted", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new DOMException("Aborted", "AbortError")));

    const error = await failure(extractQuestionnaire({ apiKey: API_KEY, file: FILE, model: null }));

    expect(error.code).toBe("ABORTED");
  });
});

describe("fetchModels", () => {
  it("returns the catalog", async () => {
    stubApi({ models: () => json(CATALOG) });

    expect(await fetchModels(API_KEY)).toEqual(CATALOG);
  });
});
