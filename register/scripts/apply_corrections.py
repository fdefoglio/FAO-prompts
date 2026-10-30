#!/usr/bin/env python3
"""Apply audited corrections to the merged register (in place).

Usage: python3 apply_corrections.py MERGED_DIR corrections.json
- patches: field replacements per rule ID ('check.x' patches a key inside check)
- dedupes scope lists
- marks rules needing non-breaking spaces or run formatting (check.requires)
- adds extra duplicate links and the execution policy to the header
- re-validates every patched regex (must compile; printed examples must still behave)
"""
import json
import os
import re
import sys


def main():
    d, cpath = sys.argv[1], sys.argv[2]
    reg_p = os.path.join(d, 'fao_style_register.json')
    words_p = os.path.join(d, 'fao_recommended_words.json')
    reg = json.load(open(reg_p, encoding='utf-8'))
    words = json.load(open(words_p, encoding='utf-8'))
    corr = json.load(open(cpath, encoding='utf-8'))
    byid = {r['id']: r for r in reg['rules'] + words['rules']}
    missing, errors = [], []
    for rid, patch in corr['patches'].items():
        r = byid.get(rid)
        if r is None:
            missing.append(rid)
            continue
        for k, v in patch.items():
            if k.startswith('check.'):
                r['check'][k[6:]] = v
            else:
                r[k] = v
        r.setdefault('audit', []).append('corrected after independent audit 2026-10-30')
        ch = r['check']
        if ch.get('method') == 'regex':
            try:
                rx = re.compile(ch['pattern'])
                for bad in (r.get('examples') or {}).get('incorrect', []) or []:
                    if not rx.search(bad):
                        errors.append(f'{rid}: patched regex misses example "{bad}"')
            except re.error as ex:
                errors.append(f'{rid}: patched regex does not compile: {ex}')
    for r in reg['rules'] + words['rules']:
        sc = []
        for s in r.get('scope', []):
            if s not in sc:
                sc.append(s)
        r['scope'] = sc
        mod = r['check'].get('module')
        if mod in corr.get('requires_by_module', {}):
            r['check'].setdefault('requires', corr['requires_by_module'][mod])
    for keep, dup, note in corr.get('duplicates_extra', []):
        byid[dup]['duplicate_of'] = keep
        byid[keep].setdefault('see_also', [])
        if dup not in byid[keep]['see_also']:
            byid[keep]['see_also'].append(dup)
    reg['header']['execution'] = corr['execution']
    reg['header']['audit'] = dict(date='2026-10-30', patched_rules=len(corr['patches']) - len(missing),
                                  note='Independent audit: fidelity sample 6/60 defects, regex noise, Appendix 2 pairing; all corrected.')
    reg['header']['ise_exceptions'] = sorted(set(words['header'].get('ise_exceptions', [])) | set(
        'promise expertise franchise merchandise surprise compromise exercise advertise supervise revise precise concise '
        'wise otherwise likewise disguise comprise arise demise premise paradise enterprise apprise chastise devise excise '
        'incise improvise noise poise praise raise'.split()))
    words['header']['ise_exceptions'] = reg['header']['ise_exceptions']
    reg['header'].pop('ise_exceptions_from_appendix2', None)
    json.dump(reg, open(reg_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(words, open(words_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'patched {len(corr["patches"]) - len(missing)} rules; missing IDs: {missing}; regex problems: {errors}')
    sys.exit(1 if missing or errors else 0)


if __name__ == '__main__':
    main()
