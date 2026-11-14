"""Grounding checks against the source document (anti-hallucination).

Statements and alternatives must appear in their page text, answer evidence must exist in the
source, and the item numbering found in the source must match the extracted items. Pages without
a text layer cannot be checked this way and are flagged.
"""
