# FAO comment-sheet finalisation — prompt template

Reusable for P5, P8, P14 and P16. Replace every `{{...}}` before sending.
Attach: the edited DOCX, the author-annotated comment sheet CSV, and any separate
author documents (abstract, revised sections).

---

## Attachments for this run

| Role | File |
|---|---|
| Manuscript to finalise | `{{REF}}_{{Pn}}_final_Edited.docx` |
| Author-annotated comment sheet | `With_author_responses_{{REF}}_CommentSheet__{{Pn}}_final.csv` |
| Separate author documents | `{{list, or "none"}}` |

If a filename in this brief does not match an attached file, work from the attachment
and tell me about the mismatch rather than pausing.

---

## Job

Finalise `{{REF}}_{{Pn}}_final_Edited.docx` by implementing the author's decisions in the
attached comment sheet, working the CSV row by row in order.

For each row, the author's text in the **Remarks** column is the instruction. Treat it as
follows:

- **Author agreed to a proposed edit** → apply the edit.
- **Author supplied content** (a source, a gloss, bibliographic data, a URL) → incorporate it,
  reformatted to FAOSTYLE rather than pasted verbatim.
- **Author declined, or confirmed the current text** → leave the text as it stands and record
  that no change was needed.
- **Author left the decision to the editor** → decide it, apply the decision, and state the
  FAOSTYLE rule or series precedent it rests on.
- **Author's remark is ambiguous or internally inconsistent** → apply the reading that requires
  the smallest change to the manuscript, and flag the ambiguity in the returned CSV rather than
  asking me mid-run.

### Struck-through material

Where the previous pass left proposed deletions as strikethrough for review and the author has
agreed, delete that material outright — this is the finalisation pass, so strikethrough is no
longer a useful state. Where the author has not agreed, or has not addressed it, leave the
strikethrough in place and note it.

### Author-supplied sources

Verify each source the author supplies before you cite it — check that the URL resolves, that
the date matches, and that the source actually supports the claim it is attached to.

- If the source checks out, cite it and add the reference entry.
- If the source is sound but its **metadata** contradicts the manuscript (wrong year, wrong
  author key), correct the manuscript to match the source, propagate the correction to every
  in-text citation, and flag the correction for author confirmation.
- If the source is sound but does **not support the claim as written**, cite it at the narrowest
  point it does support, leave the claim's wording untouched, and raise it as an author query.
  Do not soften or rewrite the claim yourself — that is the author's call.
- If the source cannot be verified, add it with the detail available, mark the uncertain field,
  and flag it.

### Editorial fixes outside the CSV

While working through the document, you will see errors the comment sheet does not cover.

- If the fix is mechanical and carries no meaning risk — duplicated phrases, em dashes, stray
  hard formatting, spacing, a `%` in running text — fix it, highlight it, and log it as a
  separate row.
- If the fix would change meaning, emphasis or structure, leave the text alone and log it as a
  flagged observation. Locked mode applies: no paraphrasing, no synonym substitution, no
  sentence-level rewriting.

### Author-supplied prose (abstracts, new sections)

Copy-edit it to FAOSTYLE before insertion — that is the point of the compliance check — but keep
the author's substance and argument intact. Splitting a sentence over 34 words is in scope;
cutting content to hit a word-count preference is not. If the text sits outside a FAOSTYLE
preferred range but inside its hard limit, insert it as is and flag the gap for the author.

Where the author's document and the manuscript both carry the same element (keyword line, title,
heading), the manuscript version wins if it already conforms to the series conventions recorded
in project memory. State which you kept and why.

---

## Why

The author needs a clean, submission-ready file. FAO compliance is the second half of the job:
the new material and every change made in response to the author's remarks has to satisfy
FAOSTYLE, and none of it may introduce a new error into text that was already compliant.

The audit trail matters as much as the file. `{{client contact}}` needs to see what changed, on
whose authority, and against which rule — without re-reading the manuscript.

---

## Guardrails

- Highlight every insertion and every modification in yellow. Deletions cannot carry a
  highlight, so record each one in the returned CSV with its page and the text removed — that
  is their audit trail.
- Preserve all existing formatting the change does not touch: italics on titles and foreign
  terms, list styles, heading styles, run-level emphasis.
- Apply FAOSTYLE and the project's `conflicts.md` precedence order. Cite the rule number or
  section for any judgment call you make on the editor's own authority.
- Keep the word-count drift within 8 percent, excluding the author's newly supplied material.
- Add reference entries only where the author supplied the source or authorised its addition.
- Where a new convention has to be chosen (italicisation of a foreign term, an author key for a
  corporate source), match what the manuscript already does and flag the inconsistency, rather
  than introducing a second treatment mid-document.

---

## What done looks like

Two files, plus a short summary in chat.

**1. `{{REF}}_{{Pn}}_final_Edited_v2.docx`** — the finalised manuscript, yellow-highlighted, no
residual strikethrough from resolved items.

**2. `With_author_responses_{{REF}}_CommentSheet__{{Pn}}_final_implemented.csv`** — the original
sheet returned unchanged in its existing columns, with two columns appended:

| Column | Contents |
|---|---|
| `Status` | `Implemented` · `Implemented — author query` · `Implemented editorially` · `Flagged — no change` |
| `Implementation note` | What was done, where (page), and the FAOSTYLE rule where one governed. For an author query, state the question plainly. |

Append editorial fixes found outside the comment sheet as extra rows, numbered `E1`, `E2`, …,
after a blank separator row.

**3. Summary in chat** — lead with anything needing an author or client decision before
delivery, then the rest. Keep it short; the CSV holds the detail.

---

## Notes for this paper

{{Anything specific to this manuscript — known open items, prior decisions to carry over, series
precedents that apply. Delete this section if there are none.}}
