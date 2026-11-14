from app.documents.models import DocumentFormat, DocumentPage, ExtractedDocument, PageSource
from app.extraction.chunking import (
    Chunk,
    answer_key_pages,
    make_chunk,
    merge,
    plan_chunks,
    split_chunk,
)
from app.extraction.prompt import CONTEXT_NOTE, build_content
from app.extraction.schema import ExtractedQuestionnaire
from app.llm.client import ImagePart, TextPart


def _document(*texts: str, scanned: tuple[int, ...] = ()) -> ExtractedDocument:
    pages = tuple(
        DocumentPage(
            number=number,
            text=text,
            image_png=f"png{number}".encode(),
            char_count=len(text),
            figure_coverage=0.0,
            source=PageSource.IMAGE_ONLY if number in scanned else PageSource.TEXT_LAYER,
        )
        for number, text in enumerate(texts, start=1)
    )
    return ExtractedDocument(document_format=DocumentFormat.PDF, filename="t.pdf", pages=pages)


def _part(
    *items: tuple[int, str], titulo: str | None = None, idioma: str = "it"
) -> ExtractedQuestionnaire:
    return ExtractedQuestionnaire.model_validate(
        {
            "titulo": titulo,
            "idioma": idioma,
            "items": [
                {"numero": number, "enunciado": text, "tipo": "desarrollo", "pagina": 1}
                for number, text in items
            ],
        }
    )


TEN_PAGES = _document(*[f"page {n}" for n in range(1, 10)], "Soluzioni: 1-B, 2-C")


def test_short_document_is_a_single_part_without_context() -> None:
    document = _document("a", "b")

    assert plan_chunks(document, pages_per_chunk=8) == [Chunk(pages=(1, 2), context_pages=())]


def test_long_document_is_split_with_next_page_and_answer_key_as_context() -> None:
    chunks = plan_chunks(TEN_PAGES, pages_per_chunk=4)

    assert chunks == [
        Chunk(pages=(1, 2, 3, 4), context_pages=(5, 10)),
        Chunk(pages=(5, 6, 7, 8), context_pages=(9, 10)),
        Chunk(pages=(9, 10), context_pages=()),
    ]


def test_answer_keys_are_detected_in_several_languages() -> None:
    document = _document("1. Domanda", "Answer key", "Clave de respuestas", "Testo normale")

    assert answer_key_pages(document) == (2, 3)


def test_split_chunk_halves_its_pages_and_recomputes_context() -> None:
    chunk = plan_chunks(TEN_PAGES, pages_per_chunk=4)[0]

    assert split_chunk(TEN_PAGES, chunk) == (
        Chunk(pages=(1, 2), context_pages=(3, 10)),
        Chunk(pages=(3, 4), context_pages=(5, 10)),
    )


def test_part_content_marks_context_pages_and_only_requires_own_scans() -> None:
    document = _document("one", "two", "three", scanned=(2, 3))

    content = build_content(document, make_chunk(document, [2]))

    assert content[0] == TextPart(
        "This request covers pages 2-2 of a 3-page document. Extract only the items that start "
        f"on pages 2-2. Pages marked {CONTEXT_NOTE} are included only to complete an item that "
        "continues there or to read an answer key."
    )
    assert isinstance(content[1], TextPart)
    assert content[1].text.startswith("=== Page 2 === (no text layer")
    assert content[2] == ImagePart(b"png2", required=True)
    assert content[3] == TextPart(
        f"=== Page 3 === {CONTEXT_NOTE} (no text layer: read it from the image)\nthree"
    )
    assert content[4] == ImagePart(b"png3", required=False)


def test_merge_keeps_order_and_drops_items_repeated_across_parts() -> None:
    merged = merge(
        [
            _part((1, "Prima domanda"), (2, "Seconda domanda che continua")),
            _part((2, "Seconda domanda che continua."), (3, "Terza domanda")),
        ]
    )

    assert [(item.number, item.statement) for item in merged.items] == [
        (1, "Prima domanda"),
        (2, "Seconda domanda che continua"),
        (3, "Terza domanda"),
    ]


def test_merge_renumbers_when_numbers_restart_in_each_part() -> None:
    merged = merge([_part((1, "Uno"), (2, "Due")), _part((1, "Tre"), (2, "Quattro"))])

    assert [(item.number, item.statement) for item in merged.items] == [
        (1, "Uno"),
        (2, "Due"),
        (3, "Tre"),
        (4, "Quattro"),
    ]


def test_merge_takes_the_first_title_and_the_most_common_language() -> None:
    merged = merge(
        [
            _part((1, "a"), idioma="it"),
            _part((2, "b"), titulo="Verifica", idioma="en"),
            _part((3, "c"), idioma="it"),
        ]
    )

    assert merged.title == "Verifica"
    assert merged.language == "it"
