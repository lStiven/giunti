"""Safety checks for untrusted uploads.

File size limit, maximum uncompressed size of DOCX/XLSX archives (zip bombs), and rejection of
macro-enabled (.docm, .xlsm) and legacy (.doc, .xls) formats.
"""
