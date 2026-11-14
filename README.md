# Extracción de cuestionarios

Servicio que recibe un cuestionario o prueba de evaluación (PDF, DOCX o XLSX) e identifica sus ítems, su tipo (escala Likert, selección múltiple, verdadero/falso, desarrollo, emparejamiento), sus alternativas y, si el documento la indica, la respuesta correcta. Devuelve un JSON estructurado.

## Estructura

```
giunti/
├── backend/              API FastAPI (Python 3.13, uv)
├── frontend/             React + Vite + TypeScript (sitio estático)
├── eval/                 Tests sintéticos, datasets y evaluación de calidad
├── scripts/              Herramientas del repositorio (chequeo de dependencias deprecadas)
├── .devcontainer/        Entorno de desarrollo (mismas versiones que producción)
├── justfile              Comandos de todo el repositorio (carga los justfile de cada proyecto)
├── docker-compose.yml    Despliegue "todo junto" (backend + frontend con nginx)
└── .github/workflows/    CI: controles de calidad y auditoría de dependencias
```

## Entorno de trabajo

Abrir el repositorio en el **devcontainer** (VS Code: "Dev Containers: Reopen in Container"). Incluye Python 3.13, uv, Node 22, LibreOffice, `just` y `pre-commit`, e instala todo con `just setup` al crearse.

```bash
cp backend/.env.example backend/.env   # completar
just                                   # lista de comandos (cada proyecto tiene además su propio justfile)
just backend::dev                      # API → http://localhost:8080 (docs en /docs)
just frontend::dev                     # Frontend → http://localhost:5173
just check                             # formato, lint, imports, tipos, tests y build de todo
just backend::check                    # solo un proyecto (o: cd backend && just check)
just up                                # todo junto con docker compose → http://localhost:8000
```

## API

| Endpoint | Qué hace |
|---|---|
| `GET /api/v1/models` | Modelos disponibles agrupados por proveedor, con su descripción y el modelo por defecto. Solo aparecen los modelos cuyo proveedor tiene API key configurada. |
| `POST /api/v1/questionnaires` | Recibe un archivo (`file`, multipart) y opcionalmente el modelo (`model`, un `id` de `GET /models`). Devuelve el JSON del cuestionario. Consume una unidad de la cuota diaria del cliente. |
| `GET /health` | Estado del servicio (sin autenticación). |

Ambos endpoints de `/api/v1` exigen la API key del cliente en el header `X-API-Key`:

```bash
just backend::create-key acme 100 10      # cliente, límite diario, límite por minuto
# → imprime la key (una sola vez) y la entrada JSON para agregar a API_KEYS en backend/.env

curl -H "X-API-Key: gk_acme_..." -F file=@cuestionario.pdf -F model=gemini-flash \
  http://localhost:8080/api/v1/questionnaires
```

La respuesta del `POST` incluye headers con datos de la ejecución: `X-LLM-Model`, `X-LLM-Input-Tokens`, `X-LLM-Output-Tokens`, `X-LLM-Repairs`, `X-LLM-Duration-Ms`, `X-Extraction-Parts` (en cuántas partes se procesó un documento largo), `X-Extraction-Warnings` (lista JSON de advertencias: contenido que no se pudo verificar contra el documento, páginas escaneadas, etc.) y `X-RateLimit-Remaining-Day`. Los errores siguen el formato `{"error": {"code", "message", "request_id"}}`; al superar un límite se responde `429 RATE_LIMITED` con `Retry-After`.

Los modelos se configuran en [backend/llm_catalog.toml](backend/llm_catalog.toml) y las API keys en `backend/.env` (`GEMINI_API_KEY`, `LLM_API_KEYS`).

## Supuestos

Cuando el enunciado admite más de una interpretación, se elige la más razonable, se registra aquí y se avanza. Cada supuesto indica qué era ambiguo, qué se asumió y por qué.

### Entrada

| # | Ambigüedad | Supuesto | Por qué |
|---|---|---|---|
| S1 | ¿Uno o varios archivos por petición? | **Un archivo por petición.** | El enunciado habla de subir un archivo. Varios archivos se cubren con varias peticiones. |
| S2 | ¿Qué versiones de Word y Excel? | Solo `.docx` y `.xlsx`. `.doc`, `.xls` y los formatos con macros (`.docm`, `.xlsm`) se rechazan con `UNSUPPORTED_FORMAT`. | El enunciado nombra `.docx` y `.xlsx`; los formatos antiguos y con macros agregan riesgo sin beneficio. |
| S3 | ¿Puede un archivo traer varios cuestionarios? | Cada archivo se trata como **un solo cuestionario**. Si tiene secciones, todos sus ítems van en la misma lista. | El esquema de salida tiene un solo `titulo` y una sola lista de `items`. |
| S4 | ¿La clave de respuestas puede venir en otro archivo? | Solo se usa la información **del mismo archivo** (marcas de formato o clave incluida en él). | Con un archivo por petición no hay forma de asociar dos archivos. |
| S5 | ¿Qué imágenes se procesan? | Solo las de **PDF y Word**, y solo para leer el texto de preguntas que vienen como imagen o para ubicar las figuras de una pregunta. Las de Excel se ignoran. | Indicación del equipo. |
| S20 | ¿Qué hacer con las hojas ocultas de un Excel? | Se **incluyen**, marcadas como ocultas. Las hojas vacías se omiten. | A veces la clave de respuestas está en una hoja oculta; marcarla deja al modelo decidir con esa información. |

### Salida

| # | Ambigüedad | Supuesto | Por qué |
|---|---|---|---|
| S6 | `respuesta_correcta` aparece como texto en el ejemplo, pero un ítem puede tener varias respuestas correctas. | Es una **lista** (`["C"]`, `["A", "D"]`) o `null`. | Cubre selección múltiple con varias correctas, verdadero/falso y emparejamiento con un solo tipo de dato. |
| S7 | El esquema no prevé el emparejamiento (dos columnas). | Un ítem por ejercicio con el campo extra **`premisas`** (columna A); `alternativas` es la columna B; la respuesta son pares: `["1-c", "2-a"]`. En los demás tipos `premisas` es `[]`. | Mantiene la numeración del documento y evita que el modelo reorganice el contenido. |
| S8 | ¿Cómo representar alternativas que son figuras ("¿qué figura falta?")? | `texto: null`; `valor` lleva la etiqueta (A, B, C…). | No se pide al modelo describir imágenes, que es donde más inventa. |
| S9 | ¿`respuesta_correcta` cuando el documento no la indica? | `null`. Solo se llena con evidencia en el documento (negrita, subrayado, resaltado, casilla marcada o clave de respuestas). | Evitar respuestas inventadas. |
| S10 | ¿Qué hacer si no hay título? | `titulo: null`. | No inventar contenido. |
| S11 | ¿Formato de `idioma`? | Código ISO 639-1 (`it`, `es`, `en`…), como en el ejemplo. Se detectan al menos italiano, español e inglés; otros idiomas se devuelven con su código. | Es el formato del ejemplo y un estándar. |
| S12 | `total_items` | Se calcula en código como la cantidad de ítems. | No depender del modelo para un dato derivable. |
| S13 | ¿Qué es `numero`? | El número que muestra el documento. Si no hay numeración, o se repite entre secciones, se numera de forma correlativa desde 1. | Respeta el documento y garantiza números únicos. |
| S14 | Valores de la escala Likert | Si el documento muestra valores numéricos, se usan esos. Si no, enteros consecutivos desde 0 en el orden mostrado. | Es lo que muestra el ejemplo (`Mai` = 0 … `Sempre` = 3). |
| S15 | Valores de selección múltiple sin letras | Si el documento no rotula las opciones, se usan A, B, C… en el orden mostrado. | Da una referencia estable para `respuesta_correcta`. |
| S16 | Verdadero/falso sin opciones escritas | Dos alternativas `V` / `F`, con el texto en el idioma del documento (por ejemplo, `Vero` / `Falso`). | El tipo implica esas dos opciones aunque el documento no las escriba. |
| S17 | Textos con errores de extracción (palabras cortadas por guion al final de línea) | Se reconstruyen las palabras cortadas, pero el contenido se copia **literal**: sin traducir, corregir ni resumir. | Fidelidad al documento original. |

### Errores y acceso

| # | Ambigüedad | Supuesto | Por qué |
|---|---|---|---|
| S18 | ¿Cómo informar los errores? | JSON `{"error": {"code", "message", "request_id"}}` con códigos estables en inglés y el código HTTP correspondiente (por ejemplo, 422 `NO_ITEMS` si no se detectan ítems, 415 `UNSUPPORTED_FORMAT` si el formato no es válido). | El cliente puede reaccionar al código sin interpretar textos, y el `request_id` permite rastrear el caso en los logs. |
| S19 | El módulo de autenticación no define usuarios. | Acceso con **API key** por cliente, tanto para el frontend como para integraciones por API. | Los clientes de prueba no necesitan registro, roles ni historial. |
| S21 | ¿Qué modelo se usa si el cliente no elige uno? | El `default_model` del catálogo (Gemini Flash); si su proveedor no tiene API key, el primer modelo habilitado. Nunca hay fallback: si el modelo falla, se devuelve el error. | Las integraciones por API no quedan obligadas a enviar el modelo, y el cliente siempre sabe qué modelo produjo el resultado (header `X-LLM-Model`). |
