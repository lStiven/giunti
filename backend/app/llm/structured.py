"""Problem-agnostic structured output.

`ExtractionTask[T]` bundles a Pydantic schema, a prompt and a validation function.
`run(task, content)` requests JSON, parses it, validates it with Pydantic and with the task
rules, retries once with the validation errors, and moves to the next model if it still fails.
JSON is requested in the prompt instead of each provider's native structured output so every
provider behaves the same.
"""
