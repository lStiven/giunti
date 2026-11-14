# Evaluación

Mide si la extracción es correcta: que identifique todos los ítems, su tipo, sus alternativas
y la respuesta correcta, sin inventar nada.

## Contenido

| Ruta | Qué es |
|---|---|
| `generator/` | Genera tests sintéticos (DOCX, XLSX, PDF, PDF escaneado) a partir de una especificación JSON, por lo que la respuesta correcta se conoce de antemano |
| `generator/specs/` | Especificaciones de los tests sintéticos (= JSON esperado) |
| `datasets/public/` | Tests reales descargados de internet (**no se suben a git**; ver su README) |
| `datasets/synthetic/` | Tests generados (no se suben a git; se regeneran) |
| `datasets/expected/` | JSON esperado de cada test real (revisado a mano) |
| `run_eval.py` | Procesa cada test con la API y compara contra lo esperado |
| `metrics.py` | Métricas: ítems encontrados/inventados, tipo, fidelidad de texto, respuesta correcta |
| `compare_extractors.py` | Compara extractor propio vs. Docling vs. MarkItDown |
| `results/` | Resultados de cada corrida (no se suben a git) |

## Uso

```bash
just setup                       # generador + evaluación
just setup --group compare       # además Docling y MarkItDown (pesado)
just generate                    # genera los tests sintéticos
just evaluate http://localhost:8080 <api-key>
```

Generar PDFs desde DOCX requiere LibreOffice (`soffice`) instalado.

## Tests sintéticos

Cada especificación de `generator/specs/` describe un cuestionario inventado: su contenido, cómo se ve (dónde y cómo se marca la respuesta) y en qué formatos se genera. `just generate` (o `just generate <id>…`) crea en `datasets/synthetic/<id>/` los archivos y `<id>.expected.json`, que es exactamente el JSON que debe devolver la API (o el error esperado).

| Especificación | Formatos | Qué prueba |
|---|---|---|
| `it_esempio_enunciado` | DOCX, PDF, XLSX | El ejemplo del enunciado (Likert, selección con respuesta en negrita, desarrollo) en los tres formatos |
| `es_marcas_de_respuesta` | DOCX, PDF, PDF escaneado | Respuesta marcada con negrita, subrayado, resaltado y casilla; dos respuestas correctas; un ítem sin respuesta (`null`); verdadero/falso |
| `en_answer_key_at_the_end` | DOCX, PDF | 60 preguntas en 12 páginas y una clave de respuestas que empieza en página nueva y ocupa dos páginas |
| `it_soluzioni_vero_falso` | DOCX, PDF | Respuestas solo en una lista en línea ("Soluzioni: 1-V, 2-F…") |
| `es_formas_con_numeracion_reiniciada` | DOCX, PDF | Dos formas que reinician la numeración en 1, con una clave por forma (la API debe numerar 1–10, S13) |
| `it_figure_e_abbinamento` | DOCX, PDF | Alternativas que son figuras (`texto: null`, S8) y emparejamiento con distractor (`premisas`, S7) |
| `es_bienestar_sin_respuestas` | DOCX, PDF, PDF escaneado | Likert de 5 puntos y preguntas abiertas: ninguna respuesta debe inventarse |
| `en_survey_spreadsheet` | XLSX | Matriz Likert con encabezado combinado, respuestas en negrita o con relleno y clave en hoja oculta |
| `en_no_questions` | DOCX, PDF | Acta con párrafos numerados y sin preguntas: la API debe responder `422 NO_ITEMS` |

Para agregar un caso, copiar una especificación y cambiarla. El generador valida que la numeración sea 1, 2, 3…, que cada respuesta tenga una marca y que Likert y desarrollo no tengan respuesta.
