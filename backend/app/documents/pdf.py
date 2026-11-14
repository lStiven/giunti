"""PDF extractor (pdfplumber for content, pypdfium2 for rendering).

Per page: text with formatting marks (bold detected from font names, checkbox symbols kept,
hyphenated line breaks joined), tables as Markdown, text-layer quality detection, raster images
and vector drawings as figures, and a rendered page image. Encrypted PDFs fail with
PROTECTED_FILE.
"""
