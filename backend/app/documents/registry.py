"""Single entry point: `extract(data, filename) -> ExtractedDocument`.

Validates the upload, detects the real type from its magic bytes (and checks it against the
extension), dispatches to the matching extractor, and fails with NO_TEXT when nothing usable is
found. Extractors are CPU-bound and synchronous: call them through `run_in_threadpool`.
"""
