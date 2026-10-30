#!/usr/bin/env python3
"""FAOSTYLE preflight: run the rule register over a manuscript.

Usage:
  python preflight.py MANUSCRIPT [--register fao_style_register.json] [--words fao_recommended_words.json]
                      [--nocs nocsDataExport.csv] [--nocs-script nocs_check.py] [--out-dir DIR]

MANUSCRIPT: labelled markdown from editor_tool --export (preferred: positions are [N] labels and
table cells [T…]; footnotes [^N]) or a .docx (paragraph numbers as positions).

Outputs (in --out-dir):
  <stem>_preflight_findings.csv   one row per hit: ID, Label, Context, Rule, Section, Action, Found,
                                  Suggested, Rule text, Snippet
  <stem>_preflight_receipt.md     data sources and checksums, counts per rule, coverage of the guide
                                  (scripted / agent / manual / not run), calibration status
  <stem>_agent_checklist.md       the rules that need reading with judgement, grouped by section,
                                  with the guide's wording, for the editor or the agent pass

Every finding is reported as Verify while the register is in its calibration phase
(header.execution.apply_policy); `Rule action` keeps the register's own action.
Exit code: 0 = ran (findings or not), 2 = setup error. A run never passes silently.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict

VERSION = 'preflight.py 0.1 (2026-10-30)'
LABEL = re.compile(r'^\[(\d+|T[\d.]+|\^\d+)\](?::)?\s?(.*)$')
CAPTION = re.compile(r'^\s*\**\s*(Figure|Table|Box|Map|Plate)\s+[A-Z]?\d', re.I)
REF_HEAD = re.compile(r'^\s*#*\s*(\d+\.?\s*)?(References|Bibliography|Further reading|Notes|(?:Principal |Key |Main )?Sources(?: and references)?|Works cited|Literature cited)\s*$', re.I)
MAIN_START = re.compile(r'^\s*#+\s*(Section\s+1\b|1\.?\s+[A-Z]|Introduction\b|Chapter\s+1\b)', re.I)


# ---------------------------------------------------------------- reading
def read_labelled_md(path):
    paras = []
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\r\n')
        m = LABEL.match(line)
        if not m:
            continue
        label, text = m.group(1), m.group(2)
        if text.strip() in ('[Empty Paragraph]', '') or text.startswith('[SPECIAL]'):
            continue
        paras.append(dict(label=label, text=text))
    return paras


def read_docx(path):
    import docx
    from docx.oxml.ns import qn
    d = docx.Document(path)
    paras, n = [], 0
    for p in d.element.body.iter(qn('w:p')):
        t = ''.join(x.text or '' for x in p.iter(qn('w:t')))
        st = p.find(qn('w:pPr') + '/' + qn('w:pStyle'))
        style = st.get(qn('w:val')) if st is not None else ''
        in_tbl = any(a.tag == qn('w:tc') for a in p.iterancestors())
        lvl = re.search(r'(\d)', style) if re.search(r'heading', style, re.I) else None
        if lvl:
            t = '#' * int(lvl.group(1)) + ' ' + t
        if t.strip():
            paras.append(dict(label=(f'T{n}' if in_tbl else str(n)), text=t))
        n += 1
    return paras


def mark_boxes(paras):
    cur, boxed = None, False
    for p in paras:
        m = re.match(r'^T(\d+)\.', p['label'])
        if not m:
            cur = None
            continue
        if m.group(1) != cur:
            cur = m.group(1)
            boxed = bool(re.match(r'^\W*(BOX|Box|CASE|Case)\b', p['text']))
        p['in_box'] = boxed


def classify(paras):
    mark_boxes(paras)
    in_refs, main = False, False
    for p in paras:
        t, lab = p['text'], p['label']
        is_head = t.lstrip().startswith('#')
        if is_head and MAIN_START.match(t):
            main = True
        if REF_HEAD.match(t.lstrip('# ')) or REF_HEAD.match(t):
            in_refs = True
            p['kind'] = 'heading'
            continue
        if lab.startswith('^'):
            p['kind'] = 'footnote'
        elif lab.startswith('T'):
            # long cell text is running text in a box or case example, not tabular data
            p['kind'] = 'box' if p.get('in_box') else 'table'
        elif in_refs and not is_head:
            p['kind'] = 'reference'
        elif is_head:
            p['kind'] = 'heading'
            in_refs = False if not REF_HEAD.match(t.lstrip('# ')) else in_refs
        elif CAPTION.match(t):
            p['kind'] = 'caption'
        elif not main and re.match(r'^\s*[A-Z][A-Za-z0-9&’\'.+-]{1,}\s*[:–]\s', t) and len(t) < 160:
            p['kind'] = 'list_entry'             # acronym or glossary list line
        elif not main:
            p['kind'] = 'front_matter'
        else:
            p['kind'] = 'body'


def masked(text, quotes=True, notes=True):
    """Blank out Word-field tokens, URLs and emails; optionally quotations (FAOSTYLE is not applied to quoted
    matter) and footnote markers (replaced by a non-space placeholder, so they never create double spaces).
    Offsets are kept."""
    def blank(m):
        return ' ' * len(m.group(0))
    t = re.sub(r'⟦[^⟧]*⟧', blank, text)
    t = re.sub(r'https?://\S+|www\.\S+|\S+@\S+\.\w+', blank, t)
    if quotes:
        t = re.sub(r'(?<=“)[^”]{3,}(?=”)|(?<=")[^"\n]{3,}(?=")', blank, t)
    if notes:
        t = re.sub(r'\[\^\d+\]', lambda m: '\u00a4' * len(m.group(0)), t)
    return t


# Rules about punctuation around quotations, ellipses or note indicators see the raw text.
RAW_QUOTES = ('PUN-5_5', 'PUN-5_10', 'REF-12_3_3')
RAW_NOTES = ('NOT-11',)


# ---------------------------------------------------------------- rule engines
def scope_ok(rule, kind):
    sc = set(rule.get('scope', []))
    if 'all' in sc or kind in sc:
        return True
    if kind == 'front_matter' and 'body' in sc:
        return True
    if kind == 'list_entry' and 'front_matter' in sc:
        return True
    if kind == 'box' and 'body' in sc:
        return True
    if kind == 'table' and ({'figure', 'box'} & sc):
        return True
    return False


def run_regex(rule, paras, out):
    try:
        rx = re.compile(rule['check']['pattern'])
    except (re.error, TypeError):
        return 'error'
    for p in paras:
        if not scope_ok(rule, p['kind']):
            continue
        rid = rule['id']
        text = (masked(p['text'], quotes=not rid.startswith(RAW_QUOTES), notes=not rid.startswith(RAW_NOTES))
                if p['kind'] != 'reference' else p['text'])
        if p['kind'] == 'heading' and not rid.startswith('PUN-5_7'):
            text = re.sub(r'^#+\s*', lambda m: ' ' * len(m.group(0)), text)
        letters = re.sub(r'[^A-Za-z]', '', text)
        if rule['id'].startswith('ABB') and letters and sum(c.isupper() for c in letters) / len(letters) > 0.6:
            continue                     # title or label set in capitals (a design choice, not abbreviations)
        for m in rx.finditer(text):
            if not m.group(0).strip():
                continue
            found = p['text'][m.start():m.end()]
            if rule['check'].get('case_policy') == 'lower_or_sentence_start' and found[:1].isupper() \
                    and not re.search(r'(^|[.!?:]\s+|\*\*\s*|^\W*)$', text[:m.start()]):
                continue                     # capitalized mid-sentence: proper name (e.g. Center for ...)
            if rid == 'ABB-7-014' and KNOWN_ABBR is not None and found.rstrip('s’') not in KNOWN_ABBR:
                continue                     # a capitalized word (STEP, CASE), not an abbreviation
            out.append((p, m.start(), m.end(), found, ''))
    return 'ran'


KNOWN_ABBR = None


def wordlist_rx(bad):
    flags = 0 if any(c.isupper() for c in bad) else re.I
    return re.compile(r'(?<![\w-])' + re.escape(bad).replace(r'\ ', r'[\s-]') + r'(?![\w-])', flags)


def run_wordlist(rule, paras, out):
    pairs = rule['check'].get('pairs') or []
    for bad, good in pairs:
        if not bad or len(bad) < 2:
            continue
        rx = wordlist_rx(bad)
        for p in paras:
            if not scope_ok(rule, p['kind']) or p['kind'] == 'reference':
                continue
            text = masked(p['text'])
            for m in rx.finditer(text):
                found = text[m.start():m.end()]
                if not any(c.isupper() for c in bad) and found[:1].isupper() and not re.search(r'(^|[.!?:]\s+|^\W*)$', text[:m.start()]):
                    continue                     # capitalized mid-sentence: part of a proper name
                out.append((p, m.start(), m.end(), p['text'][m.start():m.end()], good))
    return 'ran'


def compound_index(words):
    """Map normalized compounds (letters only) to the listed form, from Appendix 2 'form'/'pos' entries."""
    idx = {}
    for r in words:
        if r.get('entry_type') not in ('form', 'pos') or r.get('duplicate_of'):
            continue
        text = re.sub(r'\([^)]*\)', '', r['quote'])
        text = re.split(r'\b(?:but|see|e\.g\.|cf\.|not)\b', text)[0]
        forms = [f.strip(' .;') for f in re.split(r',\s*', text)]
        forms = [f for f in forms if f and re.fullmatch(r"[a-z][a-z' -]*[a-z]", f)]
        allowed = {f.lower() for f in forms}
        for form in forms:
            if len(form) < 5 or (' ' not in form and '-' not in form and len(form) < 7):
                continue
            for k2, f2 in ((re.sub(r'[\s-]', '', form), form), (re.sub(r'[\s-]', '', form) + 's', form + 's')):
                al = allowed | {x + 's' for x in allowed}
                if k2 in idx:
                    idx[k2][2].update(al)
                else:
                    idx[k2] = (f2, r, set(al))
    return idx


def run_compounds(words, paras, out_by_rule):
    idx = compound_index(words)
    tok = re.compile(r"[A-Za-z]+(?:[-\s][A-Za-z]+)?")
    pair = re.compile(r"(?<![\w-])([a-z]+)([\s-])([a-z]+)(?![\w-])")
    single = re.compile(r"(?<![\w-])([a-z]{7,})(?![\w-])")
    for p in paras:
        if p['kind'] in ('reference',):
            continue
        text = masked(p['text'])
        for rx in (pair, single):
            for m in rx.finditer(text):
                found = m.group(0)
                key = re.sub(r'[\s-]', '', found.lower())
                if key in idx:
                    form, r, allowed = idx[key]
                    if found.lower() not in allowed and re.sub('-', ' ', found.lower()) not in allowed:
                        out_by_rule[r['id']].append((p, m.start(), m.end(), p['text'][m.start():m.end()], form))
    return 'ran'


ACR = re.compile(r'(?<![\w-])([A-Z][A-Z0-9&]{1,}[a-z]?s?)(?![\w-])')
ACR_SKIP = {'FAO', 'COVID-19', 'UN', 'I', 'II', 'III', 'IV', 'V', 'VI', 'USD', 'EUR', 'A', 'AND', 'OF', 'THE', 'NB', 'OK', 'TV'}


def known_abbreviations(paras):
    known = set()
    for p in paras:
        for m in re.finditer(r'\(([A-Z][A-Za-z0-9&-]{1,}?)s?\)', p['text']):
            known.add(m.group(1))
        m = re.match(r'^\s*([A-Z][A-Za-z0-9&-]{1,}?)(?:’?s)?\s*[:–]\s', p['text'])
        if m and p['kind'] == 'list_entry':
            known.add(m.group(1))
    return known


def run_acronyms(paras, out, context_defined=frozenset()):
    """First use of an abbreviation in each chapter (## heading) and in each box must be preceded by its
    expansion (FAOSTYLE §7 with override OVR-01). Abbreviations defined in the main text (context_defined,
    from --context) need no redefinition in annexes and appendices."""
    known = known_abbreviations(paras) | set(context_defined)
    chapter, seen, defined = 'front', set(), set()
    box_saved, cur_box = None, None
    for p in paras:
        if p['kind'] in ('reference', 'footnote'):
            continue
        t = p['text']
        if p['kind'] == 'heading' and re.match(r'^##?\s', t):
            chapter, seen, defined = t, set(), set()
            continue
        bm = re.match(r'^T(\d+)\.', p['label'])
        if p['kind'] == 'box' and bm and bm.group(1) != cur_box:
            if box_saved is None:
                box_saved = (seen, defined)
            seen, defined, cur_box = set(), set(), bm.group(1)        # each box is its own scope
        elif p['kind'] != 'box' and box_saved is not None:
            seen, defined = box_saved
            box_saved, cur_box = None, None
        if re.match(r'^\W*(Sources?|Note|Notes)\s*:', t):
            continue                                          # source and note lines name corporate authors
        if p['kind'] == 'list_entry':
            continue                                          # acronym list line
        mt = masked(t)
        for m in re.finditer(r'\(([A-Z][A-Za-z0-9&-]{1,}s?)\)', mt):
            defined.add(m.group(1).rstrip('s'))
        for m in ACR.finditer(mt):
            a = m.group(1)
            base = a.rstrip('s')
            if base in ACR_SKIP or len(base) < 2 or base.isdigit() or not re.search(r'[A-Z].*[A-Z]', base) or base not in known:
                continue
            if base in context_defined:
                continue
            if base in seen:
                continue
            seen.add(base)
            if re.search(r'\([^()]*$', mt[:m.start()]) and re.match(r'[^()]*?\b(?:19|20)\d{2}', mt[m.end():]):
                continue                                      # corporate author in a citation: (FAO, 2021)
            before = mt[max(0, m.start() - 2):m.start()]
            if base not in defined and before != '(' and p['kind'] != 'heading':
                out.append((p, m.start(), m.end(), a, 'define at first use in this chapter'))


def run_consistency(paras, out_terms, out_glyph, out_serial):
    """Document-level consistency (SPL-4-008, WRT-3_1-010): the same term written in different
    capitalizations or with/without a hyphen, and mixed apostrophe glyphs. Reports the minority forms."""
    body = [p for p in paras if p['kind'] in ('body', 'box', 'front_matter', 'footnote', 'caption')]
    # capitalization variants of 1–4 word terms (not at sentence start)
    forms = defaultdict(Counter)
    where = defaultdict(list)
    word = r"[A-Za-z][A-Za-z’'-]*"
    for p in body:
        t = masked(p['text'])
        for n in (1, 2, 3, 4):
            for m in re.finditer(r'(?<![\w’-])' + r'\s'.join([word] * n) + r'(?![\w’-])', t):
                term = m.group(0)
                if n == 1 and len(term) < 5:
                    continue
                if re.search(r'(^|[.!?:•]\s*|^\W*)$', t[:m.start()]):
                    continue                              # sentence start: capital is positional
                if any(c.isupper() for c in term):
                    prev = re.search(r'([A-Za-z][\w’-]*)\W{0,3}(?:(?:of|and|on|for|the|to|in)\s+){0,2}$', t[:m.start()])
                    nxt = re.match(r'\W{0,3}(?:(?:of|and|on|for|the|to|in)\s+){0,2}([A-Za-z][\w’-]*)', t[m.end():])
                    if (prev and prev.group(1)[0].isupper()) or (nxt and nxt.group(1)[0].isupper()):
                        continue                          # part of a longer capitalized name
                    if re.search(r'\*\*[^*]*$', t[:m.start()]) or p['kind'] == 'caption':
                        continue                          # bold run-in label or caption
                key = term.lower()
                forms[key][term] += 1
                if len(where[(key, term)]) < 50:
                    where[(key, term)].append((p, m.start(), m.end()))
    reported = set()
    for key, c in forms.items():
        if len(c) < 2 or sum(c.values()) < 3:
            continue
        variants = [f for f in c if any(ch.isupper() for ch in f)]
        if not variants:
            continue
        top, topn = c.most_common(1)[0]
        for f, k in c.items():
            if f == top or k > topn / 2:
                continue
            if any(key in r or r in key for r in reported if len(r.split()) >= len(key.split())):
                continue
            reported.add(key)
            for p, a, b in where[(key, f)]:
                out_terms.append((p, a, b, f, f'{top} ({topn}x) vs {f} ({k}x): choose one form'))
    # hyphen / space / closed variants of the same compound (both spellings present)
    comp = defaultdict(Counter)
    cwhere = defaultdict(list)
    for p in body:
        t = masked(p['text'])
        for m in re.finditer(r'(?<![\w-])([a-z]{3,})(-| )([a-z]{3,})(?![\w-])', t):
            comp[m.group(1) + m.group(3)][m.group(0)] += 1
            cwhere[m.group(0)].append((p, m.start(), m.end()))
        for m in re.finditer(r'(?<![\w-])([a-z]{7,})(?![\w-])', t):
            if m.group(1) in comp:
                comp[m.group(1)][m.group(1)] += 1
                cwhere[m.group(1)].append((p, m.start(), m.end()))
    for key, c in comp.items():
        hy = [f for f in c if '-' in f]
        if len(c) < 2 or not hy or sum(c.values()) < 3:
            continue
        top, topn = c.most_common(1)[0]
        for f, k in c.items():
            if f != top and ('-' in f or '-' in top):
                for p, a, b in cwhere[f][:20]:
                    out_terms.append((p, a, b, f, f'{top} ({topn}x) vs {f} ({k}x): same form throughout (noun vs adjective may differ)'))
    # apostrophe glyphs
    glyphs = Counter()
    gwhere = defaultdict(list)
    for p in paras:
        if p['kind'] == 'reference':
            continue
        for m in re.finditer(r"(?<=[A-Za-z])(['’´`])(?=[a-z])|(?<=s)(['’´`])(?=\s)", p['text']):
            g = m.group(1) or m.group(2)
            glyphs[g] += 1
            gwhere[g].append((p, m.start(), m.end()))
    if len(glyphs) > 1:
        top = glyphs.most_common(1)[0][0]
        for g, k in glyphs.items():
            if g != top:
                p, a, b = gwhere[g][0]
                labels = ', '.join(dict.fromkeys(f"[{q['label']}]" for q, _, _ in gwhere[g]))
                out_glyph.append((p, a, b, g, f'{k} places use {g} instead of {top} ({glyphs[top]}x): {labels}'))


def run_double_l(words, paras, out_by_rule):
    """Appendix 2 lists single-l British forms (fulfil, enrol, instil): flag US double-l forms."""
    for r in words:
        if r.get('entry_type') != 'form':
            continue
        for f in re.findall(r'\b([a-z]+[aeiou]l)\b', r['quote'].split(' not ')[0]):
            if f.endswith('ll') or len(f) < 5:
                continue
            rx = re.compile(r'(?<![\w-])(' + f + r'l(?:s|ment|ments)?)(?![\w-])', re.I)
            for p in paras:
                if p['kind'] == 'reference':
                    continue
                for m in rx.finditer(masked(p['text'])):
                    out_by_rule[r['id']].append((p, m.start(), m.end(), p['text'][m.start():m.end()],
                                                 f + m.group(1)[len(f) + 1:]))


def run_heading_case(paras, out):
    """Headings in sentence case (FAOSTYLE §8.1): flag capitalized words after the first that the document
    writes in lower case elsewhere (so they are not proper names)."""
    lower_seen, cap_seen = Counter(), Counter()
    for p in paras:
        if p['kind'] in ('body', 'box', 'front_matter'):
            for m in re.finditer(r'(?<![\w’-])([A-Za-z][a-z’-]+)', p['text']):
                w = m.group(1)
                if w[0].islower():
                    lower_seen[w] += 1
                elif re.search(r'[a-z0-9,;’)]\s+$', p['text'][max(0, m.start() - 4):m.start()]):
                    cap_seen[w.lower()] += 1     # capitalized mid-sentence: the document treats it as a name
    for p in paras:
        if p['kind'] != 'heading':
            continue
        t = re.sub(r'^#+\s*', '', p['text'])
        t2 = re.sub(r'^(?:(?:Section|Part|Chapter)\s+)?[\dA-Z]{0,3}[.)]?[\d.]*\s+', '', t)
        words = list(re.finditer(r'(?<![\w’-])([A-Z][a-z’-]+)', t2))
        cand = words[1:] if words and words[0].start() == 0 else words
        bad = [m for m in cand if lower_seen[m.group(1).lower()] >= 2 and lower_seen[m.group(1).lower()] > cap_seen[m.group(1).lower()]
               and not re.search(r'[:–?!.]\s*$', t2[:m.start()])]
        if bad:
            off = len(p['text']) - len(t2)
            out.append((p, off + bad[0].start(), off + bad[-1].end(), ', '.join(m.group(1) for m in bad),
                        'sentence case: ' + ', '.join(m.group(1).lower() for m in bad)))


def load_nocs(script):
    spec = importlib.util.spec_from_file_location('nocs_check', script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='FAOSTYLE preflight')
    ap.add_argument('manuscript')
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument('--register', default=os.path.join(here, '..', 'fao_style_register.json'))
    ap.add_argument('--words', default=os.path.join(here, '..', 'fao_recommended_words.json'))
    ap.add_argument('--nocs')
    ap.add_argument('--nocs-script')
    ap.add_argument('--out-dir')
    ap.add_argument('--context', nargs='*', default=[],
                    help='main-text manuscript(s) whose defined abbreviations need no redefinition here (annexes)')
    a = ap.parse_args()
    try:
        reg = json.load(open(a.register, encoding='utf-8'))
        words = json.load(open(a.words, encoding='utf-8'))['rules']
    except (OSError, ValueError) as ex:
        print(f'preflight: cannot load the register: {ex}', file=sys.stderr)
        sys.exit(2)
    ext = os.path.splitext(a.manuscript)[1].lower()
    paras = read_docx(a.manuscript) if ext == '.docx' else read_labelled_md(a.manuscript)
    fmt = 'docx' if ext == '.docx' else 'labelled-md'
    classify(paras)
    global KNOWN_ABBR
    KNOWN_ABBR = known_abbreviations(paras)
    context_defined = set()
    for c in a.context:
        cp = read_docx(c) if c.lower().endswith('.docx') else read_labelled_md(c)
        classify(cp)
        context_defined |= known_abbreviations(cp)
    KNOWN_ABBR |= context_defined
    has_nbsp = any('\u00a0' in p['text'] for p in paras)
    rules = [r for r in reg['rules'] if r['relevance'] == 'manuscript' and not r.get('duplicate_of')]
    hits = defaultdict(list)
    status = {}
    implemented_modules = {'compound_form', 'acronym_first_use', 'nocs'}
    for r in rules:
        ch = r['check']
        req = set(ch.get('requires', []))
        if 'nbsp' in req and not has_nbsp:
            status[r['id']] = 'skipped: needs non-breaking spaces (none in this file)'
            continue
        if 'formatting' in req and fmt != 'docx':
            status[r['id']] = 'skipped: needs run formatting (DOCX input)'
            continue
        m = ch['method']
        if m == 'regex':
            status[r['id']] = run_regex(r, paras, hits[r['id']])
        elif m == 'wordlist':
            status[r['id']] = run_wordlist(r, paras, hits[r['id']])
        elif m == 'module' and ch.get('module') in implemented_modules:
            status[r['id']] = 'module'
        elif m == 'module':
            status[r['id']] = 'not built'
        else:
            status[r['id']] = m
    # Appendix 2
    for r in words:
        if r.get('duplicate_of'):
            continue
        ch = r['check']
        if ch['method'] == 'wordlist':
            status[r['id']] = run_wordlist(r, paras, hits[r['id']])
        elif ch['method'] == 'regex':
            status[r['id']] = run_regex(r, paras, hits[r['id']])
    run_compounds(words, paras, hits)
    # modules
    acr_rule = 'ABB-7-003'
    run_acronyms(paras, hits[acr_rule], context_defined)
    run_double_l(words, paras, hits)
    run_heading_case(paras, hits['CAP-8_1-001'])
    status['CAP-8_1-001'] = 'module'
    status[acr_rule] = 'module'
    run_consistency(paras, hits['SPL-4-008'], hits['SPL-4-008'], None)
    for rid in ('SPL-4-008', 'WRT-3_1-010'):
        status[rid] = 'module'
    nocs_src = None
    if a.nocs and a.nocs_script:
        nc = load_nocs(a.nocs_script)
        ents, nocs_src, _ = nc.load_nocs(a.nocs)
        npar = [dict(text=p['text'], style='Heading' if p['kind'] == 'heading' else '', el=None) for p in paras]
        nc.classify_paras(npar)
        for f in nc.scan(npar, ents):
            if f['Action'] in ('Apply', 'Verify'):
                p = paras[f['Para']]
                before = p['text'][:f['start']]
                if p['kind'] in ('table', 'list_entry') and not before.strip(' *'):
                    continue                     # label or cell that starts with the name: no article (§6.3.1.2)
                if not before.replace('*', '').strip():
                    continue                     # bold run-in label or paragraph opening with the name
                if p['kind'] == 'reference' and re.match(r'^,\s*[A-Z]\.', p['text'][f['end']:]):
                    continue                     # surname in an author list (Holland, J.)
                hits['NAM-6_3_1-001'].append((p, f['start'], f['end'], f['Found'], f['Suggested'] + f'  [{f["Action"]}]'))
        status['NAM-6_3_1-001'] = 'module'
    else:
        status['NAM-6_3_1-001'] = 'skipped: no NOCS data given'
    # outputs
    byid = {r['id']: r for r in reg['rules'] + words}
    stem = os.path.splitext(os.path.basename(a.manuscript))[0]
    out = a.out_dir or os.path.dirname(os.path.abspath(a.manuscript))
    os.makedirs(out, exist_ok=True)
    fcsv = os.path.join(out, f'{stem}_preflight_findings.csv')
    n = 0
    seen_span = set()
    with open(fcsv, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(['ID', 'Label', 'Context', 'Rule', 'Section', 'Action', 'Rule action', 'Found', 'Suggested', 'Rule text', 'Snippet'])
        order = sorted(hits.items(), key=lambda kv: kv[0])
        rows = []
        for rid, hs in order:
            r = byid[rid]
            for p, s, e, found, sug in hs:
                key = (p['label'], s, e, rid)
                if key in seen_span:
                    continue
                seen_span.add(key)
                snip = p['text'][max(0, s - 50):e + 50].replace('\n', ' ')
                rows.append((p['label'], s, rid, r, p['kind'], found, sug, snip, e))
        def labkey(x):
            l = x[0]
            if l.startswith('^'):
                return (2, int(l[1:]), x[1])
            if l.startswith('T'):
                return (0, 0, x[1])
            return (0, int(l), x[1])
        # summary-only rules (invisible characters such as non-breaking spaces): one row with the count
        summary = defaultdict(list)
        keep = []
        for row in rows:
            if row[3]['check'].get('report') == 'summary':
                summary[row[2]].append(row)
            else:
                keep.append(row)
        for rid, rs in summary.items():
            first = sorted(rs, key=labkey)[0]
            keep.append(first[:6] + (f'{len(rs)} places in this document; first shown',) + first[7:])
        # one row per spot: overlapping hits from several rules are merged
        merged = []
        for row in sorted(keep, key=labkey):
            lab, s, rid, r, kind, found, sug, snip, e = row
            if merged and merged[-1]['lab'] == lab and s < merged[-1]['end']:
                m = merged[-1]
                if rid not in m['rids']:
                    m['rids'].append(rid)
                    m['rules'].append(r)
                    if sug and not m['sug']:
                        m['sug'] = sug
                m['end'] = max(m['end'], e)
                continue
            merged.append(dict(lab=lab, start=s, end=e, rids=[rid], rules=[r], kind=kind, found=found, sug=sug, snip=snip))
        for m in merged:
            n += 1
            w.writerow([f'P{n:04d}', f'[{m["lab"]}]', m['kind'], '; '.join(m['rids']),
                        '; '.join(dict.fromkeys(r['section'] for r in m['rules'])), 'Verify',
                        '; '.join(dict.fromkeys(r['action'] for r in m['rules'])), m['found'], m['sug'],
                        ' / '.join(r['rule'] for r in m['rules']), m['snip']])
    # agent checklist
    agent = [r for r in rules if r['check']['method'] == 'agent']
    with open(os.path.join(out, f'{stem}_agent_checklist.md'), 'w', encoding='utf-8') as f:
        f.write(f'# Agent checklist — {os.path.basename(a.manuscript)}\n\nRules that need reading with judgement. '
                'Check the manuscript against each; record hits in the editor sheet.\n\n')
        sec = None
        for r in sorted(agent, key=lambda r: [int(x) if x.isdigit() else 0 for x in re.split(r'[._]', r['section'])]):
            if r['section'] != sec:
                sec = r['section']
                f.write(f'\n## {sec} {r["section_title"]}\n\n')
            f.write(f'- **{r["id"]}** ({r["kind"]}, {r["action"]}): {r["rule"]}  \n  > {r["quote"][:300]}\n')
    # receipt
    cnt = Counter({rid: len(v) for rid, v in hits.items() if v})
    cov = defaultdict(Counter)
    for r in rules:
        st = status.get(r['id'], '')
        bucket = ('scripted' if st in ('ran', 'module') else 'agent' if st == 'agent' else
                  'manual' if st == 'manual' else 'skipped' if st.startswith('skipped') else 'module not built yet')
        if st == 'not built':
            bucket = 'module not built yet'
        cov[r['section'].split('.')[0]][bucket] += 1
    with open(os.path.join(out, f'{stem}_preflight_receipt.md'), 'w', encoding='utf-8') as f:
        h = reg['header']
        f.write(f'# FAOSTYLE preflight receipt — {os.path.basename(a.manuscript)}\n\n')
        f.write(f'- Tool: {VERSION}; input format: {fmt}; paragraphs: {len(paras)} '
                f'({dict(Counter(p["kind"] for p in paras))})\n')
        f.write(f'- Register: {h["register"]} {h["register_version"]}, compiled {h["compiled"]}; guide sha256 {h["source"]["sha256"][:16]}…\n')
        f.write(f'- NOCS data: {os.path.basename(nocs_src) if nocs_src else "NOT RUN"}\n')
        f.write(f'- Non-breaking spaces in the file: {"yes" if has_nbsp else "no"}\n')
        f.write(f'- Findings: {n} (all reported as Verify: calibration phase)\n\n')
        f.write('## Findings by rule\n\n| Rule | Hits | Rule text |\n|---|---:|---|\n')
        for rid, c in cnt.most_common():
            f.write(f'| {rid} | {c} | {byid[rid]["rule"][:110]} |\n')
        f.write('\n## Coverage of the guide (manuscript rules)\n\n| Section | Scripted | Agent checklist | Module not built yet | Skipped | Manual |\n|---|---:|---:|---:|---:|---:|\n')
        for s in sorted(cov, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else 0)):
            c = cov[s]
            f.write(f'| {s} | {c["scripted"]} | {c["agent"]} | {c["module not built yet"]} | {c["skipped"]} | {c["manual"]} |\n')
        nb = Counter(r['check'].get('module') for r in rules if status.get(r['id']) == 'not built')
        f.write('\nModules not built yet (their rules were NOT checked): ' + ', '.join(f'{k} ({v})' for k, v in nb.most_common()) + '\n')
        f.write('\nScripted rules ran over every paragraph in their scope. Agent rules are listed in the agent checklist. '
                '"Module not built yet" rules were NOT checked by this run.\n')
    print(f'{os.path.basename(a.manuscript)}: {n} findings, {len(cnt)} rules fired -> {fcsv}')


if __name__ == '__main__':
    main()
