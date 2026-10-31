#!/usr/bin/env python3
"""Build a heading inventory for the FAO heading preflight check.

Usage:
    python extract_headings.py <file.md|file.docx> [--body]

Handles:
  * editor_tool v2/v3 markdown exports -> "[N] # Heading" lines
    (v2 tags headings that carry a bookmark as "[N] [SPECIAL] # Heading")
  * plain markdown                   -> "# Heading" lines
  * .docx                            -> paragraphs with a Heading style

Bold-only paragraphs are reported as level "bold?" because a title or heading
that lost its style shows up that way, and that is one of the defects this
check exists to catch.

--body also prints the paragraph count sitting under each heading, which is
what the section-balance check needs.
"""

import re
import sys
import zipfile
from xml.etree import ElementTree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

MD_HEADING = re.compile(r"^(?:\[(?P<num>\d+)\]\s*)?(?:\[SPECIAL\]\s*)?(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*$")
MD_BOLD_ONLY = re.compile(r"^(?:\[(?P<num>\d+)\]\s*)?(?:\[SPECIAL\]\s*)?\*\*(?P<text>.+?)\*\*\s*$")
MD_PARA = re.compile(r"^\[(?P<num>\d+)\]\s+(?P<text>.+)$")


def from_markdown(path):
    items = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("<!--"):
                continue
            m = MD_HEADING.match(line)
            if m:
                items.append((m.group("num") or "", "H" + str(len(m.group("hashes"))),
                              m.group("text"), True))
                continue
            m = MD_BOLD_ONLY.match(line)
            if m:
                items.append((m.group("num") or "", "bold?", m.group("text"), True))
                continue
            m = MD_PARA.match(line)
            if m:
                items.append((m.group("num"), "", "", False))
            else:
                items.append(("", "", "", False))
    return items


def from_docx(path):
    with zipfile.ZipFile(path) as zf:
        root = ElementTree.fromstring(zf.read("word/document.xml"))
    items = []
    for idx, para in enumerate(root.iter(W + "p")):
        style_el = para.find(f"{W}pPr/{W}pStyle")
        style = style_el.get(W + "val") if style_el is not None else ""
        runs = [t.text or "" for t in para.iter(W + "t")]
        text = "".join(runs).strip()
        if not text:
            continue
        if style and style.lower().startswith("heading"):
            digits = "".join(ch for ch in style if ch.isdigit())
            items.append((str(idx), "H" + digits if digits else style, text, True))
            continue
        bolds = para.findall(f".//{W}rPr/{W}b")
        if bolds and len(bolds) >= len(para.findall(f".//{W}r")) and len(text) < 200:
            items.append((str(idx), "bold?", text, True))
            continue
        items.append((str(idx), "", "", False))
    return items


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_body = "--body" in sys.argv
    if not args:
        print(__doc__)
        return 1
    path = args[0]
    items = from_docx(path) if path.lower().endswith(".docx") else from_markdown(path)

    headings = [(i, it) for i, it in enumerate(items) if it[3]]
    print(f"{'POS':>8}  {'LEVEL':<6}  WORDS  HEADING")
    print("-" * 78)
    for n, (i, (num, level, text, _)) in enumerate(headings):
        words = len(text.split())
        body = ""
        if show_body:
            end = headings[n + 1][0] if n + 1 < len(headings) else len(items)
            body = f"   [{sum(1 for x in items[i + 1:end] if not x[3])} paras]"
        pos = f"[{num}]" if num else "-"
        print(f"{pos:>8}  {level:<6}  {words:>5}  {text}{body}")

    levels = [it[1] for _, it in headings if it[1].startswith("H")]
    print("-" * 78)
    print(f"{len(headings)} headings; levels present: {sorted(set(levels)) or 'none'}")
    if any(it[1] == 'bold?' for _, it in headings):
        print("NOTE: bold-only paragraphs found — check whether one is the title.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
