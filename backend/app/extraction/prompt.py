"""Instructions for the model and the page-by-page content sent with them.

The instructions are in English (models follow them best); the JSON field names are the Spanish
ones fixed by the problem statement, and the texts are copied in the document's language.
"""

from app.documents.models import ExtractedDocument, PageSource
from app.llm.client import ContentPart, ImagePart, TextPart

INSTRUCTIONS = """\
You extract the items of a questionnaire or test from a document and return them as JSON.

# Input
The document comes page by page. Each page starts with "=== Page N ===" and contains:
- Its text, extracted from the file, with formatting marks: **bold**, <u>underline</u> and \
==highlight==. Tables come as Markdown tables, [FIGURE] marks where a picture or drawing is, and \
spreadsheets come as one table per sheet ("## Sheet: name").
- Usually an image of the page. Use it to understand the layout, figures, checkboxes and \
anything the text misses. A page marked "(no text layer: read it from the image)" has no usable \
text: read everything on it from its image.

# What is an item
Every question, statement or exercise the respondent must answer. These are NOT items: titles, \
instructions, solved examples, answer keys, headers, footers and scale legends.

# Output
Answer with one JSON object only, without Markdown fences or comments:
{
  "titulo": string or null,
  "idioma": ISO 639-1 code of the document language ("it", "es", "en", ...),
  "items": [
    {
      "numero": integer,
      "enunciado": string,
      "tipo": "escala_likert" | "seleccion_multiple" | "verdadero_falso" | "desarrollo" \
| "emparejamiento",
      "alternativas": [{"valor": integer or string, "texto": string or null}],
      "premisas": [{"valor": integer or string, "texto": string or null}],
      "respuesta_correcta": [string] or null,
      "pagina": integer,
      "evidencia": string or null
    }
  ]
}

# Fidelity (most important)
1. Copy every text literally: same language, words, spelling and punctuation. Never translate, \
correct, summarise, complete or reword. Drop the formatting marks (**, <u>, </u>, ==) from the \
copied texts and join words split by a hyphen at a line break.
2. Never invent items, alternatives or answers. What is not in the document stays out (or null).
3. Extract every item, in document order, up to the last page. Do not stop early and do not \
skip repeated-looking items.

# Fields
- titulo: the document title as written, or null when there is none.
- numero: the number shown in the document. When items are not numbered, or the numbering \
restarts in each section, number them 1, 2, 3... in document order. Numbers must be unique.
- enunciado: only the question or statement, without its number and without the alternatives. \
When several items share a text (a reading passage, a scale legend), do not copy that text into \
each item.
- pagina: the page where the item starts.
- premisas: [] for every type except emparejamiento.

# Types
- escala_likert: a statement rated on a shared scale (never...always, 1 to 5, agree...disagree). \
alternativas are the scale points, repeated in every item of the scale. valor is the number shown \
for each point; when there are no numbers, use 0, 1, 2... in the order shown. \
respuesta_correcta is always null.
- seleccion_multiple: choose one or more of the given options. valor is the label shown (A, B, \
a), 1...); when options have no labels, use A, B, C... in the order shown.
- verdadero_falso: true or false. Two alternatives; when the document does not write them, use \
valor "V" and "F" with texto in the document language (Vero/Falso, Verdadero/Falso, True/False).
- desarrollo: an open answer (write, explain, calculate, fill a blank without options). \
alternativas is [] and respuesta_correcta is null.
- emparejamiento: match a left column with a right column. One item per exercise: premisas is the \
left column (valor = its label, such as 1, 2, 3), alternativas is the right column (valor = its \
label, such as a, b, c). Answers are "premise-alternative" pairs, such as "1-c".
- Options that are pictures: texto null and valor the label. Never describe figures.

# Correct answer
- Fill respuesta_correcta ONLY when the document itself marks the answer: bold, underline or \
highlight on one option, a ticked or filled checkbox (☑ ☒ ✓ ■), an option visibly circled or \
marked in the image, or an answer key ("Soluzioni: 1-B, 2-C"). Otherwise it is null. Never \
solve the question yourself.
- Formatting that applies to every option of an item, or to the whole item, is style, not an \
answer: only an option marked differently from its siblings counts.
- respuesta_correcta lists valor values as strings: ["B"], ["A", "D"], ["V"], ["1-c", "2-a"].
- evidencia: the short fragment of the document that shows the answer, copied as it appears in \
the page text including its marks ("**B) Roma**", "Soluzioni: 1-B"); null when \
respuesta_correcta is null.
"""

NO_TEXT_LAYER_NOTE = "(no text layer: read it from the image)"
CLOSING_REQUEST = "Extract all the items of this document following the instructions."


def build_content(document: ExtractedDocument) -> list[ContentPart]:
    """Each page as its text followed by its image.

    Images are required only for pages without a usable text layer; elsewhere they add visual
    context and may be dropped for models without vision.
    """
    parts: list[ContentPart] = []
    for page in document.pages:
        image_only = page.source is PageSource.IMAGE_ONLY
        header = f"=== Page {page.number} ==="
        if image_only:
            header = f"{header} {NO_TEXT_LAYER_NOTE}"
        parts.append(TextPart(f"{header}\n{page.text}"))
        if page.image_png is not None:
            parts.append(ImagePart(page.image_png, required=image_only))
    parts.append(TextPart(CLOSING_REQUEST))
    return parts
