#!/bin/sh
# Rebuild the FAOSTYLE register from the part files, the markdown guide and the PDF.
set -e
cd "$(dirname "$0")/.."
python3 scripts/validate_part.py fao_styleguide.md parts/*.json
python3 scripts/parse_appendix2.py fao_styleguide.md parts/W_appendix2.json
python3 scripts/merge_register.py fao_styleguide.md parts overrides.json build/merged
python3 scripts/apply_corrections.py build/merged corrections.json
python3 -W ignore scripts/pdf_enrich.py fao_styleguide.md pdf/cb8081en.pdf build/merged/fao_style_register.json build/merged/fao_recommended_words.json build/final
python3 scripts/pdf_examples.py build/final/fao_style_register.json build/final/regex_vs_pdf_examples.tsv
python3 scripts/finalize.py build/final pdf/cb8081en.pdf
