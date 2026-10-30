#!/usr/bin/env python3
"""Parse FAOSTYLE Appendix 2 (List of recommended words) into register entries.

Usage: python3 parse_appendix2.py fao_styleguide.md OUT.json
Each entry keeps its verbatim quote and line numbers. Entry types:
  not        "X not Y"              -> wordlist Y -> X, Apply (mandatory)
  avoid      "X avoid; use Z"       -> wordlist X -> Z, Verify (preference)
  preferred  "X preferred to Y"     -> wordlist Y -> X, Verify (preference)
  case       "... not capitalized / lower case / not Alfalfa" -> regex on the capitalized form, Apply
  italic     "... not italicized"   -> module formatting, Verify
  prefix     "agro- compounds ..."  -> module prefix_compound, Verify
  pos        "(n.) ... (v.)"        -> module compound_form (part-of-speech dependent), Verify
  usage      meaning notes (cf., twice a year, best to specify) -> agent, Info
  form       plain headword(s)      -> module compound_form (closed/hyphen/open variants), Verify
"""
import json
import re
import sys

START, END = '# Appendix 2 LIST OF RECOMMENDED WORDS', '# Appendix 3'


def _key(w):
    return re.sub(r'[^a-z]', '', w.lower())


def logical_lines(lines, first):
    """Join PDF-wrapped lines. Returns list of (text, first_line_no, last_line_no).

    The list is alphabetical under single-letter section lines. A physical line starts a
    new entry unless (a) the previous entry has an unclosed parenthesis, or (b) the
    previous physical line was wrapped (80+ characters) and this line does not look like
    the next headword: it starts with a different letter from the current section, or it
    sorts before the previous headword.
    """
    out, last_len, letter = [], 0, 'a'
    for k, raw in enumerate(lines):
        no = first + k
        s = raw.rstrip()
        if re.fullmatch(r'[A-Z]', s.strip()):
            letter = s.strip().lower()
            continue
        if not s.strip() or s.startswith('<!--'):
            continue
        if out:
            prev = out[-1][0]
            first_word = _key(s.strip().split()[0])
            prev_head = _key(prev.split()[0])
            looks_new = bool(first_word) and first_word[0] == letter and first_word >= prev_head[:len(first_word)]
            open_end = re.search(r'(,|–|\be\.g\.|\b(?:can|not|the|a|an|of|to|and|or|but|in|for|is|be|as|with|by|on|when|which|that))$', prev)
            fragment = re.match(r'^[a-z]{1,2}\b', s.strip()) and s.strip().split()[0] not in ('a', 'an')
            hyph_end = bool(re.search(r'[a-z]-$', prev)) and last_len >= 70
            cont = prev.count('(') > prev.count(')') or (last_len >= 80 and (not looks_new or open_end or fragment)) \
                or (open_end and not looks_new) or (open_end and last_len >= 75) or hyph_end
            if cont:
                joiner = '' if hyph_end else ' '
                out[-1] = (prev + joiner + s.strip(), out[-1][1], no)
                last_len = len(s)
                continue
        out.append((s.strip(), no, no))
        last_len = len(s)
    return out


def split_forms(s):
    s = re.sub(r'\s*\([^)]*\)?', '', s)                      # (n.), (abbrev. kg), (mode of payment)
    return [x.strip(' .;') for x in re.split(r',\s*|\s+or\s+', s) if x.strip(' .;')]


def closest(bad, goods):
    import difflib
    return max(goods, key=lambda g: difflib.SequenceMatcher(None, bad.lower(), g.lower()).ratio())


# Bad forms that are also ordinary words in another sense: report, never auto-apply.
CONTEXT_DEPENDENT = {'check (payment)', 'spelt', 'lac', 'tire', 'comprised of', 'accommodations', 'glasshouse', 'fall',
                     'firewood', 'multinational', 'societal costs', 'healthcare services', 'inquire', 'inquiry'}
# Entries that look like "X not Y" but are usage notes.
USAGE_HEADS = {'stationary', 'afforestation', 'ensure', 'historic, historical', 'impact', 'religions, religious groups',
               'Jr', 'transnational', 'assist + in + gerund or noun'}


def classify(text):
    t = text
    low = t.lower()
    if re.match(r'^-?[a-z]+-\s+compounds|^-\w+ compounds', t) or re.match(r'^[a-z]+- compounds', t):
        return 'prefix'
    if 'not italicized' in low or 'not in italics' in low:
        return 'italic'
    if 'not capitalized' in low or 'lower case' in low or re.search(r' not [A-Z][a-z]', t) and t.split(' not ')[0].strip().lower() == t.split(' not ')[1].strip().split(';')[0].strip().lower():
        return 'case'
    if re.search(r'\bavoid\b.*\buse\b', low):
        return 'avoid'
    if re.match(r'^[^,;()]{2,40}?\s+use\s+[^;]{2,60}$', t) and ' not ' not in t:
        return 'use'
    if ' preferred to ' in t:
        return 'preferred'
    if re.search(r'\snot\s', t):
        return 'not'
    if re.search(r'\((n|v|adj|adv)\.', t):
        return 'pos'
    if re.search(r'\bcf\.|\btwice\b|\bevery\b|best to specify|follow author|\bmeaning\b|period of|\bone thousand\b|be consistent|\buse\b', low):
        return 'usage'
    chunks = [c for c in re.split(r',\s*', re.sub(r'\([^)]*\)', '', t)) if c.strip()]
    if any(len(c.split()) > 3 for c in chunks):
        return 'usage'
    return 'form'


def main():
    L = open(sys.argv[1], encoding='utf-8').read().split('\n')
    a = next(i for i, l in enumerate(L) if l.startswith(START))
    b = next(i for i, l in enumerate(L) if l.startswith(END))
    body = L[a + 2:b]                       # skip heading and the "see 4 Spelling" line
    first = a + 3                           # 1-based line number of body[0]
    rules, n = [], 0
    ise_words, seen_bad, rules_by_id = [], {}, {}
    for text, l1, l2 in logical_lines(body, first):
        n += 1
        kind = classify(text)
        if kind == 'not' and any(text.startswith(h + ' ') for h in USAGE_HEADS):
            kind = 'usage'
        rid = f'WRD-A2-{n:04d}'
        quote = ' '.join(L[i - 1].strip() for i in range(l1, l2 + 1) if L[i - 1].strip() and not L[i - 1].startswith('<!--'))
        head = re.split(r'\s(?:not|avoid|preferred to|\(|pl\.|see|cf\.|but)\b', text)[0].strip(' ,;')
        entry = dict(id=rid, section='Appendix 2', section_title='LIST OF RECOMMENDED WORDS', lines=[l1, l2],
                     quote=quote, kind='preference', scope=['body', 'heading', 'caption', 'table', 'footnote'],
                     relevance='manuscript', entry_type=kind, headword=head)
        for w in re.findall(r"\b([a-z]+is)(?:e|es|ed|ing)\b", text):
            if not w.endswith(('cris', 'ys')):
                ise_words.append(w + 'e')
        if kind == 'not':
            left, right = text.split(' not ', 1)
            right = re.split(r'[;(]|\be\.g\.|\bbut\b', right)[0]
            left = left.strip(' ,')
            if re.match(r'^(\w+) the \1$', left):                 # "Sahara the Sahara"
                left = left.split(' ', 1)[1]
            good, bad = split_forms(left), split_forms(right)
            pairs = []
            if len(left.split()) > 5 or len(right.split()) > 6 or re.search(r'\b(interchangeable|preceded|followed|used as|to be used)\b', right):
                bad = []
            for bd in bad:
                gd = closest(bd, good)
                if bd and gd and bd.lower() != gd.lower():
                    pairs.append([bd, gd])
                    if bd.endswith('man') and gd.endswith('er'):        # fisherman -> fisher: plural too
                        pairs.append([bd[:-3] + 'men', gd + 's'])
            entry.update(rule=f'Use {", ".join(good)}, not {", ".join(bad)}.', kind='mandatory',
                         check=dict(method='wordlist', pairs=pairs,
                                    notes='Explicit "not" form in Appendix 2. Leave quotations and published titles alone.'),
                         action='Verify' if any(b.lower() in CONTEXT_DEPENDENT for b, _ in pairs) else 'Apply')
            if not pairs:
                entry.update(check=dict(method='agent', notes='Could not pair forms automatically; read the quote.'), action='Verify')
        elif kind == 'use':
            m = re.match(r'^(.*?)\s+use\s+(.*)$', text)
            bad, good = m.group(1).strip(), m.group(2).strip(' .')
            simple = len(good.split()) <= 3 and not re.search(r'[(,]', good) and not good.startswith('for ') and ' or ' not in bad
            entry.update(rule=f'Use {good} instead of {bad}.',
                         check=dict(method='wordlist', pairs=[[bad, good]], notes='Guide says use the alternative; editor confirms context.')
                         if simple else dict(method='agent', notes='Replacement depends on context; read the quote.'),
                         action='Verify')
        elif kind == 'avoid':
            m = re.match(r'(.*?)\s+avoid;?\s*use\s+(.*)$', text)
            bad, good = (m.group(1).strip(), re.split(r'\s[–(]|;|,', m.group(2))[0].strip(' .')) if m else (head, '')
            entry.update(rule=f'Avoid {bad}; use {good}.', check=dict(method='wordlist', pairs=[[bad, good]] if good else [],
                         notes='Guide says avoid: editor confirms context.'), action='Verify')
            if not good:
                entry['check'] = dict(method='agent', notes='Avoid-entry without a replacement; read the quote.')
        elif kind == 'preferred':
            good, bad = text.split(' preferred to ', 1)
            entry.update(rule=f'Prefer {good.strip()} to {bad.strip()}.',
                         check=dict(method='wordlist', pairs=[[bad.strip(' .'), good.strip()]], notes='Preference: editor confirms.'),
                         action='Verify')
        elif kind == 'case':
            m = re.search(r' not ([A-Z][\w ]+?)(?:;|$)', text)
            simple = len(head.split()) <= 3 and not re.search(r'lower case (when|for)|upper case', text)
            if m:
                pat, note = r'\b' + re.escape(m.group(1).strip()) + r'\b', 'Flags the capitalized form the guide rejects.'
            elif simple:
                pat = r'(?<![.!?]\s)(?<!^)\b' + re.escape(head[:1].upper() + head[1:]) + r'\b'
                note = 'Flags the capitalized form mid-sentence; headings in title case are false positives.'
            else:
                pat = None
            entry.update(rule=f'Write "{head}" as shown (capitalization).', kind='mandatory', action='Verify',
                         check=dict(method='regex', pattern=pat, notes=note) if pat else
                         dict(method='agent', notes='Capitalization depends on context; read the quote.'))
        elif kind == 'italic':
            entry.update(rule=f'Do not italicize "{head}".', kind='mandatory',
                         check=dict(method='module', module='formatting', notes='Needs run formatting (DOCX) or markdown emphasis.'),
                         action='Apply')
        elif kind == 'prefix':
            pre = re.match(r'^(-?[a-z]+-?)', text).group(1)
            entry.update(rule=f'Follow the guide for {pre} compounds (closed up / hyphenated as stated).',
                         check=dict(method='module', module='prefix_compound', notes='Exceptions are listed in the quote.'),
                         action='Verify')
        elif kind == 'pos':
            entry.update(rule=f'Use the form for each part of speech as listed: {text}',
                         check=dict(method='module', module='compound_form',
                                    notes='Part-of-speech dependent (e.g. breakdown (n.), break down (v.)): flag other spellings, editor decides.'),
                         action='Verify')
        elif kind == 'usage':
            entry.update(rule=f'Usage note: {text}', kind='guidance', check=dict(method='agent', notes='Meaning-dependent.'),
                         action='Info')
        else:
            entry.update(rule=f'Spell as listed: {text}',
                         check=dict(method='module', module='compound_form',
                                    notes='Flag hyphenated, spaced or closed variants that join to a listed form.'),
                         action='Verify')
        for b, g in entry['check'].get('pairs', []):
            key = b.lower()
            if key in seen_bad and entry['entry_type'] != 'not':
                entry['duplicate_of'] = seen_bad[key]
            elif key in seen_bad and rules_by_id[seen_bad[key]]['entry_type'] != 'not':
                rules_by_id[seen_bad[key]]['duplicate_of'] = rid
                seen_bad[key] = rid
            else:
                seen_bad.setdefault(key, rid)
        if text.startswith('cheque not check'):
            entry['check'] = dict(method='agent', notes='Only the payment sense of check; calibration showed the verb "check" matched.')
            entry['action'] = 'Verify'
        if text.startswith('transnational '):
            entry['check'] = dict(method='wordlist', pairs=[['multinational', 'transnational']],
                                  notes='Only for corporations operating across borders; editor confirms.')
            entry['action'] = 'Verify'
        rules.append(entry)
        rules_by_id[rid] = entry
    ise_words += ['enterprise', 'raise', 'practise', 'advise', 'clockwise', 'otherwise', 'likewise']
    out = dict(part='W_appendix2', lines_covered=[a + 1, b], rules=rules,
               sections=[dict(section='Appendix 2', title='LIST OF RECOMMENDED WORDS', lines=[a + 1, b],
                              rule_ids=[r['id'] for r in rules], status='rules', note='')],
               ise_exceptions=sorted(set(ise_words)))
    json.dump(out, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    from collections import Counter
    print(len(rules), Counter(r['entry_type'] for r in rules))
    print('-ise words listed in Appendix 2:', sorted(set(ise_words)))


if __name__ == '__main__':
    main()
