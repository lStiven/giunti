/** User-facing texts (Spanish) and the translation of API error codes. */
import type { ItemType } from "./types/questionnaire";

export interface ErrorText {
  title: string;
  hint: string;
}

const ERROR_TEXTS: Record<string, ErrorText> = {
  UNSUPPORTED_FORMAT: {
    title: "Formato no admitido",
    hint: "Sube un archivo PDF, Word (.docx) o Excel (.xlsx). Los formatos antiguos (.doc, .xls) y con macros no se admiten.",
  },
  INVALID_FILE: {
    title: "No pudimos abrir el archivo",
    hint: "Puede estar dañado o no ser del tipo que indica su extensión. Ábrelo, guárdalo de nuevo y vuelve a subirlo.",
  },
  EMPTY_FILE: { title: "El archivo está vacío", hint: "Elige un archivo con contenido." },
  FILE_TOO_LARGE: {
    title: "El archivo es demasiado grande",
    hint: "Prueba con un archivo más liviano o con menos páginas.",
  },
  PROTECTED_FILE: {
    title: "El archivo tiene contraseña",
    hint: "Quítale la contraseña y vuelve a subirlo.",
  },
  NO_TEXT: {
    title: "No encontramos contenido",
    hint: "El documento parece estar en blanco. Revisa que sea el archivo correcto.",
  },
  NO_ITEMS: {
    title: "No encontramos preguntas",
    hint: "El documento no parece ser un cuestionario o una prueba. Si lo es, prueba con otro modelo.",
  },
  LLM_UNAVAILABLE: {
    title: "El modelo no está disponible ahora",
    hint: "Vuelve a intentarlo en unos minutos o elige otro modelo.",
  },
  INVALID_LLM_RESPONSE: {
    title: "El modelo no logró extraer las preguntas",
    hint: "Prueba de nuevo o elige otro modelo.",
  },
  NO_MODELS_AVAILABLE: {
    title: "El servicio no tiene modelos configurados",
    hint: "Ningún proveedor tiene una clave configurada en el servidor. Avisa al administrador del servicio.",
  },
  UNAUTHENTICATED: {
    title: "La clave de acceso no es válida",
    hint: "Revisa que la hayas copiado completa.",
  },
  FORBIDDEN: {
    title: "Tu clave de acceso está desactivada",
    hint: "Pide una nueva al administrador del servicio.",
  },
  RATE_LIMITED: {
    title: "Alcanzaste el límite de uso",
    hint: "Espera un momento antes de volver a intentarlo.",
  },
  INVALID_REQUEST: {
    title: "No pudimos procesar la solicitud",
    hint: "Revisa el detalle técnico; si el modelo no puede con este documento, elige otro.",
  },
  INTERNAL_ERROR: {
    title: "Algo falló en el servidor",
    hint: "Vuelve a intentarlo. Si se repite, comparte el código de solicitud con soporte.",
  },
  NETWORK_ERROR: {
    title: "No hay conexión con el servidor",
    hint: "Revisa tu conexión a internet e inténtalo de nuevo.",
  },
  INVALID_RESPONSE: {
    title: "El servidor respondió algo inesperado",
    hint: "Vuelve a intentarlo. Si se repite, comparte el código de solicitud con soporte.",
  },
};

const UNKNOWN_ERROR: ErrorText = {
  title: "Ocurrió un error inesperado",
  hint: "Vuelve a intentarlo en unos minutos.",
};

export const BACKEND_ERROR_CODES = [
  "UNSUPPORTED_FORMAT",
  "INVALID_FILE",
  "EMPTY_FILE",
  "FILE_TOO_LARGE",
  "PROTECTED_FILE",
  "NO_TEXT",
  "NO_ITEMS",
  "LLM_UNAVAILABLE",
  "NO_MODELS_AVAILABLE",
  "INVALID_LLM_RESPONSE",
  "UNAUTHENTICATED",
  "FORBIDDEN",
  "RATE_LIMITED",
  "INVALID_REQUEST",
  "NOT_FOUND",
  "INTERNAL_ERROR",
] as const;

export function errorText(code: string, retryAfterSeconds: number | null = null): ErrorText {
  const text = ERROR_TEXTS[code] ?? UNKNOWN_ERROR;
  if (code === "RATE_LIMITED" && retryAfterSeconds !== null) {
    return { ...text, hint: `Podrás intentarlo de nuevo en ${formatWait(retryAfterSeconds)}.` };
  }
  return text;
}

export function formatWait(seconds: number): string {
  if (seconds < 60) {
    return seconds === 1 ? "1 segundo" : `${String(seconds)} segundos`;
  }
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) {
    return minutes === 1 ? "1 minuto" : `${String(minutes)} minutos`;
  }
  const hours = Math.ceil(minutes / 60);
  return hours === 1 ? "1 hora" : `${String(hours)} horas`;
}

export const ITEM_TYPE_LABELS: Record<ItemType, string> = {
  escala_likert: "Escala Likert",
  seleccion_multiple: "Selección múltiple",
  verdadero_falso: "Verdadero o falso",
  desarrollo: "Desarrollo",
  emparejamiento: "Emparejamiento",
};

/** What the user sees while waiting, by elapsed seconds. The API reports no real progress. */
export const WAITING_STAGES: readonly { from: number; text: string }[] = [
  { from: 0, text: "Leyendo el documento…" },
  { from: 6, text: "Analizando cada página…" },
  { from: 20, text: "Identificando las preguntas y sus alternativas…" },
  { from: 50, text: "Verificando el resultado contra el documento original…" },
  { from: 90, text: "Los documentos largos tardan un poco más. Ya casi…" },
];

export function waitingStage(elapsedSeconds: number): string {
  let current = WAITING_STAGES[0]?.text ?? "";
  for (const stage of WAITING_STAGES) {
    if (elapsedSeconds >= stage.from) {
      current = stage.text;
    }
  }
  return current;
}

export function languageName(code: string): string {
  try {
    const name = new Intl.DisplayNames(["es"], { type: "language" }).of(code);
    return name ?? code;
  } catch {
    return code;
  }
}

export function formatDuration(milliseconds: number): string {
  const seconds = Math.round(milliseconds / 1000);
  if (seconds < 60) {
    return `${String(seconds)} s`;
  }
  return `${String(Math.floor(seconds / 60))} min ${String(seconds % 60)} s`;
}
