#!/usr/bin/env python3
"""Turn the PDF colour coding into per-rule examples and test the regex rules against them.

Usage: python3 pdf_examples.py REGISTER_ENRICHED.json OUT_REPORT.tsv
Adds `pdf_examples: {"ok": [...], "avoid": [...]}` to each rule whose quote_pdf carries teal
({+…}) or red ({-…}) text, writes the JSON back in place, and reports, for regex rules:
  avoid snippets the pattern misses (possible gaps) and ok snippets it flags (false positives).
"""
import json
import re
import sys


def snippets(s):
    t = re.sub(r'\*\*|(?<![{])\*|\^|~', '', s)          # drop bold/italic/sup/sub markers
    t = re.sub(r'\}\s*\{([+=-])', lambda m: ' \x00' + m.group(1), t)   # mark joins
    out = {'ok': [], 'avoid': [], 'literal': []}
    for m in re.finditer(r'\{([+=-])((?:[^{}]|\x00[+=-])*)\}', t):
        kind = {'+': 'ok', '-': 'avoid', '=': 'literal'}[m.group(1)]
        body = m.group(2)
        # split where the colour type changes inside a joined run
        parts = re.split(r'\x00([+=-])', body)
        cur, buf = kind, parts[0]
        for k in range(1, len(parts), 2):
            nk = {'+': 'ok', '-': 'avoid', '=': 'literal'}[parts[k]]
            if nk == cur:
                buf += ' ' + parts[k + 1]
            else:
                out[cur].append(buf)
                cur, buf = nk, parts[k + 1]
        out[cur].append(buf)
    for k in out:
        out[k] = [re.sub(r'\s+', ' ', x).strip(' ,;.') for x in out[k] if x.strip(' ,;.')]
    return out


def main():
    path, rep = sys.argv[1], sys.argv[2]
    data = json.load(open(path, encoding='utf-8'))
    rows, n = [], 0
    for r in data['rules']:
        q = r.get('quote_pdf')
        if not q:
            continue
        ex = snippets(q)
        ex = {k: v for k, v in ex.items() if v}
        if not ex:
            continue
        r['pdf_examples'] = ex
        n += 1
        ch = r.get('check', {})
        if ch.get('method') == 'regex' and r.get('relevance') == 'manuscript':
            try:
                rx = re.compile(ch['pattern'])
            except re.error:
                continue
            miss = [a for a in ex.get('avoid', []) if not rx.search(a)]
            fp = [o for o in ex.get('ok', []) if rx.search(o)]
            if miss or fp:
                rows.append((r['id'], len(ex.get('avoid', [])), ' | '.join(miss)[:200], ' | '.join(fp)[:200]))
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(rep, 'w', encoding='utf-8') as f:
        f.write('id\tavoid_examples\tavoid_missed_by_regex\tok_flagged_by_regex\n')
        for row in rows:
            f.write('\t'.join(str(x) for x in row) + '\n')
    print(f'{n} rules with PDF examples; {len(rows)} regex rules with misses or false positives')


if __name__ == '__main__':
    main()
