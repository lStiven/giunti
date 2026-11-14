"""Use case `process(file) -> Questionnaire`, independent of the HTTP transport.

Extract the document, chunk it, run the structured LLM task, merge, validate, and strip internal
fields. Fails with NO_ITEMS when nothing is found.
"""
