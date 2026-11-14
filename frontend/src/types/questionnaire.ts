/**
 * Mirror of the API contract (backend/app/extraction/schema.py and app/api/llm_models.py).
 * Questionnaire field names are Spanish because the problem statement fixes the JSON contract.
 */

export const ITEM_TYPES = [
  "escala_likert",
  "seleccion_multiple",
  "verdadero_falso",
  "desarrollo",
  "emparejamiento",
] as const;

export type ItemType = (typeof ITEM_TYPES)[number];

export interface Alternative {
  valor: number | string;
  /** `null` means the alternative is a figure. */
  texto: string | null;
}

export interface Item {
  numero: number;
  enunciado: string;
  tipo: ItemType;
  alternativas: Alternative[];
  /** Only used by matching items. */
  premisas: Alternative[];
  respuesta_correcta: string[] | null;
}

export interface Questionnaire {
  titulo: string | null;
  idioma: string;
  total_items: number;
  items: Item[];
}

/** Data about the run, read from the response headers. */
export interface RunInfo {
  model: string;
  durationMs: number;
  inputTokens: number;
  outputTokens: number;
  parts: number;
  /** The warnings' English messages, as sent by the API. */
  warnings: string[];
  /** The same warnings with their code and the items or pages they refer to. */
  notices: ExtractionNotice[];
  dailyRemaining: number | null;
}

/** A warning of a successful extraction (header `X-Extraction-Warnings`). */
export interface ExtractionNotice {
  /** Stable code (`scanned_pages`, `statement_not_found`...); "unknown" for plain-text warnings. */
  code: string;
  message: string;
  items: number[];
  pages: number[];
}

export interface ExtractionResult {
  questionnaire: Questionnaire;
  run: RunInfo;
}

export interface ModelInfo {
  id: string;
  label: string;
  description: string;
  vision: boolean;
  free: boolean;
  is_default: boolean;
}

export interface ProviderModels {
  id: string;
  label: string;
  description: string;
  models: ModelInfo[];
}

export interface ModelCatalog {
  default_model: string;
  providers: ProviderModels[];
}
