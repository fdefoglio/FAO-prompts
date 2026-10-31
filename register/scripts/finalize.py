#!/usr/bin/env python3
"""Stamp the PDF source into the header and write the review CSV (with PDF formatting)."""
import csv, hashlib, json, os, sys
d, pdf = sys.argv[1], sys.argv[2]
reg = json.load(open(os.path.join(d, 'fao_style_register.json'), encoding='utf-8'))
words = json.load(open(os.path.join(d, 'fao_recommended_words.json'), encoding='utf-8'))
reg['header']['source']['pdf'] = dict(file='cb8081en.pdf', sha256=hashlib.sha256(open(pdf, 'rb').read()).hexdigest(),
    note='Used to restore formatting lost in the markdown: quote_pdf/examples_pdf mark *italic*, **bold**, ^superscript^, ~subscript~, '
         '{+teal example = correct form}, {-red example = form to avoid}, {=green template text = literal}. pdf_page gives the PDF page.')
reg['header']['counts']['rules_located_in_pdf'] = sum(1 for r in reg['rules'] + words['rules'] if r.get('pdf_match') is not False)
reg['header']['counts']['rules_with_pdf_examples'] = sum(1 for r in reg['rules'] if r.get('pdf_examples'))
json.dump(reg, open(os.path.join(d, 'fao_style_register.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
ov = {}
for o in reg['overrides']:
    for rid in o.get('affects', []):
        ov.setdefault(rid, []).append(o['id'])
with open(os.path.join(d, 'register_review.csv'), 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, quoting=csv.QUOTE_ALL)
    w.writerow(['ID', 'Section', 'Guide lines', 'PDF page', 'Kind', 'Relevance', 'Check', 'Module / pattern / pairs', 'Action',
                'Rule', 'Quote (guide)', 'Quote with PDF formatting', 'Override', 'Duplicate of', 'Reviewer decision', 'Reviewer note'])
    for r in reg['rules'] + words['rules']:
        ch = r['check']
        w.writerow([r['id'], r['section'], f"{r['lines'][0]}–{r['lines'][-1]}", r.get('pdf_page', ''), r['kind'], r['relevance'],
                    ch['method'], ch.get('module') or ch.get('pattern') or '; '.join(f'{a} → {b}' for a, b in ch.get('pairs', [])),
                    r['action'], r['rule'], r['quote'], r.get('quote_pdf', ''), ', '.join(ov.get(r['id'], [])),
                    r.get('duplicate_of', ''), '', ''])
print('final register written to', d)
