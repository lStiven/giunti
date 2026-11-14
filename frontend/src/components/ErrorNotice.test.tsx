import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "../api/client";
import { ErrorNotice } from "./ErrorNotice";

function renderNotice(error: ApiRequestError): Record<string, ReturnType<typeof vi.fn>> {
  const handlers = {
    onRetry: vi.fn(),
    onStartOver: vi.fn(),
    onChangeModel: vi.fn(),
    onReenterKey: vi.fn(),
  };
  render(<ErrorNotice error={error} {...handlers} />);
  return handlers;
}

describe("ErrorNotice", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps the retry button disabled until the wait is over", () => {
    vi.useFakeTimers();
    const error = new ApiRequestError("RATE_LIMITED", "limit", 429, "req-1", 3, {
      reason: "per_minute_limit",
      details: { limit: 10 },
    });
    renderNotice(error);

    const button = screen.getByRole("button", { name: "Podrás reintentar en 3 segundos" });
    expect(button).toHaveProperty("disabled", true);

    act(() => {
      vi.advanceTimersByTime(3_000);
    });

    expect(screen.getByRole("button", { name: "Intentar de nuevo" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("offers another model first when the model's quota is exhausted", async () => {
    const error = new ApiRequestError("LLM_UNAVAILABLE", "quota", 502, "req-1", 900, {
      reason: "quota_exhausted",
      details: { model: "gemini-flash" },
    });
    const handlers = renderNotice(error);

    const buttons = screen.getAllByRole("button").map((button) => button.textContent);
    expect(buttons[0]).toBe("Elegir otro modelo");
    await userEvent.click(screen.getByRole("button", { name: "Elegir otro modelo" }));
    expect(handlers["onChangeModel"]).toHaveBeenCalledOnce();
  });

  it("shows the request code to copy when the administrator must be told", () => {
    renderNotice(new ApiRequestError("NO_MODELS_AVAILABLE", "none", 503, "req-77"));

    expect(screen.getByText("req-77", { selector: "code" })).toBeDefined();
    expect(screen.getByRole("button", { name: /Copiar código/ })).toBeDefined();
  });

  it("does not offer a retry for a problem with the file", () => {
    renderNotice(new ApiRequestError("PROTECTED_FILE", "password", 422, "req-1"));

    expect(screen.queryByRole("button", { name: "Intentar de nuevo" })).toBeNull();
    expect(screen.getByRole("button", { name: "Elegir otro archivo" })).toBeDefined();
  });
});
