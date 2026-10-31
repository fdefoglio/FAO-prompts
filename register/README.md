# FAOSTYLE rule register

Every rule in FAOSTYLE (Publishing at FAO – English, revised November 2024, CB8081EN), in machine-readable form, for a preflight script and for the FAO editing skills. Each rule carries the guide's own wording, its line in the markdown guide, its page in the PDF, how it can be checked, and what the editor should do with a hit.

**Status:** compiled 30 October 2026, independently audited and corrected. Under review by the editor before first use; until then every finding is reported as Verify (see the execution policy in the header).

## Files

| File | Content |
|---|---|
| `fao_style_register.json` | Header (sources, checksums, counts, execution policy, -ise exceptions), `overrides` (project decisions), `open_questions` (contradictions in the guide, with proposed defaults), `rules` (§1–§12), `coverage` (every heading in the guide and its status) |
| `fao_recommended_words.json` | Appendix 2, List of recommended words: one entry per headword, with forbidden → preferred pairs where the guide gives them |
| `SCHEMA.md` | Field definitions |
| `overrides.json` | Source of the overrides, open questions and duplicate links |
| `corrections.json` | Fixes from the independent audit, applied on every rebuild, plus the execution policy |
| `parts/*.json` | Section-by-section extraction (the source of the rules) |
| `fao_styleguide_pdf_enriched.md` | The guide's text with the PDF formatting restored: `*italic*`, `**bold**`, `^sup^`, `~sub~`, `{+…}` teal example (correct form), `{-…}` red example (form to avoid), `{=…}` green template text (literal) |
| `scripts/` | Build pipeline |

## Reading a rule

```json
{"id": "NUM-10_2-001", "section": "10.2", "lines": [1566, 1568], "pdf_page": 46,
 "quote": "Use percent (never per cent) rather than the symbol % in text, ...",
 "rule": "Write percent, never per cent.", "kind": "mandatory", "scope": ["body", "..."],
 "check": {"method": "regex", "pattern": "..."}, "action": "Apply", "relevance": "manuscript"}
```

- `kind`: mandatory, preference or guidance.
- `action`: Apply (editor fixes; unambiguous), Verify (editor decides), Author (only the author can resolve), Info.
- `check.method`: regex, wordlist, module (needs a script with state, e.g. `nocs`, `acronym_first_use`), agent (needs reading with judgement), manual (layout; not visible in a manuscript).
- `relevance`: manuscript (checkable in an author manuscript), production (FAO publishing staff), reference (background).
- Mandatory rules are never offered to the author as a choice (OVR-11).

## Running the preflight

```
python3 register/preflight/preflight.py MANUSCRIPT_for_ai.md \
    --register register/fao_style_register.json --words register/fao_recommended_words.json \
    --nocs nocs/nocsDataExport_20261030.csv --nocs-script nocs/nocs_check.py --out-dir OUT
# annexes: add --context MAIN_TEXT_for_ai.md (abbreviations defined in the main text are not reported again)
```

Input: the labelled markdown from editor_tool --export (preferred), or a .docx. Outputs: `<stem>_preflight_findings.csv` (one row per spot, with the [N] label), `<stem>_preflight_receipt.md` (coverage of the guide, modules not yet built) and `<stem>_agent_checklist.md` (rules that need judgement). Every finding is reported as Verify during calibration.

First calibration: FAO Technical Guide on the VGGT and Indigenous Peoples plus four annexes (October 2026): 90 percent of findings on the main guide were correct in the first run; the false-positive sources found there are fixed (see corrections.json, "Calibration" notes).

## Rebuilding

The build needs the markdown guide and the PDF next to the scripts:

```
cd register
curl -sSLf -o fao_styleguide.md https://raw.githubusercontent.com/fdefoglio/FAO_part2_LTJ/main/fao_styleguide.md
mkdir -p pdf && cp /path/to/cb8081en.pdf pdf/        # the official PDF (not committed here)
pip install pymupdf
sh scripts/build_register.sh                         # writes build/final/
```

The build validates every quote against the guide (it must appear verbatim at the cited lines), merges the parts, applies the audit corrections, restores PDF formatting and tests the regex rules against the PDF's red and teal examples. When FAO revises the guide, the markdown checksum in the header changes; re-extract only the sections whose text changed.
