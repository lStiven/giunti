# Problemas frecuentes

[← Volver al README](../README.md)

**Primer paso siempre:** mira el estado y los logs.

```bash
docker compose ps                     # ¿ambos servicios "healthy"?
docker compose logs --tail 50 backend # últimas líneas del backend
```

Cada error que muestra la página incluye un **código de solicitud**. Búscalo en los logs para ver el detalle: `docker compose logs backend | grep <código>`.

## Al instalar o levantar

| Síntoma | Causa | Solución |
|---|---|---|
| `docker: command not found` o `Cannot connect to the Docker daemon` | Docker no está instalado o no está abierto | Instálalo y ábrelo (ver [requisitos](instalacion.md#1-requisitos)) |
| `docker compose` no existe, pero `docker-compose` sí | Compose v1, ya obsoleto | Instala Docker Desktop o el plugin `docker-compose-plugin` |
| `port is already allocated` | El puerto 8000 está ocupado | Pon `APP_PORT=8001` (u otro) en el `.env` de la raíz y repite `docker compose up -d` |
| `env file …/backend/.env not found` | No se creó `backend/.env` | `cp backend/.env.example backend/.env` y complétalo |
| El backend no arranca: `API_KEY_PEPPER must be a random secret…` | Con `APP_ENV=production`, el secreto es el de ejemplo o tiene menos de 32 caracteres | Genera uno largo ([paso 4.2](instalacion.md#4-configura-el-backend)) |
| `docker compose ps` muestra el backend `unhealthy` o reiniciándose | El backend no arranca por configuración inválida | `docker compose logs backend` muestra el motivo |
| El frontend se queda en `Created` y no arranca | Espera a que el backend esté sano | Resuelve primero el problema del backend |
| La página carga, pero sin estilos o en blanco | Construcción incompleta | `docker compose up -d --build --force-recreate` |

## Al usar el servicio

| Síntoma | Causa | Solución |
|---|---|---|
| "El servicio no tiene modelos configurados" | Ningún proveedor tiene API key | Completa `GEMINI_API_KEY` en `backend/.env` y ejecuta `docker compose up -d --force-recreate backend` |
| "Se agotó la cuota del modelo" | El proyecto de Gemini alcanzó su límite de gasto o de cuota | Sube el límite en [ai.studio/spend](https://ai.studio/spend) o espera a que se renueve; mientras tanto, elige otro modelo |
| "La clave de acceso no es válida" para todos | Cambió `API_KEY_PEPPER` o se borró la base de datos | Crea un administrador nuevo y nuevas invitaciones |
| "La clave de acceso no es válida" para un cliente | Se generó una **Nueva invitación** y la anterior dejó de funcionar | Envíale el enlace nuevo |
| Perdí el enlace del administrador | Solo se muestra una vez | Ejecuta de nuevo el comando que crea el administrador: crea otro. Después elimina el anterior con `python -m app.auth.delete_client <id>` (ver [uso](uso.md#panel-de-administración)) |
| El enlace de invitación abre una dirección equivocada | `PUBLIC_APP_URL` no corresponde a la dirección real | Corrígelo (en el `.env` de la raíz con Docker Compose, en `backend/.env` en desarrollo), reinicia y genera una **Nueva invitación** |
| "Alcanzaste el límite de uso" | El cliente llegó a su límite por minuto o diario | Espera, o sube sus límites en el panel (**Editar acceso**) |
| "No encontramos preguntas" (`NO_ITEMS`) | El documento no parece un cuestionario, o el modelo no lo leyó bien | Prueba con otro modelo |
| Las respuestas correctas quedan vacías | El documento no marca la respuesta (o la marca de una forma que no se detecta) | Es lo esperado: nunca se inventan respuestas. Revisa las advertencias del resultado |
| Los Word fallan con "Algo falló en el servidor" (sin Docker ni devcontainer) | LibreOffice no está instalado | Instálalo, o usa Docker Compose o el devcontainer |
| Error de CORS en la consola del navegador | El frontend se sirve desde otro dominio que el backend | Agrega ese dominio a `CORS_ORIGINS` en `backend/.env` |

## En un servidor con dominio

| Síntoma | Causa | Solución |
|---|---|---|
| Las extracciones largas fallan siempre a los 60 o 100 segundos, pero las cortas funcionan | El proxy inverso corta la petición antes de que termine | Sube su tiempo de espera a 900 s, o usa Caddy (ver [servidor propio](servidor-propio.md#5-pon-https-con-caddy)) |
| Los archivos de más de 1 MB fallan antes de procesarse (error 413) | El nginx de delante tiene el límite de subida por defecto | Agrega `client_max_body_size 25m;` en su configuración |
| Caddy no obtiene el certificado | El DNS aún no apunta al servidor, o los puertos 80/443 están cerrados | Comprueba el registro A y el firewall; `sudo journalctl -u caddy` muestra el motivo |
| `http://IP:8000` responde desde fuera del servidor | `APP_BIND_ADDRESS` no está en `127.0.0.1` | Agrégalo al `.env` de la raíz y ejecuta `docker compose up -d` |

¿No está aquí? Revisa los logs con el código de solicitud y [Cómo funciona](funcionamiento.md) para ubicar en qué etapa falló.
