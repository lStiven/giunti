import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only cleans up automatically when the runner exposes globals; Vitest does not.
afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
