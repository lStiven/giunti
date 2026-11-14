# Backend: API de extracción de cuestionarios

FastAPI + LiteLLM. Recibe un archivo (PDF, DOCX o XLSX) y devuelve los ítems del cuestionario como JSON. Cómo funciona por dentro, con diagramas: [guia/funcionamiento.md](../guia/funcionamiento.md).

## Ejecutar en local

```bash
cp .env.example .env        # completar GEMINI_API_KEY y API_KEY_PEPPER
just setup                  # dependencias
just create-admin           # primer administrador: imprime el enlace al panel
just dev                    # API en http://localhost:8080 (documentación en /docs)
just check                  # formato, lint, imports, tipos y tests
just                        # todos los comandos
```

La conversión de DOCX requiere **LibreOffice** instalado en el sistema (`soffice`). En Docker y en el devcontainer ya viene incluido. Todas las variables están explicadas en [.env.example](.env.example), y los modelos en [llm_catalog.toml](llm_catalog.toml).

## Estructura

| Carpeta | Contenido | ¿Se reutiliza? |
|---|---|---|
| `app/core/` | Configuración, logging JSON, errores, base de datos | Sí |
| `app/api/` | Middleware (request_id), manejo de errores, salud, catálogo de modelos | Sí |
| `app/auth/` | API keys (HMAC), clientes, límite de peticiones, rutas del panel de administración | Sí |
| `app/documents/` | PDF / DOCX (vía LibreOffice) / XLSX → texto + imágenes de página | Sí |
| `app/llm/` | LiteLLM con un modelo por petición, reintentos, reparación, pausas por modelo, salida estructurada genérica | Sí |
| `app/extraction/` | **Lo específico del problema**: esquema, instrucciones, reglas, verificación, partes, clave de respuestas y ruta | **Se reemplaza** |

## Usar como base para otro problema

1. Copiar el proyecto.
2. Reemplazar `app/extraction/` (esquema, instrucciones, reglas, ruta) y `tests/extraction/`.
3. Ajustar `.env` (límites) y `llm_catalog.toml` (modelos).

Nada fuera de `app/extraction/` debe mencionar cuestionarios; `import-linter` lo comprueba.
