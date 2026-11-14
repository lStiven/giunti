# Backend: API de extracción de cuestionarios

FastAPI + LiteLLM. Recibe un archivo (PDF, DOCX o XLSX) y devuelve los ítems del cuestionario como JSON.

## Ejecutar en local

```bash
cp .env.example .env        # completar modelos, claves y API_KEYS
just setup                  # dependencias
just dev                    # API en http://localhost:8080
just check                  # formato, lint, imports, tipos y tests
just                        # todos los comandos
```

La conversión de DOCX requiere **LibreOffice** instalado en el sistema (`soffice`). En Docker ya viene incluido.

## Estructura

| Carpeta | Contenido | ¿Se reutiliza? |
|---|---|---|
| `app/core/` | Configuración, logging JSON, errores | Sí |
| `app/api/` | Middleware (request_id), manejo de errores, salud | Sí |
| `app/auth/` | API keys (HMAC), límite de peticiones | Sí |
| `app/documents/` | PDF / DOCX (vía LibreOffice) / XLSX → texto + imágenes de página | Sí |
| `app/llm/` | LiteLLM con fallback, clasificación de errores, salida estructurada genérica | Sí |
| `app/extraction/` | **Lo específico del problema**: esquema, prompt, validadores, verificación, ruta | **Se reemplaza** |

## Usar como base para otro problema

1. Copiar el proyecto.
2. Reemplazar `app/extraction/` (esquema, prompt, validadores, ruta) y `tests/extraction/`.
3. Ajustar `.env` (modelos y límites).

Nada fuera de `app/extraction/` debe mencionar cuestionarios.
