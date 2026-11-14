/** User-facing texts (Spanish) and the translation of API error codes. */
import type { ExtractionNotice, ItemType } from "./types/questionnaire";

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

/** What the error screen offers, most useful first. */
export type ErrorAction =
  "retry" | "wait" | "changeModel" | "changeFile" | "reenterKey" | "contactAdmin";

export interface ErrorGuidance extends ErrorText {
  actions: ErrorAction[];
}

/** The parts of a failed request that decide what to tell the user. */
export interface ErrorFacts {
  code: string;
  reason: string | null;
  details: Record<string, number | string>;
  retryAfterSeconds: number | null;
  elapsedMs: number | null;
}

const CODE_ACTIONS: Record<string, ErrorAction[]> = {
  UNSUPPORTED_FORMAT: ["changeFile"],
  INVALID_FILE: ["changeFile"],
  EMPTY_FILE: ["changeFile"],
  FILE_TOO_LARGE: ["changeFile"],
  PROTECTED_FILE: ["changeFile"],
  NO_TEXT: ["changeFile"],
  NO_ITEMS: ["changeFile", "changeModel"],
  LLM_UNAVAILABLE: ["retry", "changeModel"],
  INVALID_LLM_RESPONSE: ["retry", "changeModel"],
  NO_MODELS_AVAILABLE: ["contactAdmin"],
  UNAUTHENTICATED: ["reenterKey"],
  FORBIDDEN: ["reenterKey", "contactAdmin"],
  RATE_LIMITED: ["wait"],
  INVALID_REQUEST: ["changeModel", "retry"],
  INTERNAL_ERROR: ["retry", "contactAdmin"],
  NETWORK_ERROR: ["retry"],
  INVALID_RESPONSE: ["retry", "contactAdmin"],
  TIMED_OUT: ["changeFile", "retry"],
};

type ReasonText = (facts: ErrorFacts, wait: string | null) => ErrorGuidance;

function detail(facts: ErrorFacts, key: string): string {
  const value = facts.details[key];
  return value === undefined ? "" : String(value);
}

function modelName(facts: ErrorFacts): string {
  const model = detail(facts, "model");
  return model ? `«${model}»` : "elegido";
}

const REASON_TEXTS: Record<string, ReasonText> = {
  file_size: (facts) => ({
    title: "El archivo es demasiado grande",
    hint: `Pesa ${detail(facts, "actual_mb")} MB y el máximo es ${detail(facts, "limit_mb")} MB. Reduce su tamaño (por ejemplo, comprimiendo las imágenes) o divídelo en partes.`,
    actions: ["changeFile"],
  }),
  uncompressed_size: () => ({
    title: "El archivo ocupa demasiado al abrirlo",
    hint: "Suele pasar con imágenes muy pesadas dentro del Word o Excel. Redúcelas y vuelve a subirlo.",
    actions: ["changeFile"],
  }),
  too_many_pages: (facts) => ({
    title: "El documento tiene demasiadas páginas",
    hint: `Tiene ${detail(facts, "actual")} páginas y el máximo es ${detail(facts, "limit")}. Divídelo en partes más cortas y súbelas por separado. En un Word se cuentan las páginas tal como se imprimen.`,
    actions: ["changeFile"],
  }),
  too_many_sheets: (facts) => ({
    title: "El Excel tiene demasiadas hojas",
    hint: `Tiene ${detail(facts, "actual")} hojas y el máximo es ${detail(facts, "limit")}. Deja solo las hojas del cuestionario y vuelve a subirlo.`,
    actions: ["changeFile"],
  }),
  sheet_too_large: () => ({
    title: "Una hoja del Excel es demasiado grande",
    hint: "Elimina las filas y columnas que no son parte del cuestionario y vuelve a subirlo.",
    actions: ["changeFile"],
  }),
  legacy_format: () => ({
    title: "Formato antiguo de Office",
    hint: "Abre el archivo en Word o Excel y guárdalo como .docx o .xlsx; luego súbelo de nuevo.",
    actions: ["changeFile"],
  }),
  macros: () => ({
    title: "El archivo tiene macros",
    hint: "Guárdalo sin macros, como .docx o .xlsx normal, y vuelve a subirlo.",
    actions: ["changeFile"],
  }),
  extension_mismatch: (facts) => ({
    title: "La extensión no coincide con el contenido",
    hint: `El archivo es en realidad un ${detail(facts, "detected").toUpperCase()}. Guárdalo de nuevo en el formato correcto y vuelve a subirlo.`,
    actions: ["changeFile"],
  }),
  not_a_document: () => ({
    title: "El archivo no es un PDF, Word ni Excel",
    hint: "Puede ser otro tipo de archivo con la extensión cambiada. Exporta el cuestionario a PDF y súbelo.",
    actions: ["changeFile"],
  }),
  conversion_failed: () => ({
    title: "No pudimos convertir el Word",
    hint: "Ábrelo en Word y guárdalo de nuevo, o expórtalo a PDF y sube el PDF.",
    actions: ["changeFile"],
  }),
  model_not_responding: (facts, wait) => ({
    title: "El modelo no respondió",
    hint: wait
      ? `El modelo ${modelName(facts)} pidió esperar ${wait}. Puedes esperar o elegir otro modelo.`
      : `El modelo ${modelName(facts)} no respondió tras varios intentos. Suele ser momentáneo: intenta de nuevo o elige otro modelo.`,
    actions: wait ? ["wait", "changeModel"] : ["retry", "changeModel"],
  }),
  quota_exhausted: (facts, wait) => ({
    title: "Se agotó la cuota del modelo",
    hint: `El modelo ${modelName(facts)} no estará disponible${wait ? ` durante unos ${wait}` : " por un rato"}. Elige otro modelo o vuelve más tarde.`,
    actions: ["changeModel", "wait"],
  }),
  model_paused: (facts, wait) => ({
    title: "El modelo está en pausa",
    hint: `El modelo ${modelName(facts)} falló varias veces seguidas y se pausó${wait ? ` por ${wait}` : ""}. Espera o elige otro modelo.`,
    actions: ["changeModel", "wait"],
  }),
  model_misconfigured: (facts) => ({
    title: "El modelo no está bien configurado",
    hint: `El modelo ${modelName(facts)} tiene un problema de configuración en el servidor. Elige otro modelo y avisa al administrador.`,
    actions: ["changeModel", "contactAdmin"],
  }),
  model_refused: (facts) => ({
    title: "El modelo se negó a procesar el documento",
    hint: `El modelo ${modelName(facts)} rechazó el contenido. Prueba con otro modelo.`,
    actions: ["changeModel"],
  }),
  output_too_long: () => ({
    title: "El documento tiene demasiado contenido",
    hint: "Una parte del documento tiene más preguntas de las que el modelo puede devolver de una vez. Divídelo en partes más cortas o prueba con otro modelo.",
    actions: ["changeFile", "changeModel"],
  }),
  invalid_output: () => ({
    title: "El modelo no logró extraer las preguntas",
    hint: "La respuesta del modelo no fue válida. Intenta de nuevo; si se repite, prueba con otro modelo.",
    actions: ["retry", "changeModel"],
  }),
  unknown_model: () => ({
    title: "El modelo elegido no existe",
    hint: "Elige uno de los modelos de la lista.",
    actions: ["changeModel"],
  }),
  model_without_key: (facts) => ({
    title: "El modelo elegido no está disponible",
    hint: `El modelo ${modelName(facts)} no está habilitado en el servidor. Elige otro de la lista.`,
    actions: ["changeModel"],
  }),
  document_too_long_for_model: (facts) => ({
    title: "El documento es demasiado largo para este modelo",
    hint: `El modelo ${modelName(facts)} no puede leer un documento de este tamaño. Elige otro modelo o divide el documento.`,
    actions: ["changeModel", "changeFile"],
  }),
  model_cannot_read_images: (facts) => ({
    title: "Este modelo no puede leer páginas escaneadas",
    hint: `El documento tiene páginas que son imágenes y el modelo ${modelName(facts)} solo lee texto. Elige un modelo que lea imágenes.`,
    actions: ["changeModel"],
  }),
  per_minute_limit: (facts, wait) => ({
    title: "Demasiadas solicitudes seguidas",
    hint: `Tu clave permite ${detail(facts, "limit")} extracciones por minuto.${wait ? ` Podrás intentarlo de nuevo en ${wait}.` : ""}`,
    actions: ["wait"],
  }),
  daily_limit: (facts, wait) => ({
    title: "Alcanzaste el límite diario",
    hint: `Tu clave permite ${detail(facts, "limit")} extracciones por día y se renueva a medianoche (UTC)${wait ? `, en ${wait}` : ""}.`,
    actions: ["wait", "contactAdmin"],
  }),
};

/** Title, explanation and the actions to offer for a failed request. */
export function errorGuidance(facts: ErrorFacts): ErrorGuidance {
  const wait = facts.retryAfterSeconds === null ? null : formatWait(facts.retryAfterSeconds);
  const byReason = facts.reason === null ? undefined : REASON_TEXTS[facts.reason];
  if (byReason) {
    return byReason(facts, wait);
  }
  if (facts.code === "TIMED_OUT") {
    const after = facts.elapsedMs === null ? "" : ` después de ${formatDuration(facts.elapsedMs)}`;
    return {
      title: "El procesamiento tardó demasiado",
      hint: `La conexión se cortó${after}, antes de que terminara. Pasa con documentos largos o con muchas imágenes: divídelo en partes más cortas o intenta de nuevo más tarde.`,
      actions: ["changeFile", "retry"],
    };
  }
  if (facts.code === "HTTP_413") {
    return { ...ERROR_TEXTS_FILE_TOO_LARGE, actions: ["changeFile"] };
  }
  if (/^HTTP_5\d\d$/.test(facts.code)) {
    return {
      title: "El servidor no está respondiendo",
      hint: "Puede estar reiniciándose o con demasiado trabajo. Espera un momento e intenta de nuevo.",
      actions: ["retry"],
    };
  }
  const text = errorText(facts.code, facts.retryAfterSeconds);
  const actions = CODE_ACTIONS[facts.code] ?? ["retry"];
  return { ...text, actions: facts.code === "RATE_LIMITED" && wait === null ? ["retry"] : actions };
}

const ERROR_TEXTS_FILE_TOO_LARGE: ErrorText = {
  title: "El archivo es demasiado grande",
  hint: "El servidor no aceptó un archivo de este tamaño. Reduce su tamaño o divídelo en partes.",
};

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

/** Item or page numbers as short ranges: [1, 2, 3, 5, 9, 10] → "1–3, 5, 9 y 10". */
export function formatNumbers(numbers: readonly number[]): string {
  const runs: number[][] = [];
  for (const value of [...new Set(numbers)].sort((a, b) => a - b)) {
    const run = runs[runs.length - 1];
    if (run?.[run.length - 1] === value - 1) {
      run.push(value);
    } else {
      runs.push([value]);
    }
  }
  const parts = runs.flatMap((run) =>
    run.length >= 3 ? [`${String(run[0])}–${String(run[run.length - 1])}`] : run.map(String),
  );
  const last = parts.pop();
  if (last === undefined) {
    return "";
  }
  return parts.length > 0 ? `${parts.join(", ")} y ${last}` : last;
}

function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many;
}

/** A warning of a successful extraction, in Spanish, pointing to items or pages. */
export function noticeText(notice: ExtractionNotice): string {
  const items = formatNumbers(notice.items);
  const pages = formatNumbers(notice.pages);
  const theItems = plural(notice.items.length, `la pregunta ${items}`, `las preguntas ${items}`);
  const thePages = plural(notice.pages.length, `La página ${pages}`, `Las páginas ${pages}`);
  switch (notice.code) {
    case "scanned_pages":
      return `${thePages} ${plural(notice.pages.length, "está escaneada", "están escaneadas")}: ${theItems} se leyeron desde la imagen y no se pudieron comprobar contra el texto. Revísalas.`;
    case "missing_formula_values":
      return `${plural(notice.pages.length, `La hoja ${pages} tiene`, `Las hojas ${pages} tienen`)} fórmulas sin valores guardados. Abre el archivo en Excel, guárdalo y vuelve a subirlo para incluirlas.`;
    case "statement_not_found":
      return `No encontramos tal cual en el texto del documento el enunciado de ${theItems} (puede estar en columnas o dentro de una imagen). Compáralo con el original.`;
    case "options_not_found":
      return `Algunas alternativas de ${theItems} no aparecen tal cual en el texto del documento. Compáralas con el original.`;
    case "answer_not_verified":
      return `No pudimos comprobar en el texto la respuesta correcta de ${theItems} (por ejemplo, si la clave es una imagen). Revísala.`;
    case "missing_item_numbers":
      return `El documento muestra ${plural(notice.items.length, `el número ${items}`, `los números ${items}`)}, pero no ${plural(notice.items.length, "aparece", "aparecen")} en el resultado. Revisa si falta alguna pregunta.`;
    case "answer_key_unread":
      return `No pudimos leer la clave de respuestas (${plural(notice.pages.length, `página ${pages}`, `páginas ${pages}`)}): ${theItems} quedaron sin respuesta correcta.`;
    case "answers_not_in_key":
      return `La clave de respuestas (${plural(notice.pages.length, `página ${pages}`, `páginas ${pages}`)}) no indica la respuesta de ${theItems}. Revísalas en el documento.`;
    default:
      return notice.message;
  }
}
