"""The questionnaire extraction task for one document: schema, instructions and checks."""

from app.documents.models import ExtractedDocument
from app.extraction.grounding import grounding_review
from app.extraction.prompt import INSTRUCTIONS
from app.extraction.schema import ExtractedQuestionnaire
from app.extraction.validators import questionnaire_rules
from app.llm.structured import ExtractionTask

TASK_NAME = "questionnaire"


def questionnaire_task(document: ExtractedDocument) -> ExtractionTask[ExtractedQuestionnaire]:
    return ExtractionTask(
        name=TASK_NAME,
        output_type=ExtractedQuestionnaire,
        instructions=INSTRUCTIONS,
        validate=questionnaire_rules(page_count=len(document.pages)),
        review=grounding_review(document),
    )
