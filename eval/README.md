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
