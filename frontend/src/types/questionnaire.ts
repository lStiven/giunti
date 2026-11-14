/**
 * Mirror of the API contract (backend/app/extraction/schema.py).
 * Field names are Spanish because the problem statement fixes the JSON contract.
 */

export type ItemType =
  "escala_likert" | "seleccion_multiple" | "verdadero_falso" | "desarrollo" | "emparejamiento";

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

export interface ApiError {
  error: { code: string; message: string; request_id: string | null };
}
