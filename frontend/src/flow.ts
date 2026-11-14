/**
 * The page's state machine: key → choose file and model → processing → result or error.
 *
 * Every transition lives here, so components only render the state and dispatch actions.
 */
import type { ApiRequestError } from "./api/client";
import type { ExtractionResult, ModelCatalog } from "./types/questionnaire";

export type Stage =
  "needsKey" | "checkingKey" | "unavailable" | "ready" | "processing" | "done" | "failed";

export interface FlowState {
  stage: Stage;
  apiKey: string | null;
  catalog: ModelCatalog | null;
  model: string | null;
  file: File | null;
  result: ExtractionResult | null;
  error: ApiRequestError | null;
}

export type FlowAction =
  | { type: "keyChecking"; apiKey: string }
  | { type: "keyAccepted"; catalog: ModelCatalog }
  | { type: "keyRejected"; error: ApiRequestError }
  | { type: "catalogFailed"; error: ApiRequestError }
  | { type: "catalogRetried" }
  | { type: "keyChangeRequested" }
  | { type: "fileChosen"; file: File | null }
  | { type: "modelChosen"; model: string }
  | { type: "extractionStarted" }
  | { type: "extractionSucceeded"; result: ExtractionResult }
  | { type: "extractionFailed"; error: ApiRequestError }
  | { type: "extractionCancelled" }
  | { type: "tryAnotherModel" }
  | { type: "startOver" };

export function initialState(apiKey: string | null): FlowState {
  return {
    stage: apiKey === null ? "needsKey" : "checkingKey",
    apiKey,
    catalog: null,
    model: null,
    file: null,
    result: null,
    error: null,
  };
}

export function flowReducer(state: FlowState, action: FlowAction): FlowState {
  switch (action.type) {
    case "keyChecking":
      return { ...state, stage: "checkingKey", apiKey: action.apiKey, catalog: null, error: null };
    case "keyAccepted":
      return {
        ...state,
        stage: "ready",
        catalog: action.catalog,
        model: keptOrDefault(state.model, action.catalog),
        error: null,
      };
    case "keyRejected":
      return { ...state, stage: "needsKey", apiKey: null, catalog: null, error: action.error };
    case "catalogFailed":
      return { ...state, stage: "unavailable", error: action.error };
    case "catalogRetried":
      return { ...state, stage: "checkingKey", error: null };
    case "keyChangeRequested":
      return { ...state, stage: "needsKey", error: null };
    case "fileChosen":
      return { ...state, file: action.file, error: null };
    case "modelChosen":
      return { ...state, model: action.model };
    case "extractionStarted":
      return { ...state, stage: "processing", result: null, error: null };
    case "extractionSucceeded":
      return { ...state, stage: "done", result: action.result };
    case "extractionFailed":
      return { ...state, stage: "failed", error: action.error };
    case "extractionCancelled":
    case "tryAnotherModel":
      return { ...state, stage: "ready", result: null, error: null };
    case "startOver":
      return { ...state, stage: "ready", file: null, result: null, error: null };
  }
}

function keptOrDefault(model: string | null, catalog: ModelCatalog): string | null {
  const available = catalog.providers.flatMap((provider) => provider.models.map((m) => m.id));
  if (model !== null && available.includes(model)) {
    return model;
  }
  return available.includes(catalog.default_model) ? catalog.default_model : (available[0] ?? null);
}

export function modelLabel(catalog: ModelCatalog | null, modelId: string): string {
  for (const provider of catalog?.providers ?? []) {
    const model = provider.models.find((candidate) => candidate.id === modelId);
    if (model) {
      return model.label;
    }
  }
  return modelId;
}
