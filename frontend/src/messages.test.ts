import { describe, expect, it } from "vitest";

import { BACKEND_ERROR_CODES, errorText, formatWait, waitingStage } from "./messages";

describe("errorText", () => {
  it.each(BACKEND_ERROR_CODES.filter((code) => code !== "NOT_FOUND"))(
    "has a specific Spanish message for %s",
    (code) => {
      expect(errorText(code)).not.toEqual(errorText("SOMETHING_NEW"));
    },
  );

  it("falls back to a generic message for unknown codes", () => {
    expect(errorText("SOMETHING_NEW").title).toBe("Ocurrió un error inesperado");
  });

  it("tells how long to wait when the limit was reached", () => {
    expect(errorText("RATE_LIMITED", 3600).hint).toBe("Podrás intentarlo de nuevo en 1 hora.");
  });
});

describe("formatWait", () => {
  it.each([
    [1, "1 segundo"],
    [59, "59 segundos"],
    [60, "1 minuto"],
    [61, "2 minutos"],
    [3600, "1 hora"],
    [3601, "2 horas"],
  ])("formats %i seconds as %s", (seconds, text) => {
    expect(formatWait(seconds)).toBe(text);
  });
});

describe("waitingStage", () => {
  it("changes the message as time passes, without going back", () => {
    const stages = [0, 5, 6, 30, 60, 600].map(waitingStage);

    expect(stages[0]).toBe(stages[1]);
    expect(stages[2]).not.toBe(stages[1]);
    expect(new Set(stages).size).toBe(5);
  });
});
