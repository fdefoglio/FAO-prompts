# NOCS country-name check

`nocs_check.py` checks a manuscript (.docx, or labelled .md/.txt) against the FAO Names of Countries and Territories (NOCS) database and FAOSTYLE §6.3.1. The FAO skills and procedures fetch it from here at run time, so this folder is the single master copy.

## Files

| File | Purpose |
|---|---|
| `nocs_check.py` | The checker. Python 3, needs `python-docx` and `lxml` for .docx input |
| `test_nocs.py` | Regression cases. Run them after every change to the checker |
| `nocsDataExport_20261030.csv` | Official NOCS export (fao.org/nocs, "download the full collection"), 30 October 2026 |

## Fetch and run

```
BASE=https://raw.githubusercontent.com/fdefoglio/FAO-prompts/main/nocs
curl -sSLf -o nocs_check.py $BASE/nocs_check.py
curl -sSLf -o nocs_export.csv $BASE/nocsDataExport_20261030.csv

python3 nocs_check.py MANUSCRIPT.docx --nocs nocs_export.csv --out-dir OUT            # scan
python3 nocs_check.py MANUSCRIPT.docx --nocs nocs_export.csv --apply FIXED.docx       # fix Apply rows, yellow highlight
python3 nocs_check.py FINAL.docx --nocs nocs_export.csv --gate                        # delivery gate: exit 0 only with Apply 0
python3 -I test_nocs.py nocs_export.csv                                               # regression tests
```

On Windows: `py nocs_check.py "D:\...\P6_final.docx" --nocs nocs_export.csv --gate`.

## Output

- `<stem>_nocs_findings.csv`: ID, Para, Context, Found, Suggested, Action, Rule, Snippet.
- `<stem>_nocs_receipt.md`: data file and checksum, counts, gate result. Deliver it even when it shows zero findings, because it proves the check ran.

| Action | Meaning |
|---|---|
| Apply | Unambiguous editor fix, e.g. Tanzania → the United Republic of Tanzania, Laos → the Lao People's Democratic Republic, Niger → the Niger |
| Verify | Editor decision: possible proper name (Tanzania Land Alliance, High Court of Tanzania), citation key that changes with its reference entry, "(Lao PDR)" abbreviation to delete, "northern Laos", US/UK used as a noun |
| Protected | Left alone: quotations, published titles in references, UK/USA in references, US/UK as adjectives, foreign proper names (Office du Niger) |

Exit codes: 0 = clean (with `--gate`: no Apply rows), 1 = findings, 2 = setup error. The NOCS data must load or the run stops. A run never passes silently.

## Rules applied (FAOSTYLE §6.3.1)

- Short Name in text. When the name ends "(the)", the article goes before it ("the Niger").
- No article at the start of a title or heading, after a colon, comma or en dash in a heading, in keyword lists, or in a place of publication ("Dar es Salaam, United Republic of Tanzania").
- The Short Name for Lists only in lists after a colon, in parentheses and in tables.
- "United States" or "United Kingdom" only after the full name has appeared once. UK and USA are allowed in citations; US, UK and EU are allowed as adjectives.
- NOCS is mandatory. It is never an author choice, and an author reply such as "Laos is fine" does not override it.

## Updating the NOCS data

Download a fresh export at the start of each batch (names change; Nauru became Naoero in June 2026). Commit it here as `nocsDataExport_YYYYMMDD.csv`, run the tests against it, then update the file name in this README and in the skills.
