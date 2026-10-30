#!/usr/bin/env python3
"""Validate a FAOSTYLE register part (or the merged register) against fao_styleguide.md.

Usage: python3 validate_part.py STYLEGUIDE.md PART.json [PART2.json ...]
Checks: required fields, enums, unique IDs, quotes verbatim at the cited lines (whitespace-normalized,
±3 lines tolerance), regex patterns compile, examples: incorrect matched / correct not matched by regex.
Exit 0 = clean, 1 = errors.
"""
import json
import re
import sys

KINDS = {'mandatory', 'preference', 'guidance'}
METHODS = {'regex', 'wordlist', 'module', 'agent', 'manual'}
ACTIONS = {'Apply', 'Verify', 'Author', 'Info'}
RELEV = {'manuscript', 'production', 'reference'}
SCOPES = {'body', 'heading', 'caption', 'table', 'figure', 'box', 'footnote', 'reference', 'front_matter', 'title', 'all'}
REQ = ['id', 'section', 'section_title', 'lines', 'quote', 'rule', 'kind', 'scope', 'check', 'action', 'relevance']


def norm(s):
    s = s.replace(' ', ' ').replace(' ', ' ').replace(' ', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def main():
    guide = open(sys.argv[1], encoding='utf-8').read().split('\n')
    errors, warns, ids, n = [], [], {}, 0
    for path in sys.argv[2:]:
        data = json.load(open(path, encoding='utf-8'))
        rules = data['rules'] if isinstance(data, dict) else data
        for r in rules:
            n += 1
            rid = r.get('id', f'<no id #{n}>')
            for k in REQ:
                if k not in r:
                    errors.append(f'{rid}: missing {k}')
            if rid in ids:
                errors.append(f'{rid}: duplicate id (also in {ids[rid]})')
            ids[rid] = path
            if r.get('kind') not in KINDS:
                errors.append(f'{rid}: bad kind {r.get("kind")}')
            if r.get('action') not in ACTIONS:
                errors.append(f'{rid}: bad action {r.get("action")}')
            if r.get('relevance') not in RELEV:
                errors.append(f'{rid}: bad relevance {r.get("relevance")}')
            bad_sc = set(r.get('scope', [])) - SCOPES
            if bad_sc:
                errors.append(f'{rid}: bad scope {bad_sc}')
            ch = r.get('check', {})
            if ch.get('method') not in METHODS:
                errors.append(f'{rid}: bad check.method {ch.get("method")}')
            # quote check
            ln = r.get('lines') or [0, 0]
            try:
                a, b = int(ln[0]), int(ln[-1])
            except Exception:
                errors.append(f'{rid}: bad lines {ln}')
                continue
            win = norm(' '.join(guide[max(0, a - 4):min(len(guide), b + 3)]))
            q = norm(r.get('quote', ''))
            if not q:
                errors.append(f'{rid}: empty quote')
            elif q not in win:
                # try whole-file to report the right lines
                whole = norm(' '.join(guide))
                where = 'elsewhere in file' if q in whole else 'NOT in file'
                errors.append(f'{rid}: quote not at lines {a}-{b} ({where}): "{q[:80]}"')
            for ex in r.get('exceptions', []) or []:
                eq = norm(ex.get('quote', ''))
                el = ex.get('lines') or ln
                ew = norm(' '.join(guide[max(0, int(el[0]) - 4):min(len(guide), int(el[-1]) + 3)]))
                if eq and eq not in ew:
                    errors.append(f'{rid}: exception quote not at lines {el}: "{eq[:70]}"')
            # regex checks
            if ch.get('method') == 'regex':
                pat = ch.get('pattern')
                try:
                    rx = re.compile(pat)
                except Exception as ex:
                    errors.append(f'{rid}: regex does not compile: {ex}')
                    continue
                exs = r.get('examples') or {}
                for bad in exs.get('incorrect', []) or []:
                    if not rx.search(bad):
                        warns.append(f'{rid}: regex misses incorrect example "{bad}"')
                for good in exs.get('correct', []) or []:
                    if rx.search(good):
                        warns.append(f'{rid}: regex flags correct example "{good}"')
            if ch.get('method') == 'wordlist' and not ch.get('pairs'):
                errors.append(f'{rid}: wordlist without pairs')
    for e in errors:
        print('ERROR', e)
    for w in warns:
        print('WARN ', w)
    print(f'{n} rules, {len(errors)} errors, {len(warns)} warnings')
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
