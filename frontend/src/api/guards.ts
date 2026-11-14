/**
 * Runtime checks for API responses: TypeScript types say nothing about what the server sends.
 */
import {
  ITEM_TYPES,
  type Alternative,
  type Item,
  type ModelCatalog,
  type ModelInfo,
  type ProviderModels,
  type Questionnaire,
} from "../types/questionnaire";

type UnknownRecord = Record<string, unknown>;

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id: string | null;
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isArrayOf<T>(value: unknown, check: (item: unknown) => item is T): value is T[] {
  return Array.isArray(value) && value.every(check);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isAlternative(value: unknown): value is Alternative {
  return (
    isRecord(value) &&
    (typeof value["valor"] === "number" || isString(value["valor"])) &&
    isNullableString(value["texto"])
  );
}

function isItem(value: unknown): value is Item {
  return (
    isRecord(value) &&
    typeof value["numero"] === "number" &&
    isString(value["enunciado"]) &&
    ITEM_TYPES.some((type) => type === value["tipo"]) &&
    isArrayOf(value["alternativas"], isAlternative) &&
    isArrayOf(value["premisas"], isAlternative) &&
    (value["respuesta_correcta"] === null || isArrayOf(value["respuesta_correcta"], isString))
  );
}

export function isQuestionnaire(value: unknown): value is Questionnaire {
  return (
    isRecord(value) &&
    isNullableString(value["titulo"]) &&
    isString(value["idioma"]) &&
    typeof value["total_items"] === "number" &&
    isArrayOf(value["items"], isItem)
  );
}

function isModelInfo(value: unknown): value is ModelInfo {
  return (
    isRecord(value) &&
    isString(value["id"]) &&
    isString(value["label"]) &&
    isString(value["description"]) &&
    typeof value["vision"] === "boolean" &&
    typeof value["free"] === "boolean" &&
    typeof value["is_default"] === "boolean"
  );
}

function isProviderModels(value: unknown): value is ProviderModels {
  return (
    isRecord(value) &&
    isString(value["id"]) &&
    isString(value["label"]) &&
    isString(value["description"]) &&
    isArrayOf(value["models"], isModelInfo)
  );
}

export function isModelCatalog(value: unknown): value is ModelCatalog {
  return (
    isRecord(value) &&
    isString(value["default_model"]) &&
    isArrayOf(value["providers"], isProviderModels)
  );
}

export function apiErrorBody(value: unknown): ApiErrorBody | null {
  if (!isRecord(value) || !isRecord(value["error"])) {
    return null;
  }
  const error = value["error"];
  if (!isString(error["code"]) || !isString(error["message"])) {
    return null;
  }
  return {
    code: error["code"],
    message: error["message"],
    request_id: isString(error["request_id"]) ? error["request_id"] : null,
  };
}

/** The warnings header is a JSON list of strings; anything else counts as no warnings. */
export function parseWarnings(header: string | null): string[] {
  if (header === null) {
    return [];
  }
  try {
    const parsed: unknown = JSON.parse(header);
    return isArrayOf(parsed, isString) ? parsed : [];
  } catch {
    return [];
  }
}
