#!/usr/bin/env python3
"""
Insert a LIT line into every US# box that lacks one, in the hub file + all first-pass files.
Idempotent. Honest by JP state — never fabricates a literal from garbled JP:
  clean JP   (kana/kanji, no <codes>)  -> LIT: __LIT_TODO__   (a human/Claude fills a real literal)
  dirty JP   (contains <...> unsolved) -> LIT: (literal pending: JP has unsolved codes)
  empty JP                             -> LIT: (no JP text)

Also fixes the column-legend comment to name LIT.
Run: python3 tools/add_lit_slots.py            # report only
     python3 tools/add_lit_slots.py --write     # apply
"""
import os, re, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [os.path.join(ROOT,'translation/insert','m1_chateau_hub_FINAL.txt')] + \
        sorted(glob.glob(os.path.join(ROOT,'translation/insert','firstpass','*.txt')))

CJK = re.compile(r'[぀-ヿ㐀-鿿]')
def jp_state(body):
    b = body.strip()
    if not b: return 'empty'
    if '<' in b: return 'dirty'
    if CJK.search(b): return 'clean'
    return 'dirty'   # ascii-only JP line = still artifacty

def process(path, write):
    lines = open(path, encoding='utf-8').read().split('\n')
    out = []; added=0; clean=0; dirty=0; empty=0; had=0
    i = 0
    while i < len(lines):
        ln = lines[i]; out.append(ln)
        m = re.match(r'^(\s{2})JP\s*:\s?(.*)$', ln)
        if m:
            # does a LIT line already follow (allowing JP continuation lines)?
            j = i+1
            # skip JP continuation (indent 7+, not a tag)
            while j < len(lines) and re.match(r'^\s{7}\S', lines[j]) and not re.match(r'^\s{2}(LIT|EN|RE)\s*:', lines[j]):
                out.append(lines[j]); j += 1
            nxt = lines[j] if j < len(lines) else ''
            if re.match(r'^\s{2}LIT\s*:', nxt):
                had += 1
            else:
                st = jp_state(m.group(2))
                if st=='clean': lit='  LIT: __LIT_TODO__'; clean+=1
                elif st=='empty': lit='  LIT: (no JP text)'; empty+=1
                else: lit='  LIT: (literal pending: JP has unsolved codes)'; dirty+=1
                out.append(lit); added+=1
            i = j; continue
        i += 1
    txt = '\n'.join(out)
    txt = txt.replace('# Columns: JP (reference) / EN (original) / RE (fit, em-dash-free).',
                      '# Columns: JP (reference) / LIT (literal) / EN (original) / RE (fit, em-dash-free).')
    if write: open(path,'w',encoding='utf-8').write(txt)
    return added, clean, dirty, empty, had

def main():
    write = '--write' in sys.argv
    tot=[0,0,0,0,0]
    for f in FILES:
        a,c,d,e,h = process(f, write)
        tot=[tot[0]+a,tot[1]+c,tot[2]+d,tot[3]+e,tot[4]+h]
        print(f"{os.path.relpath(f,ROOT):44} +{a:4d} LIT (clean {c}, dirty {d}, empty {e}; had {h})")
    print('-'*80)
    verb = 'WROTE' if write else 'would add'
    print(f"{verb}: +{tot[0]} LIT lines | {tot[1]} clean(__LIT_TODO__ to fill) / {tot[2]} pending / {tot[3]} empty | {tot[4]} already had LIT")

if __name__=='__main__':
    main()
