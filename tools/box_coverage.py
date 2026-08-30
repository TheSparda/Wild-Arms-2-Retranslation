#!/usr/bin/env python3
"""
Honest coverage report over the CORRECT box set (data/script/boxes.json), not the old
indexed-only DB slots. Cross-references each EN story box against the translated RE in
wa2_db.json (matched by normalized EN text, the only reliable bridge between the two
extractors — the US# slot key does NOT index the new box set).

See memory: wa2-extraction-two-framings. The old DB counted only \x10\x0c-indexed boxes as
the denominator, inflating coverage to ~97%. Measured against the real ~14.1k EN story
boxes, true coverage is ~48%.

OUTPUT
  data/script/box_coverage.json  — {total, match, per_block:{blk:{total,match}}}
  (stdout) headline % + top untranslated blocks. --verify prints a block's gap sample.
"""
import os, re, sys, json, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GS   = os.path.join(ROOT, 'data/script')
INS  = os.path.join(ROOT, 'translation/insert')
BOX  = os.path.join(GS, 'boxes.json')
DB   = os.path.join(GS, 'wa2_db.json')
OUT  = os.path.join(GS, 'box_coverage.json')

DEMO = ('demo version', 'this is a demo', 'cannot save', 'present demo')


def norm(s):
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower()).split())


def is_demo(t):
    tl = t.lower()
    return any(d in tl for d in DEMO)


def translated_en():
    """Normalized EN of everything that has an RE translation = the 'already translated' set.

    Two sources, because inline/ambient boxes (\x06/\x0d-framed) have NO US# slot and so never
    enter the US#-keyed DB: (1) RE-bearing DB rows, (2) any box in an translation/insert/*_FINAL.txt that has
    an `EN :` line followed by at least one `RE :` line. Keyed by normalized EN text — the only
    bridge between the box set and the translation files."""
    s = set()
    for r in json.load(open(DB))['rows']:
        if r.get('re', '').strip():
            nt = norm(r['en'])
            if len(nt) >= 6:
                s.add(nt)
    for path in glob.glob(os.path.join(INS, '*_FINAL.txt')) + \
                glob.glob(os.path.join(INS, 'firstpass', '*_FINAL.txt')):
        cur_en = None
        for ln in open(path, encoding='utf-8'):
            m = re.match(r'^  EN :\s?(.*)', ln)
            if m:
                cur_en = norm(m.group(1)); continue
            if ln.startswith('  RE :') and cur_en and len(cur_en) >= 6:
                s.add(cur_en); cur_en = None
    return s


def compute():
    box = json.load(open(BOX))
    tr = translated_en()
    tr_list = list(tr)
    per = {}
    g_tot = g_match = g_demo = 0
    for blk, v in box.items():
        tot = match = 0
        for p in v['pairs']:
            en = p.get('en', '')
            if not en:
                continue
            nt = norm(en)
            if len(nt) < 6:
                continue
            if is_demo(en):
                g_demo += 1
                continue
            tot += 1
            if nt in tr or any(nt in h or h in nt for h in tr_list):
                match += 1
        per[blk] = {'total': tot, 'match': match}
        g_tot += tot
        g_match += match
    return {'total': g_tot, 'match': g_match, 'demo_skipped': g_demo, 'per_block': per}


def main():
    cov = compute()
    json.dump(cov, open(OUT, 'w'))
    t, m = cov['total'], cov['match']
    print(f"HONEST EN story-box coverage (demo excluded): {m}/{t} = {100*m/t:.1f}%")
    print(f"untranslated boxes: {t - m}  ·  demo/boilerplate skipped: {cov['demo_skipped']}")
    gaps = sorted(((int(b), v['total'] - v['match']) for b, v in cov['per_block'].items()),
                  key=lambda x: -x[1])
    print("top blocks by untranslated boxes:", gaps[:15])
    print(f"wrote {OUT}")

    if '--verify' in sys.argv:
        blk = str(int(sys.argv[sys.argv.index('--verify') + 1]))
        box = json.load(open(BOX))
        tr = translated_en(); trl = list(tr)
        print(f"\n=== untranslated sample, block {blk} ===")
        n = 0
        for p in box[blk]['pairs']:
            en = p.get('en', '')
            if not en or len(norm(en)) < 6 or is_demo(en):
                continue
            nt = norm(en)
            if not (nt in tr or any(nt in h or h in nt for h in trl)):
                print(f"  EN: {en[:60]}")
                print(f"  JP: {p.get('jp','')[:40]}")
                n += 1
                if n >= 15:
                    break


if __name__ == '__main__':
    main()
