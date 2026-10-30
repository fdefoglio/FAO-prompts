#!/usr/bin/env python3
"""Merge register parts into fao_style_register.json and fao_recommended_words.json.

Usage: python3 merge_register.py STYLEGUIDE.md PARTS_DIR OVERRIDES.json OUT_DIR
Writes:
  OUT_DIR/fao_style_register.json   header, overrides, rules (§1–§12), coverage map
  OUT_DIR/fao_recommended_words.json Appendix 2 entries (same rule schema)
  OUT_DIR/register_review.csv        one row per rule, for human review
Checks that every heading in the guide's body (§1–§12, Appendix 2) has a coverage entry.
"""
import csv
import datetime
import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter

NOT_APPLICABLE = {
    'Appendix 1': 'Links to online resources; no rules.',
    'Appendix 3': 'Microsoft Word shortcuts; software how-to, no editorial rules.',
    'Appendix 4': 'Zotero installation; software how-to, no editorial rules.',
}


def main():
    guide_path, parts_dir, ov_path, out = sys.argv[1:5]
    raw = open(guide_path, 'rb').read()
    lines = raw.decode('utf-8').split('\n')
    sha = hashlib.sha256(raw).hexdigest()
    parts = sorted(glob.glob(os.path.join(parts_dir, '*.json')))
    rules, words, sections, ise = [], [], [], []
    for p in parts:
        d = json.load(open(p, encoding='utf-8'))
        if d['part'].startswith('W_'):
            words.extend(d['rules'])
            ise = d.get('ise_exceptions', [])
        else:
            rules.extend(d['rules'])
        sections.extend(d.get('sections', []))
    overrides = json.load(open(ov_path, encoding='utf-8'))
    for o in overrides['overrides']:
        rx = re.compile(o['match'], re.I) if o.get('match') else None
        if 'affects_explicit' in o:
            o['affects'] = o.pop('affects_explicit')
            continue
        o['affects'] = [r['id'] for r in rules + words
                        if any(r['section'] == s or r['section'].startswith(s + '.') for s in o.get('sections', []))
                        and (rx is None or rx.search(r['quote'] + ' ' + r['rule']))]

    # headings in the guide body that need a coverage entry
    heads = []
    in_body = False
    for i, l in enumerate(lines, 1):
        m = re.match(r'^(#{1,4})\s+(.*)$', l)
        if not m:
            continue
        title = m.group(2).strip()
        if title.startswith('1 ABOUT'):
            in_body = True
        if not in_body:
            continue
        num = re.match(r'^((?:\d+\.)*\d+|Appendix \d)', title)
        heads.append((i, num.group(1) if num else title, title))
    covered = {s['section'] for s in sections}
    missing = [(i, n, t) for i, n, t in heads if n not in covered and n not in NOT_APPLICABLE]
    for n, why in NOT_APPLICABLE.items():
        ln = next((i for i, nn, t in heads if nn == n), None)
        sections.append(dict(section=n, title=n, lines=[ln, ln], rule_ids=[], status='not_applicable', note=why))

    def method_counts(rs):
        return dict(Counter(r['check']['method'] for r in rs))

    rel = Counter(r['relevance'] for r in rules)
    header = dict(
        register='FAOSTYLE rule register',
        register_version='1.0',
        compiled=datetime.date.today().isoformat(),
        source=dict(file=os.path.basename(guide_path), edition='FAOSTYLE, Publishing at FAO — English, revised November 2024 (CB8081EN)',
                    sha256=sha, lines=len(lines),
                    master='https://github.com/fdefoglio/FAO_part2_LTJ/blob/main/fao_styleguide.md'),
        companion_files=dict(recommended_words='fao_recommended_words.json',
                             nocs='FAO-prompts/nocs/nocsDataExport_*.csv (official NOCS export; live source for country names)'),
        precedence=overrides['precedence'],
        counts=dict(rules=len(rules), recommended_words=len(words),
                    by_relevance=dict(rel), by_method=method_counts(rules),
                    by_action=dict(Counter(r['action'] for r in rules)),
                    by_kind=dict(Counter(r['kind'] for r in rules))),
        ise_exceptions_from_appendix2=ise,
        coverage_gaps=[dict(line=i, section=n, title=t) for i, n, t in missing],
    )
    byid = {r['id']: r for r in rules + words}
    for keep, dup, note in overrides.get('duplicates', []):
        byid[dup]['duplicate_of'] = keep
        byid[keep].setdefault('see_also', []).append(dup)
        if note:
            byid[dup]['check']['notes'] = (byid[dup]['check'].get('notes', '') + ' Duplicate: report under ' + keep + '. ' + note).strip()
    header['open_questions'] = len(overrides.get('open_questions', []))
    reg = dict(header=header, overrides=overrides['overrides'], open_questions=overrides.get('open_questions', []), rules=rules,
               coverage=sorted(sections, key=lambda s: (s['lines'][0] or 0)))
    os.makedirs(out, exist_ok=True)
    json.dump(reg, open(os.path.join(out, 'fao_style_register.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(dict(header=dict(source_sha256=sha, section='Appendix 2', count=len(words),
                               ise_exceptions=ise), rules=words),
              open(os.path.join(out, 'fao_recommended_words.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(os.path.join(out, 'register_review.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(['ID', 'Section', 'Lines', 'Kind', 'Relevance', 'Check', 'Module/pattern', 'Action', 'Rule', 'Quote', 'Override'])
        ov_by = {}
        for o in overrides['overrides']:
            for rid in o.get('affects', []):
                ov_by.setdefault(rid, []).append(o['id'])
        for r in rules + words:
            ch = r['check']
            w.writerow([r['id'], r['section'], f"{r['lines'][0]}–{r['lines'][-1]}", r['kind'], r['relevance'], ch['method'],
                        ch.get('module') or ch.get('pattern') or '; '.join(f'{a} → {b}' for a, b in ch.get('pairs', [])),
                        r['action'], r['rule'], r['quote'], ', '.join(ov_by.get(r['id'], []))])
    print(json.dumps(header['counts'], indent=1))
    print('coverage gaps:', len(missing))
    for x in missing:
        print('  ', x)


if __name__ == '__main__':
    main()
