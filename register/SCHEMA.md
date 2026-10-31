# FAOSTYLE rule register — entry schema (v1)

Source: `fao_styleguide.md` (markdown conversion of CB8081EN, FAOSTYLE revised November 2024).
Each part file is a JSON object: `{"part": "<name>", "lines_covered": [start, end], "rules": [ ... ], "sections": [ ... ]}`.

## Rule entry

```json
{
  "id": "NUM-10-003",
  "section": "10",
  "section_title": "NUMBERS",
  "lines": [1470, 1471],
  "quote": "Use numerals where a number accompanies a unit, e.g. 5 cm, 7 percent, USD 2.",
  "rule": "Use numerals, not words, when a number goes with a unit.",
  "kind": "mandatory",
  "scope": ["body", "heading", "caption", "table"],
  "check": {
    "method": "regex",
    "pattern": "\\b(one|two|three|four|five|six|seven|eight|nine|ten)\\s+(percent|cm|mm|m|km|kg|g|t|ha|l|L|°C)\\b",
    "notes": "Flag a number word directly before a unit."
  },
  "action": "Apply",
  "examples": {"correct": ["5 cm", "7 percent", "USD 2"], "incorrect": ["five cm"]},
  "exceptions": [],
  "relevance": "manuscript"
}
```

### Fields

| Field | Required | Content |
|---|---|---|
| `id` | yes | `<PREFIX>-<section>-<NNN>`, unique. Prefixes: PUB (§2), WRT (§3), SPL (§4), PUN (§5), TRM (§6.1–6.2), NAM (§6.3), FOR (§6.4), ABB (§7), CAP (§8), ITA (§9), NUM (§10), NOT (§11), REF (§12), WRD (Appendix 2). Section with dots replaced by underscores, e.g. `PUN-5_6-002` |
| `section` | yes | Section number as in the guide heading, e.g. `"5.6"`, `"6.3.1.2"` |
| `section_title` | yes | Heading text |
| `lines` | yes | `[first, last]` line numbers in `fao_styleguide.md` where the quote sits |
| `quote` | yes | **Verbatim** text copied from those lines (line breaks may become single spaces). The validator rejects a quote that does not occur there. Quote enough to carry the rule, not the whole paragraph |
| `rule` | yes | One normative sentence in plain English. No new content beyond the quote |
| `kind` | yes | `mandatory` (guide says must / do not / always / use X not Y), `preference` (prefer, avoid, where possible, recommended), `guidance` (advice that is not a checkable rule) |
| `scope` | yes | Where the rule applies: any of `body`, `heading`, `caption`, `table`, `figure`, `box`, `footnote`, `reference`, `front_matter`, `title`, `all` |
| `check.method` | yes | `regex` (a pattern finds violations), `wordlist` (list of forbidden → preferred forms), `module` (needs code with state, e.g. first-use tracking, cross-document consistency), `agent` (needs reading with judgement), `manual` (layout/production; not visible in a manuscript text) |
| `check.pattern` | for regex | Python regex that matches a **violation**. Prefer precision over recall; note known false positives |
| `check.pairs` | for wordlist | `[["forbidden", "preferred"], ...]` |
| `check.module` | for module | Short name of the needed module, e.g. `acronym_first_use`, `nocs`, `consistency`, `caption_format`, `heading_case`, `keywords`, `sentence_length` |
| `check.notes` | optional | How to check, known false positives |
| `action` | yes | `Apply` (editor fixes, unambiguous), `Verify` (editor decides), `Author` (only the author can resolve), `Info` (no action; production or context) |
| `examples` | optional | Only examples printed in the guide. `correct` / `incorrect` arrays. These become regression tests |
| `exceptions` | optional | Array of `{"quote": "...", "lines": [a,b], "note": "..."}` — exceptions stated in the guide |
| `relevance` | yes | `manuscript` (checkable in an author manuscript), `production` (layout, cover, design, ISBN — FAO publishing staff), `reference` (background, not a rule) |
| `see_also` | optional | IDs of related rules or other sections |

## Section entry (coverage map)

One per heading (`#`, `##`, `###`, `####`) in the covered lines:

```json
{"section": "10.1", "title": "UNITS", "lines": [1510, 1564], "rule_ids": ["NUM-10_1-001", "..."], "status": "rules", "note": ""}
```

`status`: `rules` (rules extracted), `no_rules` (descriptive text only; say why in `note`), `production_only` (rules exist but all are layout/production).

## Extraction principles

1. Every normative statement becomes a rule. Do not merge two different requirements into one entry; do not split one requirement across entries.
2. Copy quotes exactly. Never paraphrase into `quote`. Never invent examples.
3. Do not add rules from general knowledge or other style guides. If the guide is ambiguous, say so in `check.notes` and use `Verify`.
4. PDF conversion artefacts exist (broken lines, superscripts on separate lines, stray spaces before punctuation). Quote the text as it stands in the file.
5. Prefer `regex` only when a pattern finds violations with good precision. Otherwise use `module`, `agent` or `manual` honestly.
