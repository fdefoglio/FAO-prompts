# Heading inventory

`extract_headings.py` lists every heading in a manuscript, and every bold-only paragraph. A bold-only paragraph is often a title or a heading the author typed in bold instead of applying a Word heading style.

```
python3 extract_headings.py MANUSCRIPT_for_ai.md --body
```

- **Input:** an editor_tool export (`[N] # Heading` lines), plain markdown, or a .docx.
- **Output:** a table of position, level and word count, plus the heading text.
  - Bold-only paragraphs appear with the level `bold?`.
  - `--body` adds the number of paragraphs under each heading, for the section-balance check.

**How the fao-manuscript-editing skill uses it:** in Phase 0b, step "Bold pseudo-headings".

1. Each bold line that is really a heading becomes `[N] ## Text` under the same label in the labelled markdown.
2. On import, editor_tool applies the Word style `Heading N` and drops the direct bold. This was tested on 31 October 2026.

The script came from the retired fao-heading-preflight skill.
