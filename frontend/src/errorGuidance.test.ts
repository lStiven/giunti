import { describe, expect, it } from "vitest";

import { ApiRequestError, explainLongFailure, extractQuestionnaire } from "./api/client";
import { parseNotices } from "./api/guards";
import { errorGuidance, formatNumbers, noticeText, type ErrorFacts } from "./messages";
import { QUESTIONNAIRE, json, stubApi } from "./test/api";

function facts(overrides: Partial<ErrorFacts>): ErrorFacts {
  return {
    code: "LLM_UNAVAILABLE",
    reason: null,
    details: {},
    retryAfterSeconds: null,
    elapsedMs: null,
    ...overrides,
  };
}

describe("errorGuidance", () => {
  it("tells how long a model with exhausted quota is paused and offers another model", () => {
    const guidance = errorGuidance(
      facts({
        reason: "quota_exhausted",
        details: { model: "gemini-flash" },
        retryAfterSeconds: 900,
      }),
    );

    expect(guidance.title).toBe("Se agotó la cuota del modelo");
    expect(guidance.hint).toContain("«gemini-flash»");
    expect(guidance.hint).toContain("15 minutos");
    expect(guidance.actions[0]).toBe("changeModel");
  });

  it("gives the page count and the limit of a document that is too long", () => {
    const guidance = errorGuidance(
      facts({
        code: "FILE_TOO_LARGE",
        reason: "too_many_pages",
        details: { limit: 60, actual: 63 },
      }),
    );

    expect(guidance.hint).toContain("Tiene 63 páginas y el máximo es 60");
    expect(guidance.actions).toEqual(["changeFile"]);
  });

  it("asks to wait out the per-minute limit", () => {
    const guidance = errorGuidance(
      facts({
        code: "RATE_LIMITED",
        reason: "per_minute_limit",
        details: { limit: 10 },
        retryAfterSeconds: 42,
      }),
    );

    expect(guidance.hint).toBe(
      "Tu clave permite 10 extracciones por minuto. Podrás intentarlo de nuevo en 42 segundos.",
    );
    expect(guidance.actions).toEqual(["wait"]);
  });

  it("explains a connection that dropped after a long wait as a timeout", () => {
    const guidance = errorGuidance(facts({ code: "TIMED_OUT", elapsedMs: 312_000 }));

    expect(guidance.title).toBe("El procesamiento tardó demasiado");
    expect(guidance.hint).toContain("5 min 12 s");
  });

  it("treats a gateway error page as a server that is not responding", () => {
    expect(errorGuidance(facts({ code: "HTTP_502" })).title).toBe(
      "El servidor no está respondiendo",
    );
  });

  it("falls back to the code's text when the reason is unknown", () => {
    const guidance = errorGuidance(facts({ code: "NO_ITEMS", reason: "something_new" }));

    expect(guidance.title).toBe("No encontramos preguntas");
  });
});

describe("explainLongFailure", () => {
  const dropped = new ApiRequestError("NETWORK_ERROR", "The server could not be reached.");

  it("turns a dropped connection after a long wait into TIMED_OUT", () => {
    const error = explainLongFailure(dropped, 400_000);

    expect(error).toBeInstanceOf(ApiRequestError);
    expect((error as ApiRequestError).code).toBe("TIMED_OUT");
    expect((error as ApiRequestError).elapsedMs).toBe(400_000);
  });

  it("keeps a quick network failure as a network problem", () => {
    expect(explainLongFailure(dropped, 2_000)).toBe(dropped);
  });
});

describe("error body and warnings", () => {
  it("reads the reason and details of an API error", async () => {
    stubApi({
      extract: () =>
        json(
          {
            error: {
              code: "FILE_TOO_LARGE",
              message: "too many pages",
              request_id: "req-9",
              reason: "too_many_pages",
              details: { limit: 60, actual: 63 },
            },
          },
          413,
        ),
    });

    const error = await extractQuestionnaire({
      apiKey: "k",
      file: new File(["x"], "a.pdf"),
      model: null,
    }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiRequestError);
    expect((error as ApiRequestError).reason).toBe("too_many_pages");
    expect((error as ApiRequestError).details).toEqual({ limit: 60, actual: 63 });
  });

  it("parses structured warnings and keeps their messages", async () => {
    const header = JSON.stringify([
      { code: "answer_not_verified", message: "msg", items: [1, 2, 3, 7], pages: [] },
    ]);
    stubApi({ extract: () => json(QUESTIONNAIRE, 200, { "X-Extraction-Warnings": header }) });

    const result = await extractQuestionnaire({
      apiKey: "k",
      file: new File(["x"], "a.pdf"),
      model: null,
    });

    expect(result.run.notices[0]?.items).toEqual([1, 2, 3, 7]);
    expect(result.run.warnings).toEqual(["msg"]);
  });

  it("accepts plain-text warnings from older servers", () => {
    expect(parseNotices('["Pages 2 have no text layer"]')).toEqual([
      { code: "unknown", message: "Pages 2 have no text layer", items: [], pages: [] },
    ]);
  });

  it("writes warnings in Spanish with the item numbers as ranges", () => {
    const text = noticeText({
      code: "answers_not_in_key",
      message: "",
      items: [1, 2, 3, 4, 24, 25],
      pages: [23, 24],
    });

    expect(text).toBe(
      "La clave de respuestas (páginas 23 y 24) no indica la respuesta de las preguntas 1–4, 24 y 25. Revísalas en el documento.",
    );
  });

  it("formats number lists", () => {
    expect(formatNumbers([9, 1, 2, 3, 5])).toBe("1–3, 5 y 9");
    expect(formatNumbers([4])).toBe("4");
    expect(formatNumbers([])).toBe("");
  });
});
