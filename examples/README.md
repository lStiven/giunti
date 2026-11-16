# Ejemplos

[← Volver al README](../README.md)

Cuestionarios de entrada en los tres formatos que acepta el servicio, junto con el JSON que devolvió la API desplegada para cada uno.

| Archivo | Formato | Qué muestra | Resultado |
|---|---|---|---|
| [prueba-logica.docx](prueba-logica.docx) | Word | Prueba de lógica y matemática. Las respuestas se marcan con negrita, subrayado y resaltado, y una pregunta tiene dos correctas. El verdadero/falso y el emparejamiento solo se responden en una clave al final. Cierra con una pregunta de desarrollo | [JSON](resultados/prueba-logica.json) · [ejecución](resultados/prueba-logica.ejecucion.json) |
| [encuesta-taller.xlsx](encuesta-taller.xlsx) | Excel | Encuesta con escala Likert de 1 a 5 bajo un encabezado combinado. La selección múltiple marca la respuesta con negrita o con relleno. Las respuestas del verdadero/falso están solo en una **hoja oculta**. Cierra con una pregunta abierta | [JSON](resultados/encuesta-taller.json) · [ejecución](resultados/encuesta-taller.ejecucion.json) |
| [ejemplo_examen.pdf](ejemplo_examen.pdf) | PDF | Modelo de examen de lógica matemática de CORFO (Chile). Tiene comprensión lectora, una serie numérica, alternativas que son figuras y una clave de respuestas en la última página | [JSON](resultados/ejemplo_examen.json) · [ejecución](resultados/ejemplo_examen.ejecucion.json) |
| [Depression-Care-and-PHQ9-Spanish.pdf](Depression-Care-and-PHQ9-Spanish.pdf) | PDF | Cuestionario de Salud del Paciente (PHQ-9) en español. Es una escala Likert de 0 a 3 en tabla, con una pregunta final de casillas sin rotular, y una segunda página informativa que no tiene preguntas | [JSON](resultados/Depression-Care-and-PHQ9-Spanish.json) · [ejecución](resultados/Depression-Care-and-PHQ9-Spanish.ejecucion.json) |

## Cómo se obtuvieron los resultados

- **Servicio:** la API en producción (`https://giunti-backend-747240323866.us-central1.run.app`), el 16-11-2026.
- **Modelo y modo:** Gemini 3.8 Flash (`gemini-flash`), en modo rápido (`fast`), el modo por defecto.
- **`resultados/<archivo>.json`:** el cuerpo de la respuesta tal cual lo devolvió la API. Es el formato que pide el enunciado.
- **`resultados/<archivo>.ejecucion.json`:** los datos de la ejecución, que la API envía en los headers para no agregar campos al JSON: modelo, modo, partes, reparaciones, tokens y advertencias (`X-Extraction-Warnings`).

Para repetirlo con tu clave:

```bash
curl -H "X-API-Key: gk_…" -F file=@examples/prueba-logica.docx -F mode=fast \
  https://giunti-backend-747240323866.us-central1.run.app/api/v1/questionnaires
```

## Fuentes de los PDF

Los dos PDF fueron publicados por sus autores para distribuirse. Se incluyen solo como ejemplo, sin fines de lucro:

- `ejemplo_examen.pdf`: *Modelo del Examen de Lógica Matemática*, Proceso de Selección Convocatoria Mil Programadores, CORFO y Sence (Gobierno de Chile), www.corfo.cl. Se entrega a los postulantes para que conozcan la prueba.
- `Depression-Care-and-PHQ9-Spanish.pdf`: *Cuestionario de Salud del Paciente (PHQ-9)*, versión en español de Community Healthcare Network. El PHQ-9 (Pfizer) se puede reproducir, traducir y distribuir sin pedir permiso.

## Verificación

### PDF reales (revisados a mano contra el documento)

**`ejemplo_examen.pdf`** (CORFO), 13 s:

| Pregunta | Ítem | Tipo | Respuesta | Clave del documento |
|---|---|---|---|---|
| 1. Comprensión lectora | Enunciado y 5 alternativas literales | Selección múltiple | `A` | Letra A |
| 2. Serie 17 – 34 – 51 – 68 – ? | Literal | Desarrollo | `null` | 85 (ver limitación 2) |
| 3. Dibujo que completa la serie | 5 alternativas que son figuras (`texto: null`, S8) | Selección múltiple | `B` | Letra B |
| 4. Cubo desplegado | Alternativas I, II y III (figuras) | Selección múltiple | `II` | Número II |

Resultado: 4/4 ítems y 3/3 respuestas de selección correctas, sin advertencias. El título viene sin el subtítulo "Proceso de Selección Convocatoria Mil Programadores".

**`Depression-Care-and-PHQ9-Spanish.pdf`** (PHQ-9), 17 s:

| Ítems | Tipo | Alternativas | Respuesta |
|---|---|---|---|
| 1 a 9 (enunciados literales, incluido el "?" del ítem 8) | Escala Likert | Los valores que muestra el documento, de 0 = "Para nada" a 3 = "Casi todos los días" (S14) | `null`: es una encuesta |
| 10. Dificultad para hacer el trabajo… | Selección múltiple | A–D: "Nada difícil"… "Sumamente difícil". Las casillas no tienen letra, así que se rotulan A, B, C… (S15) | `null` |

Resultado: 10/10 ítems, sin advertencias. Quedaron fuera, correctamente, los campos del paciente, la fila "Totales de la columna" y la segunda página, que es informativa. La pregunta común de la tabla ("En las últimas 2 semanas, ¿qué tan seguido te molestaron…?") no se repite en cada ítem (ver limitación 1).

### Limitaciones que muestran estos ejemplos

1. **Contexto compartido entre preguntas:** el esquema solo tiene el enunciado de cada ítem, así que no hay dónde poner lo que comparten varias preguntas:
   - el texto de lectura de la pregunta 1 de CORFO: el ítem dice "del texto anterior", pero ese texto no viaja en el JSON;
   - el encabezado del PHQ-9 con el período ("En las últimas 2 semanas…").
2. **Respuestas de desarrollo:** el esquema solo admite respuesta correcta en selección múltiple, verdadero/falso y emparejamiento. Por eso el "85" de la clave de CORFO no se guarda.

Las dos cambian el contrato del JSON que fija el enunciado, así que quedan como decisión del equipo.

### Word y Excel (comparados automáticamente con su JSON esperado)

El Word y el Excel son **inventados**, así que no tienen derechos de autor. Se generan con el generador de [`eval/`](../eval/README.md) a partir de las especificaciones [`es_ejemplo_word_logica.json`](../eval/generator/specs/es_ejemplo_word_logica.json) y [`es_ejemplo_excel_taller.json`](../eval/generator/specs/es_ejemplo_excel_taller.json). Cada especificación es, al mismo tiempo, el JSON que la API debe devolver. Comparado campo por campo:

| Archivo | Ítems | Respuestas correctas | Diferencias con lo esperado |
|---|---|---|---|
| `encuesta-taller.xlsx` | 8/8 | 4/4, incluidas las 2 de la hoja oculta | Ninguna |
| `prueba-logica.docx` | 8/8 | 7/7, incluidas las 3 de la clave al final y la de dos correctas | Solo de formato: en el emparejamiento, el `valor` de las premisas vino como texto (`"1"`) en vez de número (`1`). El esquema acepta ambos |

Para regenerarlos: `cd eval && just generate es_ejemplo_word_logica es_ejemplo_excel_taller`.
