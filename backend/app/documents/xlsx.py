"""XLSX extractor (openpyxl, cached values only).

Each sheet becomes a Markdown table without empty rows or columns. Merged cell values are
propagated, bold or filled cells are marked, missing cached formula values produce a warning,
and images are ignored.
"""
