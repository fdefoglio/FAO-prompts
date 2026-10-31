"""Regression cases for nocs_check.py. Run: python -I test_nocs.py <nocs_export.csv>"""
import sys
sys.path.insert(0, sys.argv[2] if len(sys.argv) > 2 else __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import nocs_check as nc

ents, _, _ = nc.load_nocs(sys.argv[1])

# (kind, text, expected list of (found, action, suggested-or-None))
CASES = [
    ('body', 'Land reforms in Tanzania were gendered.', [('Tanzania', 'Apply', 'the United Republic of Tanzania')]),
    ('body', 'Tanzania’s 1995 National Land Policy is gender-aware.', [('Tanzania', 'Apply', 'The United Republic of Tanzania')]),
    ('body', 'Laos officially does not recognize Indigenous Peoples.', [('Laos', 'Apply', "The Lao People's Democratic Republic")]),
    ('body', 'The Land Management Project Laos (LMPL) works in Houaphan.', [('Laos', 'Verify', None)]),
    ('body', 'The Tanzania Women Lawyers Association drafted a guide.', [('Tanzania', 'Verify', None)]),
    ('body', 'Experience from the United Republic of Tanzania shows progress.', []),
    ('body', 'Experience from United Republic of Tanzania shows progress.', [('United Republic of Tanzania', 'Apply', 'the United Republic of Tanzania')]),
    ('body', 'Study visits to Benin, Burkina Faso and Niger informed the process.', [('Niger', 'Apply', 'the Niger')]),
    ('body', 'Nigeria and South Sudan are not affected.', []),
    ('body', 'Many Hmong supported the US during the war.', [('US', 'Verify', None)]),
    ('body', 'US exports grew.', [('US', 'Protected', None)]),
    ('body', 'The United States was involved in that war.', [('United States', 'Apply', 'United States of America')]),
    ('body', 'Vietnam and Cambodia share borders with Laos.', [('Vietnam', 'Apply', 'Viet Nam'), ('Laos', 'Apply', "the Lao People's Democratic Republic")]),
    ('body', 'Data came from the Republic of Kenya and Bolivia.', [('the Republic of Kenya', 'Apply', 'Kenya'), ('Bolivia', 'Apply', 'the Plurinational State of Bolivia')]),
    ('body', 'Countries covered: Bolivia (Plurinational State of), Chile and Peru.', []),
    ('body', 'In the words of the minister, “Laos is open for business”.', [('Laos', 'Protected', None)]),
    ('body', 'The Democratic Republic of the Congo and the Congo signed.', []),
    ('body', 'DRC reforms followed.', [('DRC', 'Apply', 'The Democratic Republic of the Congo')]),
    ('body', 'Swaziland and Turkey were consulted.', [('Swaziland', 'Apply', 'Eswatini'), ('Turkey', 'Verify', 'Türkiye')]),
    ('heading', 'Land rights in Laos', [('Laos', 'Apply', "the Lao People's Democratic Republic")]),
    ('heading', 'Tanzania – lessons learned', [('Tanzania', 'Apply', 'United Republic of Tanzania')]),
    ('caption', 'Figure 2. Poster used in Laos', [('Laos', 'Apply', "the Lao People's Democratic Republic")]),
    ('reference', 'Shivji, I.G. 1998. Not yet democracy: Reforming land tenure in Tanzania. Dar es Salaam, Tanzania, Hakiardhi.',
     [('Tanzania', 'Protected', None), ('Tanzania', 'Apply', 'United Republic of Tanzania')]),
    ('reference', 'Tanzania. Land Act, 1999. Act No. 4 of 1999.', [('Tanzania', 'Apply', 'United Republic of Tanzania')]),
    ('reference', 'United Republic of Tanzania. Land Act, 1999. Act No. 4 of 1999.', []),
    ('reference', 'Government of Lao PDR. 2021. 9th five-year plan. Vientiane.', [('Lao PDR', 'Verify', None)]),
    ('reference', 'Berry, S. 1993. No condition is permanent. Madison, USA, University of Wisconsin Press.', [('USA', 'Protected', None)]),
    ('reference', 'Hett, C. 2020. Land leases and concessions in the Lao PDR. Bern, CDE.', [('Lao PDR', 'Protected', None)]),
    # added after the P4/P6 run
    ('body', 'Over 70 percent of Laos’ 7.3 million inhabitants live in rural areas.', [('Laos’', 'Apply', "the Lao People's Democratic Republic’s")]),
    ('body', 'Their settling in northern Laos can be traced back.', [('northern Laos', 'Verify', "the northern Lao People's Democratic Republic")]),
    ('body', 'Northern Laos resembles a patchwork quilt.', [('Northern Laos', 'Verify', "The northern Lao People's Democratic Republic")]),
    ('body', 'The forest strategy (Government of Lao PDR, 2024) sets targets.', [('Lao PDR', 'Verify', "the Lao People's Democratic Republic")]),
    ('body', 'In the Lao People’s Democratic Republic (Lao PDR), this required work.', [('Lao PDR', 'Verify', '')]),
    ('body', 'The LRM filed charges in the High Court of Tanzania.', [('Tanzania', 'Verify', None)]),
    ('body', 'The Government of Tanzania embraced a market economy.', [('Tanzania', 'Apply', 'the United Republic of Tanzania')]),
    ('body', 'This law establishes the bodies (United Republic of Tanzania, 2023, p. 2).', []),
    ('body', 'Parcels are titled (Lao PDR, 2020).', [('Lao PDR', 'Verify', "Lao People's Democratic Republic")]),
    ('body', 'Leases on state-owned land in the Office du Niger grew.', [('Niger', 'Protected', None)]),
    ('body', 'During the Belgian Congo (1908–1960), concessions shifted.', [('Congo', 'Verify', None)]),
    ('body', 'Keywords: Amendment of the 1973 Land Law; DRC; land reform', [('DRC', 'Apply', 'Democratic Republic of the Congo')]),
    ('heading', '4.3 Tanzania', [('Tanzania', 'Apply', 'United Republic of Tanzania')]),
    ('body', 'Study visits to Benin, Burkina Faso, and Niger informed it.', [('Niger', 'Apply', 'the Niger')]),
    ('body', 'Northern Viet Nam and Vietnam’s south were covered.', [('Vietnam', 'Apply', 'Viet Nam')]),
]

fails = 0
for kind, text, exp in CASES:
    paras = [dict(text=text, style='Heading1' if kind == 'heading' else '', el=None)]
    if kind == 'reference':
        paras = [dict(text='References', style='Heading1', el=None)] + paras
    nc.classify_paras(paras)
    if kind == 'caption':
        assert paras[0]['kind'] == 'caption'
    got = [(f['Found'], f['Action'], f['Suggested']) for f in nc.scan(paras, ents)]
    got.sort(key=lambda x: text.find(x[0]))
    ok = len(got) == len(exp) and all(g[0] == e[0] and g[1] == e[1] and (e[2] is None or g[2] == e[2]) for g, e in zip(sorted(got), sorted(exp)))
    if not ok:
        fails += 1
        print('FAIL', kind, '|', text, '\n   expected', exp, '\n   got     ', got)
print(f'{len(CASES) - fails}/{len(CASES)} cases pass')
sys.exit(1 if fails else 0)
