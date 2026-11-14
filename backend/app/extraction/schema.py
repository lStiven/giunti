"""Questionnaire schemas.

Public contract (JSON field names are fixed by the problem statement, so they are Spanish and
mapped through Pydantic aliases): `titulo`, `idioma`, `total_items`, `items`; each item has
`numero`, `enunciado`, `tipo`, `alternativas`, `premisas`, `respuesta_correcta`.
Item types: escala_likert, seleccion_multiple, verdadero_falso, desarrollo, emparejamiento.
An alternative with `texto: null` is a figure. Matching answers look like `["1-c", "2-a"]`.

The internal schema requested from the model adds the source page and the evidence for each
correct answer; those fields are removed before responding.
"""
