"""Generates synthetic tests from `generator/specs/*.json`.

Each spec yields, as applicable: a DOCX (automatic numbering, answers marked with bold,
underline, highlight or checkboxes, Likert tables, two-column matching, figure images, text
boxes, answer key at the end), an XLSX (Likert matrix with merged headers, multiple choice rows,
answers marked with bold or fill), a PDF converted with LibreOffice, and a "scanned" PDF
(rasterized with noise and slight rotation, no text layer). The spec is copied next to each
generated file as the expected JSON.
"""
