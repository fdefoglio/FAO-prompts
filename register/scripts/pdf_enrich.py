#!/usr/bin/env python3
"""Restore formatting lost in the markdown conversion, using the real FAOSTYLE PDF.

Usage: python3 pdf_enrich.py STYLEGUIDE.md GUIDE.pdf REGISTER.json [WORDS.json] OUT_DIR

For every rule (and every example string) the quote is located in the PDF page that the
markdown line belongs to (via the <!-- page N --> markers), matching with all whitespace
removed so that wrapped lines and split superscripts still match. The matched PDF span is
re-rendered with inline markup:
    *italic*   **bold**   ^superscript^   ~subscript~
    {+text}  teal example (correct form)   {-text}  red example (form to avoid)
    {=text}  green template text (literal)
and stored as `quote_pdf` / `examples_pdf` when it differs from the plain text. Each rule
also gets `pdf_page`. Writes the updated JSON files and a report of rules whose meaning
depends on formatting, plus an enriched page-by-page text of the guide.
"""
import json
import os
import re
import sys

import pymupdf

# The PDF colour-codes its examples: teal = correct/illustrative form, red = form to avoid,
# green (in §12.8 templates) = literal text that stays as shown. Other colours are headings.
SEMANTIC = {0x029baf: 'ok', 0x009baf: 'ok', 0xff0100: 'avoid', 0x538135: 'literal'}
FIX = {'\u0002': '-', '­': '-', '': '•', ' ': ' ', ' ': ' '}


def page_chars(page):
    """List of (char, attrs) for a page, in reading order, with whitespace kept."""
    out = []
    d = page.get_text('rawdict')
    for b in d['blocks']:
        for line in b.get('lines', []):
            spans = line['spans']
            if not spans:
                continue
            body = max(spans, key=lambda s: (len(s['chars']), s['size']))
            base_size, base_y = body['size'], body['origin'][1]
            for s in spans:
                font = s['font']
                ital = 'Italic' in font or 'Oblique' in font or bool(s['flags'] & 2)
                bold = 'Bold' in font or bool(s['flags'] & 16)
                small = s['size'] < base_size * 0.85
                dy = s['origin'][1] - base_y
                sup = bool(s['flags'] & 1) or (small and dy < -0.5)
                sub = small and dy > 0.2 and not sup
                colour = SEMANTIC.get(s['color'])
                for ch in s['chars']:
                    c = FIX.get(ch['c'], ch['c'])
                    out.append((c, (ital, bold, sup, sub, colour)))
            out.append((' ', (False, False, False, False, None)))
        out.append((' ', (False, False, False, False, None)))
    return out


def render(chars):
    res, cur = [], (False, False, False, False, None)
    marks = [('*', '*'), ('**', '**'), ('^', '^'), ('~', '~')]

    def close(a):
        s = ''
        if a[4]:
            s += '}'
        for k in (3, 2, 1, 0):
            if a[k]:
                s += marks[k][1]
        return s

    def open_(a):
        s = ''
        for k in (0, 1, 2, 3):
            if a[k]:
                s += marks[k][0]
        if a[4]:
            s += {'ok': '{+', 'avoid': '{-', 'literal': '{='}[a[4]]
        return s
    for c, a in chars:
        if c.isspace():
            a = cur if not any(cur[:4]) and not cur[4] else cur  # spaces inherit
            res.append(' ')
            continue
        if a != cur:
            res.append(close(cur) + open_(a))
            cur = a
        res.append(c)
    res.append(close(cur))
    return re.sub(r'\s+', ' ', ''.join(res)).strip()


def squash_index(chars):
    """String of non-space chars and map from squashed index to chars index."""
    s, idx = [], []
    for i, (c, a) in enumerate(chars):
        c = CANON.get(c, c)
        for cc in c:
            if not cc.isspace():
                s.append(cc)
                idx.append(i)
    return ''.join(s), idx


CANON = {'•': '', '…': '...', 'µ': 'μ', '\uf0a7': ''}


def norm_q(q):
    q = re.sub(r'(^|\s)-\s', ' ', q)                    # markdown list bullets
    q = ''.join(CANON.get(c, FIX.get(c, c)) for c in q)
    q = re.sub(r'\s+', '', q)
    return q


def main():
    md_path, pdf_path, reg_path = sys.argv[1:4]
    words_path = sys.argv[4] if len(sys.argv) > 5 else None
    out = sys.argv[-1]
    os.makedirs(out, exist_ok=True)
    md = open(md_path, encoding='utf-8').read().split('\n')
    page_of_line, cur = [], 1
    for l in md:
        m = re.match(r'<!-- page (\d+) -->', l)
        if m:
            cur = int(m.group(1))
        page_of_line.append(cur)
    doc = pymupdf.open(pdf_path)
    pages = {}

    def chars_for(pn):
        if pn not in pages:
            pages[pn] = page_chars(doc[pn - 1]) if 1 <= pn <= doc.page_count else []
        return pages[pn]

    # enriched full text for reference
    with open(os.path.join(out, 'fao_styleguide_pdf_enriched.md'), 'w', encoding='utf-8') as f:
        for pn in range(1, doc.page_count + 1):
            f.write(f'\n<!-- pdf page {pn} -->\n{render(chars_for(pn))}\n')

    def locate(text, pn):
        q = norm_q(text)
        if len(q) < 3:
            return None, None
        for cand in (pn, pn + 1, pn - 1):
            for span in ((cand,), (cand, cand + 1)):
                chars = sum((chars_for(p) for p in span), [])
                s, idx = squash_index(chars)
                k = s.find(q)
                if k < 0:
                    # tolerate a lost hyphen or bullet glyph from the conversion
                    q2 = q.replace('•', '')
                    k = s.replace('•', '').find(q2) if q2 != q else -1
                    if k >= 0:
                        continue
                if k >= 0:
                    seg = chars[idx[k]: idx[k + len(q) - 1] + 1]
                    return render(seg), span[0]
        return None, None

    report, stats = [], dict(rules=0, located=0, formatted=0, examples_formatted=0)
    files = [reg_path] + ([words_path] if words_path else [])
    for path in files:
        data = json.load(open(path, encoding='utf-8'))
        for r in data['rules']:
            stats['rules'] += 1
            pn = page_of_line[r['lines'][0] - 1]
            rendered, page = locate(r['quote'], pn)
            if rendered is None:
                r['pdf_page'] = pn
                r['pdf_match'] = False
                continue
            stats['located'] += 1
            r['pdf_page'] = page
            plain = re.sub(r'\s+', ' ', r['quote']).strip()
            if re.search(r'[*^~]|\{[+=-]', rendered):
                r['quote_pdf'] = rendered
                stats['formatted'] += 1
                report.append((r['id'], page, rendered))
            exs = r.get('examples') or {}
            exp = {}
            for kind in ('correct', 'incorrect'):
                for e in exs.get(kind, []) or []:
                    rend, _ = locate(e, pn)
                    if rend and re.search(r'[*^~]|\{[+=-]', rend):
                        exp.setdefault(kind, []).append(rend)
            if exp:
                r['examples_pdf'] = exp
                stats['examples_formatted'] += 1
        base = os.path.basename(path)
        json.dump(data, open(os.path.join(out, base), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(os.path.join(out, 'pdf_formatting_report.tsv'), 'w', encoding='utf-8') as f:
        f.write('id\tpdf_page\tquote_with_formatting\n')
        for rid, p, t in report:
            f.write(f'{rid}\t{p}\t{t}\n')
    print(json.dumps(stats))


if __name__ == '__main__':
    main()
