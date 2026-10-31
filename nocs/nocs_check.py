#!/usr/bin/env python3
"""nocs_check.py — FAO NOCS country-name check for manuscripts (FAOSTYLE §6.3.1).

Detects country and territory names that do not follow the FAO Names of Countries and
Territories (NOCS) database and proposes the NOCS form, with the article rules of
FAOSTYLE §6.3.1.2 and the exceptions of §6.3.1.3.

Usage
  python nocs_check.py MANUSCRIPT [--nocs nocsDataExport.csv | --lookup nocs_lookup.json]
                       [--out-dir DIR] [--apply OUT.docx] [--gate]

  MANUSCRIPT  .docx (body, tables) or .md/.txt (one paragraph per line; '#' = heading)
  --nocs      official export from https://www.fao.org/nocs/en ("download the full
              collection"); preferred. Columns: SHORT NAME, LIST NAME, FULL NAME, NOTES …
  --lookup    project nocs_lookup.json (fallback: full name → short name only)
  --apply     write a copy of the .docx with every 'Apply' finding replaced and
              highlighted in yellow ('Verify' and 'Protected' findings are left alone)

Outputs (in --out-dir, default: next to the manuscript)
  <stem>_nocs_findings.csv   ID, Para, Context, Found, Suggested, Action, Rule, Snippet
  <stem>_nocs_receipt.md     data source + checksum, counts, zero-finding statement

Actions
  Apply      unambiguous editor fix (FAOSTYLE is mandatory; never an author choice)
  Verify     probable fix that needs a human look (possible proper name, author key,
             in-text list, US/UK noun use, list-name form)
  Protected  left untouched by rule: quotations, published titles in references,
             permitted citation forms (UK/USA in citations), adjectives (US exports)

  --gate      delivery gate: exit 0 as soon as no Apply findings remain

Exit code: 0 = no Apply/Verify findings (with --gate: no Apply findings), 1 = findings to
action, 2 = setup error.
A run that cannot load the NOCS data stops with exit 2 — it never passes silently.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys

VERSION = 'nocs_check.py 1.1 (2026-10-30)'

# ---------------------------------------------------------------- data
# Colloquial / former / abbreviated forms that the official export does not list as names.
# Each maps to the NOCS SHORT NAME exactly as it appears in the export.
VARIANTS = {
    'Tanzania': 'United Republic of Tanzania (the)',
    'Laos': "Lao People's Democratic Republic (the)",
    'Lao PDR': "Lao People's Democratic Republic (the)",
    'Lao P.D.R.': "Lao People's Democratic Republic (the)",
    'Vietnam': 'Viet Nam', 'Viet-Nam': 'Viet Nam',
    'Bolivia': 'Plurinational State of Bolivia (the)',
    'Iran': 'Islamic Republic of Iran (the)',
    'Venezuela': 'Bolivarian Republic of Venezuela (the)',
    'Micronesia': 'Federated States of Micronesia (the)',
    'Netherlands': 'Kingdom of the Netherlands (the)', 'Holland': 'Kingdom of the Netherlands (the)',
    'Syria': 'Syrian Arab Republic (the)',
    'Russia': 'Russian Federation (the)',
    'South Korea': 'Republic of Korea (the)',
    'North Korea': "Democratic People's Republic of Korea (the)", 'DPRK': "Democratic People's Republic of Korea (the)",
    'DRC': 'Democratic Republic of the Congo (the)', 'DR Congo': 'Democratic Republic of the Congo (the)',
    'Democratic Republic of Congo': 'Democratic Republic of the Congo (the)',
    'Congo-Kinshasa': 'Democratic Republic of the Congo (the)',
    'Congo-Brazzaville': 'Congo (the)', 'Republic of Congo': 'Congo (the)',
    'Moldova': 'Republic of Moldova (the)',
    'Czech Republic': 'Czechia',
    'Ivory Coast': "Côte d'Ivoire", "Cote d'Ivoire": "Côte d'Ivoire",
    'Swaziland': 'Eswatini',
    'Macedonia': 'North Macedonia', 'FYROM': 'North Macedonia',
    'Turkey': 'Türkiye', 'Turkiye': 'Türkiye',
    'Burma': 'Myanmar',
    'Cape Verde': 'Cabo Verde',
    'East Timor': 'Timor-Leste',
    'UAE': 'United Arab Emirates (the)',
    'Nauru': 'Naoero',
    'Brunei': 'Brunei Darussalam',
    'State of Palestine': 'Palestine',
    'Great Britain': 'United Kingdom of Great Britain and Northern Ireland (the)',
    'Britain': 'United Kingdom of Great Britain and Northern Ireland (the)',
    'Gambia': 'Gambia (the)',  # article check also covers this
}
# Abbreviations governed by §6.3.1.1/§6.3.1.3 exceptions (handled specially).
US_FORMS = ['USA', 'U.S.A.', 'US', 'U.S.']
UK_FORMS = ['UK', 'U.K.']
SHORTENED = {'United States': 'United States of America (the)',
             'United Kingdom': 'United Kingdom of Great Britain and Northern Ireland (the)'}
# Variants that are also common words or proper-name parts: report as Verify, never Apply.
WEAK = {'Britain', 'Great Britain', 'Holland', 'Micronesia', 'Turkey', 'Macedonia'}
# Forms whose adjective use is allowed (§6.3.1.3): "US exports", "UK aid".
ADJ_OK = set(US_FORMS) | set(UK_FORMS)

REF_HEADS = re.compile(r'^\s*(#+\s*)?(\d+\.?\s*)?(References|Bibliography|Further reading|Referencias|Bibliographie)\s*$', re.I)
CAPTION = re.compile(r'^\s*(Figure|Table|Box|Map|Plate)\s+\d', re.I)
SENT_END = re.compile(r'[.!?]["”’)]*\s*$')
STOP_CAP = {'In', 'The', 'And', 'Of', 'For', 'From', 'To', 'On', 'At', 'By', 'With', 'As', 'Both',
            'Across', 'Between', 'Within', 'Like', 'While', 'Unlike', 'Including', 'Than', 'Or', 'Neither', 'Nor'}


class Entity:
    def __init__(self, short, list_name='', full='', notes=''):
        self.short = short.strip()
        self.list_name = (list_name or '').strip()
        self.full = (full or '').strip()
        self.notes = notes or ''
        m = re.match(r'^(.*) \((the|The)\)$', self.short)
        self.base = m.group(1) if m else self.short          # name without article
        self.article = (m.group(2) if m else '')              # 'the', 'The' or ''

    def text_form(self, capital=False):
        if self.article == 'The':
            return 'The ' + self.base
        if self.article:
            return ('The ' if capital else 'the ') + self.base
        return self.base


def load_nocs(nocs_csv=None, lookup=None):
    ents, src = {}, None
    if nocs_csv:
        with open(nocs_csv, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                if not r.get('SHORT NAME'):
                    continue
                e = Entity(r['SHORT NAME'], r.get('LIST NAME', ''), r.get('FULL NAME', ''), r.get('NOTES', ''))
                ents[e.short] = e
        src = nocs_csv
    elif lookup:
        with open(lookup, encoding='utf-8') as f:
            lk = json.load(f)
        for k, v in lk.items():
            e = ents.setdefault(v, Entity(v))
            if k.startswith('the ') and not re.search(r' (Of|And|The) ', k) and k[4:5].isupper():
                e.full = e.full or k
        src = lookup
    if not ents:
        raise ValueError('no NOCS data loaded (give --nocs export.csv or --lookup nocs_lookup.json)')
    sha = hashlib.sha256(open(src, 'rb').read()).hexdigest()[:16]
    return ents, src, sha


# ---------------------------------------------------------------- reading
def read_docx(path):
    import docx
    from docx.oxml.ns import qn
    d = docx.Document(path)
    paras = []
    for p in d.element.body.iter(qn('w:p')):
        t = ''.join(x.text or '' for x in p.iter(qn('w:t')))
        st = p.find(qn('w:pPr') + '/' + qn('w:pStyle'))
        sname = st.get(qn('w:val')) if st is not None else ''
        paras.append(dict(text=t, style=sname, el=p))
    return d, paras


def read_text(path):
    paras = []
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        lab = re.match(r'^\[\d+\]\s*', line)
        body = line[lab.end():] if lab else line
        style = 'Heading' if body.lstrip().startswith('#') else ''
        paras.append(dict(text=line, style=style, el=None))
    return None, paras


def classify_paras(paras):
    in_refs = False
    for p in paras:
        t = re.sub(r'^\[\d+\]\s*', '', p['text']).strip()
        is_head = bool(re.search(r'heading|title|titre|berschrift|ttulo|titel', p['style'], re.I)) or t.startswith('#')
        if REF_HEADS.match(t):
            in_refs = True
            p['kind'] = 'heading'
            continue
        if in_refs and is_head and not REF_HEADS.match(t) and len(t.split()) > 6:
            pass
        if in_refs:
            p['kind'] = 'reference' if not is_head else 'heading-refs'
        elif CAPTION.match(t):
            p['kind'] = 'caption'
        elif is_head:
            p['kind'] = 'heading'
        else:
            p['kind'] = 'body'


# ---------------------------------------------------------------- matching
def quote_spans(text):
    spans = []
    for m in re.finditer(r'“[^”]*”|"[^"]*"', text):
        spans.append((m.start(), m.end()))
    return spans


def in_spans(i, spans):
    return any(a <= i < b for a, b in spans)


def word_rx(s):
    s2 = re.escape(s).replace("'", "['’]").replace('’', "['’]")
    return re.compile(r'(?<![\w-])' + s2 + r'(?![\w-])')


def build_patterns(ents):
    pats = []   # (regex, kind, entity_short, form)
    for e in ents.values():
        if e.article:      # correct NOCS name that needs the article in running text
            pats.append((word_rx(e.base), 'article', e.short, e.base))
        else:
            pats.append((word_rx(e.base), 'ok', e.short, e.base))
        if e.full and e.full.lower() != e.text_form().lower() and e.full.lower() != ('the ' + e.base).lower():
            pats.append((word_rx(e.full), 'fullname', e.short, e.full))
            if e.full.startswith('the '):
                pats.append((word_rx('The ' + e.full[4:]), 'fullname', e.short, 'The ' + e.full[4:]))
        if e.list_name and e.list_name != e.base and '(' in e.list_name:
            pats.append((word_rx(e.list_name), 'listname', e.short, e.list_name))
    for v, short in VARIANTS.items():
        if short in ents:
            pats.append((word_rx(v), 'variant', short, v))
    for v, short in SHORTENED.items():
        if short in ents:
            pats.append((word_rx(v), 'shortened', short, v))
    for v in US_FORMS:
        pats.append((word_rx(v), 'usuk', 'United States of America (the)', v))
    for v in UK_FORMS:
        pats.append((word_rx(v), 'usuk', 'United Kingdom of Great Britain and Northern Ireland (the)', v))
    # longest form first so that 'Democratic Republic of the Congo' wins over 'Congo'
    pats.sort(key=lambda x: -len(x[3]))
    return pats


def prev_token(text, i):
    m = re.search(r'([\w’\'.-]+)\W*$', text[:i])
    return m.group(1) if m else ''


def next_token(text, j):
    m = re.match(r'\s*([\w’\'.-]+)', text[j:])
    return m.group(1) if m else ''


def at_sentence_start(text, i):
    before = re.sub(r'^\[\d+\]\s*#*\s*', '', text[:i])
    before = re.sub(r'^\s*\d+(?:\.\d+)*\.?\s+$', '', before)     # "4.3 Tanzania" (numbered heading)
    return before.strip() == '' or bool(SENT_END.search(before))


def preceded_by_the(text, i):
    return bool(re.search(r'\b[Tt]he\s+$', text[:i]))


def in_parens(text, i):
    depth = 0
    for ch in text[:i]:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
    return depth > 0


def in_list_after_colon(text, i):
    seg = re.split(r'[.;!?]', text[:i])[-1]
    return ':' in seg


def proper_name_guard(text, i, j):
    """True if the match looks like part of a proper name (project, organization, place)."""
    nt = next_token(text, j)
    pt = prev_token(text, i)
    follows_cap = bool(nt) and nt[0].isupper() and not re.match(r'^\s*[,;:.)(–—-]', text[j:])
    prev_cap = bool(pt) and pt[0].isupper() and pt not in STOP_CAP and not at_sentence_start(text, i - len(pt) - 1 if i > len(pt) else 0) \
        and not re.search(r'[,;:(]\s*$', text[:i]) and not re.search(r'\b(and|or)\s+$', text[:i])
    return follows_cap or prev_cap


MODIFIERS = {'northern', 'southern', 'eastern', 'western', 'central', 'north-eastern', 'north-western',
             'south-eastern', 'south-western', 'northeastern', 'northwestern', 'southeastern', 'southwestern',
             'rural', 'urban', 'socialist', 'colonial', 'pre-colonial', 'postcolonial', 'post-colonial',
             'independent', 'modern', 'contemporary', 'mainland', 'coastal', 'upland', 'lowland', 'today’s', "today's"}
INSTITUTION_OK = {'Government', 'government', 'Governments', 'people', 'peoples', 'citizens', 'parts', 'part', 'regions', 'areas'}


def modifier_before(text, i):
    """Return (start, word) of a descriptive modifier right before the country ("northern Laos")."""
    m = re.search(r"([\w’'-]+)\s+$", text[:i])
    if m and m.group(1).lower() in MODIFIERS:
        return m.start(1), m.group(1)
    return None, None


def institution_before(text, i):
    """'High Court of Tanzania', 'Bank of Tanzania' — official names keep their own wording."""
    m = re.search(r"\b([A-Z][\w’'-]*) of\s+$", text[:i])
    return bool(m) and m.group(1) not in INSTITUTION_OK and m.group(1) not in STOP_CAP


def citation_key(text, i, j):
    """Country inside an in-text citation: '(Government of Lao PDR, 2021)'."""
    return in_parens(text, i) and bool(re.match(r'^[^()]*?,\s*(?:\d{4}|n\.d\.)', text[j:]))


def abbreviation_def(text, i, j):
    """'the Lao People's Democratic Republic (Lao PDR)': a defined abbreviation of a country name."""
    return bool(re.search(r'\(\s*$', text[:i])) and bool(re.match(r'^\s*\)', text[j:]))


def scan(paras, ents):
    pats = build_patterns(ents)
    findings = []
    full_seen = {'United States of America (the)': False,
                 'United Kingdom of Great Britain and Northern Ireland (the)': False}
    fid = 0
    for pi, p in enumerate(paras):
        text = p['text']
        kind = p['kind']
        qs = quote_spans(text)
        taken = []
        for rx, pkind, short, form in pats:
            for m in rx.finditer(text):
                i, j = m.start(), m.end()
                if any(not (j <= a or i >= b) for a, b in taken):
                    continue
                taken.append((i, j))
                e = ents[short]
                found = m.group(0)
                if short in full_seen and pkind in ('article', 'fullname') and kind == 'body':
                    if form == e.base:
                        full_seen[short] = True
                if pkind == 'ok':
                    continue
                act, sug, rule = decide(text, i, j, found, pkind, e, kind, qs, full_seen)
                if act is None:
                    continue
                # possessive of a name ending in s: "Laos’ population" -> "…Republic’s population"
                if sug and j < len(text) and text[j] in '’\'' and text[j + 1:j + 2] != 's' and not sug.endswith('s'):
                    sug, j, found = sug + '’s', j + 1, found + text[j]
                # modifier before a name that takes the article: "northern Laos" -> "the northern Lao …"
                if act == 'Apply' and kind != 'reference' and e.article and pkind != 'usuk' and not preceded_by_the(text, i):
                    ms, mw = modifier_before(text, i)
                    if ms is not None:
                        art = 'The ' if at_sentence_start(text, ms) else 'the '
                        core = sug.split(' ', 1)[1] if sug.lower().startswith('the ') else sug
                        act, sug = 'Verify', art + mw.lower() + ' ' + core
                        rule += ' — article goes before the modifier; replace the whole phrase (or rephrase, e.g. “the north of …”)'
                        found = text[ms:j]
                        i = ms
                fid += 1
                snip = text[max(0, i - 45):min(len(text), j + 45)].replace('\n', ' ')
                findings.append(dict(ID=f'N{fid:03d}', Para=pi, Context=kind, Found=found, Suggested=sug,
                                     Action=act, Rule=rule, Snippet=('…' if i > 45 else '') + snip + ('…' if j + 45 < len(text) else ''),
                                     start=i, end=j))
    return findings


def decide(text, i, j, found, pkind, e, kind, qs, full_seen):
    R = 'FAOSTYLE 6.3.1'
    if in_spans(i, qs):
        return 'Protected', '', 'Quotation (rule 42: quotations follow the original)'
    if kind in ('reference', 'heading-refs'):
        return decide_ref(text, i, j, found, pkind, e)
    if re.search(r"\b(?:du|de|des|del|della|di|do|da|dos|das|von|van|d’|d')\s*$", text[:i]):
        return 'Protected', '', 'Part of a foreign-language proper name (e.g. Office du Niger) — kept as is'
    if pkind in ('variant', 'fullname', 'article', 'listname') and abbreviation_def(text, i, j):
        return 'Verify', '', R + ': defined abbreviation of a country name — delete the parenthesis and use the Short Name throughout'
    if pkind in ('variant', 'fullname', 'shortened') and citation_key(text, i, j):
        if preceded_by_the(text, i) or not re.search(r'\bof\s+$', text[:i]):
            tf = e.base                       # bare key "(United Republic of Tanzania, 2023)" takes no article
        else:
            tf = e.text_form()                # "(Government of the Lao People's Democratic Republic, 2021)"
        if tf == found:
            return None, None, None
        return 'Verify', tf, R + ': in-text citation author key — change together with the reference-list entry'
    if pkind in ('variant', 'article') and institution_before(text, i):
        return 'Verify', e.base if preceded_by_the(text, i) else e.text_form(), R + ': part of an official name (court, bank, ministry…) — keep if that is the official name'
    heading_like = kind in ('heading', 'caption')
    sent_start = at_sentence_start(text, i)
    no_article_slot = heading_like and (sent_start or re.search(r'[:,–—]\s*$', text[:i]))
    if re.match(r'^\s*(?:\[\d+\]\s*)?(?:Keywords?|Key words)\s*:', text, re.I):
        no_article_slot = True        # keyword lists: bare Short Name, no article
    has_the = preceded_by_the(text, i)

    def form():
        if no_article_slot:
            return e.base
        if has_the:
            return e.base
        return e.text_form(capital=sent_start)

    if pkind == 'article':
        if e.article and not has_the and not no_article_slot:
            if citation_key(text, i, j):
                return None, None, None       # corporate author key already in NOCS form
            if no_article_slot:
                return None, None, None
            pt = prev_token(text, i)
            if pt and pt[0].isupper() and pt not in STOP_CAP and not re.search(r'[,;:(–—]\s*$', text[:i]) \
                    and not re.search(r'\b(and|or)\s+$', text[:i]) and not at_sentence_start(text, i - len(pt) - 1 if i > len(pt) else 0):
                return 'Verify', e.text_form(), R + ': preceded by a capitalized word — possible historical or proper name (e.g. Belgian Congo); check'
            if in_parens(text, i) or in_list_after_colon(text, i):
                return 'Verify', e.list_name or e.base, R + '.2: in-text lists after a colon or in parentheses use the Short Name for Lists'
            if found.endswith(('’s', "'s")):
                pass
            if re.search(r'^\s*(Act|Law|Policy|Agreement)\b', text[j:]):
                return None, None, None
            return 'Apply', e.text_form(capital=sent_start), R + '.2: Short Name with (the) takes the article in running text'
        return None, None, None
    if pkind == 'fullname':
        if found.lower() == e.text_form().lower():
            return None, None, None
        return 'Apply', form(), R + '.2: Full Name is reserved for formal documents; use the Short Name'
    if pkind == 'listname':
        if in_parens(text, i) or in_list_after_colon(text, i) or kind == 'caption':
            return None, None, None
        return 'Apply', form(), R + '.2: Short Name for Lists only in lists, tables and in-text lists after a colon'
    if pkind == 'variant':
        if proper_name_guard(text, i, j) or found in WEAK:
            return 'Verify', form(), R + ': non-NOCS form; possible proper name (project, organization, place) — check'
        return 'Apply', form(), R + ': non-NOCS form; use the NOCS Short Name'
    if pkind == 'shortened':
        if full_seen.get(e.short) and kind == 'body':
            if not has_the and not no_article_slot:
                return 'Apply', ('The ' if sent_start else 'the ') + found, R + '.1: shortened form after full name, with article'
            return None, None, None
        return 'Apply', form(), R + '.1: write the full NOCS name once before using the shortened form'
    if pkind == 'usuk':
        if in_parens(text, i) and re.search(r'\d{4}', text[i:i + 40]):
            return 'Protected', '', R + '.3: UK and USA allowed in citations'
        nt = next_token(text, j)
        if nt and nt[0].islower() and nt not in ('is', 'was', 'has', 'had', 'and', 'or', 'to', 'in', 'of', 'during', 'were', 'are', 'will', 'would', 'bombed', 'did', 'does'):
            return 'Protected', '', R + '.3: US/UK as adjective is allowed'
        target = ('the United States' if 'States' in e.base else 'the United Kingdom') if full_seen.get(e.short) else e.text_form()
        if sent_start:
            target = target[0].upper() + target[1:]
        rep_start = i - 4 if has_the else i
        return 'Verify', target, R + '.3: US/UK/USA as a noun is not allowed in text (only as adjective or in citations)'
    return None, None, None


def decide_ref(text, i, j, found, pkind, e):
    R = 'FAOSTYLE 6.3.1'
    body = re.sub(r'^\[\d+\]\s*', '', text)
    off = len(text) - len(body)
    # entry-start author key: "United Republic of Tanzania. Land Act…", "Tanzania. …"
    if i - off <= 1 and re.match(r'^\s*[.,]', text[j:]):
        if pkind in ('variant', 'fullname'):
            return 'Apply', e.base, R + '.2 and rule 135: country key of a legislation entry uses the NOCS Short Name'
        return None, None, None
    if pkind == 'usuk':
        return 'Protected', '', 'Rule 73 / FAOSTYLE 6.3.1.3: UK and USA allowed in references'
    # place of publication: "City, Country, Publisher." or "City, Country."
    before = text[:i]
    if re.search(r'Government of\s+$', before):
        return 'Verify', e.text_form(), R + ': corporate author key — NOCS form unless the publication prints otherwise'
    if re.search(r"(?:^|[.,] )[A-Z][\w'’.-]*(?: [a-z]{1,3})?(?: [A-Z][\w'’.-]*)*, $", before) and re.match(r'^\s*[,.;&]', text[j:]):
        if pkind in ('variant', 'fullname', 'shortened'):
            return 'Apply', e.base, R + '.2: place of publication uses the NOCS Short Name, no article (rule 72)'
        return None, None, None
    if pkind == 'variant' and re.match(r'^\s*\(', text[j:]):
        return 'Verify', e.base, R + ': non-NOCS form in an author key — check'
    return 'Protected', '', 'Published title or publisher name in a reference entry (kept as published)'


# ---------------------------------------------------------------- apply (.docx)
def apply_docx(doc, paras, findings, out_path):
    from docx.oxml.ns import qn
    import copy
    by_para = {}
    for f in findings:
        if f['Action'] == 'Apply':
            by_para.setdefault(f['Para'], []).append(f)
    alltext = ''.join(p['text'] for p in paras)
    curly = alltext.count('’') >= alltext.count("'")      # follow the document's apostrophe style
    n = 0
    for pi, fs in by_para.items():
        p_el = paras[pi]['el']
        for f in sorted(fs, key=lambda x: -x['start']):
            start, end, new = f['start'], f['end'], f['Suggested']
            text = paras[pi]['text']
            if preceded_by_the(text, start) and f['Context'] != 'reference' and new.lower().startswith('the '):
                new = new[4:]
            if re.match(r'^the ', new) and preceded_by_the(text, start):
                new = new[4:]
            if curly:
                new = new.replace("'", '’')
            _replace_span(p_el, start, end, new)
            n += 1
    doc.save(out_path)
    return n


def _replace_span(p_el, start, end, new):
    from docx.oxml.ns import qn
    import copy
    runs = [r for r in p_el.iter(qn('w:r')) if r.findall(qn('w:t'))]
    pos, loc = 0, []
    for r in runs:
        t = ''.join(x.text or '' for x in r.findall(qn('w:t')))
        loc.append((r, pos, pos + len(t), t))
        pos += len(t)
    first = True
    for r, a, b, t in loc:
        if b <= start or a >= end:
            continue
        s, e_ = max(start, a) - a, min(end, b) - a
        ts = r.findall(qn('w:t'))
        for x in ts[1:]:
            r.remove(x)
        if first:
            pre, post = t[:s], t[e_:]
            ts[0].text = pre
            ts[0].set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            nr = copy.deepcopy(r)
            for x in nr.findall(qn('w:t'))[1:]:
                nr.remove(x)
            nr.findall(qn('w:t'))[0].text = new
            rpr = nr.find(qn('w:rPr'))
            if rpr is None:
                from lxml import etree
                rpr = etree.Element(qn('w:rPr'))
                nr.insert(0, rpr)
            for h in rpr.findall(qn('w:highlight')):
                rpr.remove(h)
            from lxml import etree
            h = etree.Element(qn('w:highlight'))
            h.set(qn('w:val'), 'yellow')
            after = [qn('w:' + t) for t in ('u', 'effect', 'bdr', 'shd', 'fitText', 'vertAlign', 'rtl', 'cs',
                                            'em', 'lang', 'eastAsianLayout', 'specVanish', 'oMath', 'rPrChange')]
            nxt = next((c for c in rpr if c.tag in after), None)
            if nxt is not None:
                nxt.addprevious(h)
            else:
                rpr.append(h)
            r.addnext(nr)
            if post:
                pr = copy.deepcopy(r)
                pr.findall(qn('w:t'))[0].text = post
                nr.addnext(pr)
            first = False
        else:
            ts[0].text = t[:s] + t[e_:]
            ts[0].set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='FAO NOCS country-name check')
    ap.add_argument('manuscript')
    ap.add_argument('--nocs')
    ap.add_argument('--lookup')
    ap.add_argument('--out-dir')
    ap.add_argument('--apply')
    ap.add_argument('--gate', action='store_true',
                    help='delivery gate: exit 0 when no Apply findings remain (Verify items are listed for the editor)')
    a = ap.parse_args()
    try:
        ents, src, sha = load_nocs(a.nocs, a.lookup)
    except (OSError, ValueError) as ex:
        print(f'nocs_check: cannot load NOCS data: {ex}', file=sys.stderr)
        sys.exit(2)
    missing = [v for v, s in VARIANTS.items() if s not in ents]
    ext = os.path.splitext(a.manuscript)[1].lower()
    doc, paras = read_docx(a.manuscript) if ext == '.docx' else read_text(a.manuscript)
    classify_paras(paras)
    findings = scan(paras, ents)
    stem = os.path.splitext(os.path.basename(a.manuscript))[0]
    out = a.out_dir or os.path.dirname(os.path.abspath(a.manuscript))
    os.makedirs(out, exist_ok=True)
    fcsv = os.path.join(out, f'{stem}_nocs_findings.csv')
    with open(fcsv, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(['ID', 'Para', 'Context', 'Found', 'Suggested', 'Action', 'Rule', 'Snippet'])
        for x in findings:
            w.writerow([x['ID'], x['Para'], x['Context'], x['Found'], x['Suggested'], x['Action'], x['Rule'], x['Snippet']])
    applied = None
    if a.apply:
        if doc is None:
            print('nocs_check: --apply needs a .docx input', file=sys.stderr)
            sys.exit(2)
        applied = apply_docx(doc, paras, findings, a.apply)
    cnt = {k: sum(1 for x in findings if x['Action'] == k) for k in ('Apply', 'Verify', 'Protected')}
    by_form = {}
    for x in findings:
        if x['Action'] != 'Protected':
            by_form[x['Found']] = by_form.get(x['Found'], 0) + 1
    rec = os.path.join(out, f'{stem}_nocs_receipt.md')
    with open(rec, 'w', encoding='utf-8') as f:
        f.write(f'# NOCS check receipt — {os.path.basename(a.manuscript)}\n\n')
        f.write(f'- Tool: {VERSION}\n- NOCS data: `{os.path.basename(src)}` (sha256 {sha}…), {len(ents)} entries\n')
        f.write(f'- Paragraphs scanned: {len(paras)} (body, headings, captions, tables, references)\n')
        f.write(f'- Findings: Apply {cnt["Apply"]}, Verify {cnt["Verify"]}, Protected {cnt["Protected"]}\n')
        if applied is not None:
            f.write(f'- Applied to: `{os.path.basename(a.apply)}` ({applied} replacements, highlighted)\n')
        if missing:
            f.write(f'- WARNING: variant targets missing from the NOCS data: {", ".join(missing)}\n')
        if a.gate:
            f.write(f'- Delivery gate: **{"PASS" if not cnt["Apply"] else "FAIL"}** (Apply must be 0; '
                    f'each Verify item needs an editor decision recorded in the editor sheet)\n')
        if not (cnt['Apply'] or cnt['Verify']):
            f.write('\n**Result: no non-NOCS country names found.** This receipt is the evidence that the check ran.\n')
        else:
            f.write('\n## Forms to action\n\n| Form found | Count |\n|---|---|\n')
            for k, v in sorted(by_form.items(), key=lambda kv: -kv[1]):
                f.write(f'| {k} | {v} |\n')
    print(f'{os.path.basename(a.manuscript)}: Apply {cnt["Apply"]}, Verify {cnt["Verify"]}, Protected {cnt["Protected"]} -> {fcsv}')
    if a.gate:
        sys.exit(1 if cnt['Apply'] else 0)
    sys.exit(1 if (cnt['Apply'] or cnt['Verify']) else 0)


if __name__ == '__main__':
    main()
