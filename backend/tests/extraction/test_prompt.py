from app.documents.models import DocumentFormat, DocumentPage, ExtractedDocument, PageSource
from app.extraction.prompt import CLOSING_REQUEST, INSTRUCTIONS, NO_TEXT_LAYER_NOTE, build_content
from app.extraction.schema import ExtractedItem, ExtractedQuestionnaire
from app.llm.client import ImagePart, TextPart


def _page(number: int, source: PageSource, image: bytes | None) -> DocumentPage:
    return DocumentPage(
        number=number,
        text=f"text {number}",
        image_png=image,
        char_count=6,
        figure_coverage=0.0,
        source=source,
    )


def test_each_page_is_sent_as_text_followed_by_its_image() -> None:
    document = ExtractedDocument(
        document_format=DocumentFormat.PDF,
        filename="t.pdf",
        pages=(
            _page(1, PageSource.TEXT_LAYER, b"png1"),
            _page(2, PageSource.IMAGE_ONLY, b"png2"),
            _page(3, PageSource.TEXT_LAYER, None),
        ),
    )

    content = build_content(document)

    assert content == [
        TextPart("=== Page 1 ===\ntext 1"),
        ImagePart(b"png1", required=False),
        TextPart(f"=== Page 2 === {NO_TEXT_LAYER_NOTE}\ntext 2"),
        ImagePart(b"png2", required=True),
        TextPart("=== Page 3 ===\ntext 3"),
        TextPart(CLOSING_REQUEST),
    ]


def test_instructions_name_every_field_of_the_internal_schema() -> None:
    fields = {
        field.alias
        for model in (ExtractedQuestionnaire, ExtractedItem)
        for field in model.model_fields.values()
        if field.alias
    }

    assert fields
    assert all(f'"{name}"' in INSTRUCTIONS for name in fields)
