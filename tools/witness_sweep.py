"""Systematic witness-compound sweep.
Phase A: build code-pair stats (all aligned 2-byte kanji-code bigrams, freq + block spread).
Phase B: for each DUPLICATE-coded char, compare the two codes' neighbor profiles — if disjoint,
one is a merge error; report top compounds for manual/auto adjudication.
Phase C: for each UNSOLVED code, list its strongest compounds with SOLVED neighbors -> candidates.
Output: font_work/sweep_report.txt (no auto-commits; solves must be human-adjudicated)."""
import sys, collections, re
sys.path.insert(0,'tools')
import importlib, wa2_kanji_map
importlib.reload(wa2_kanji_map)
from wa2_jp_decode import readfile, decode
K = wa2_kanji_map.KANJI
JD = readfile('Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin',12601,13271040)
JBLK = 110592

# --- Phase A: aligned bigram scan inside messages ---
CTRL2 = {0xf0,0x05,0x0a,0x0b,0x10,0x11,0x13,0x16,0x17,0x18}
KHI = {0x88,0x89,0x8a,0x8b}
pair_freq = collections.Counter()      # (c1,c2) -> count
pair_blocks = collections.defaultdict(set)
code_freq = collections.Counter()
code_blocks = collections.defaultdict(set)
# also record kana AFTER a code (okurigana profile) and kana BEFORE
after_kana = collections.defaultdict(collections.Counter)
i = 0
while True:
    i = JD.find(b'\x10\x0c', i+1)
    if i < 0: break
    j = i+2; prev = None
    while j < len(JD)-1:
        c = JD[j]
        if c == 0x00: break
        if c in KHI:
            code = (c<<8) | JD[j+1]
            code_freq[code] += 1
            code_blocks[code].add(j//JBLK)
            if prev is not None:
                pair_freq[(prev,code)] += 1
                pair_blocks[(prev,code)].add(j//JBLK)
            prev = code
            j += 2
        elif c in CTRL2:
            prev = None; j += 2
        else:
            if prev is not None and 0x01 <= c <= 0x7f:
                after_kana[prev][c] += 1
            prev = None; j += 1

def name(code):
    return K.get(f'{code:04x}', '□')

out = []
out.append('='*90)
out.append('PHASE B — DUPLICATE-CODED CHARS (merge-error audit)')
out.append('  For each char with 2+ codes: top compounds per code. DISJOINT profiles = merge error.')
out.append('='*90)
rev = collections.defaultdict(list)
for k,v in K.items(): rev[v].append(int(k,16))
dups = {v:cs for v,cs in rev.items() if len(cs)>1}
for ch, cs in sorted(dups.items(), key=lambda x: -max(code_freq.get(c,0) for c in x[1])):
    out.append(f'\n## {ch} <- codes {[f"{c:04x}" for c in cs]}')
    for c in cs:
        # top pair-compounds where this code participates (either side), freq>=5, blocks>=3
        comps = []
        for (a,b),f in pair_freq.items():
            if f<5: continue
            if a==c or b==c:
                bl=len(pair_blocks[(a,b)])
                if bl<2: continue
                comps.append((f,bl,f'{name(a)}{name(b)}',f'{a:04x}+{b:04x}'))
        comps.sort(reverse=True)
        tot=code_freq.get(c,0); nb=len(code_blocks.get(c,()))
        out.append(f'  {c:04x} (freq={tot}, blocks={nb}):')
        for f,bl,w,hx in comps[:6]:
            out.append(f'      {w}  {f}x/{bl}blk  [{hx}]')

out.append('')
out.append('='*90)
out.append('PHASE C — UNSOLVED CODES with solved-neighbor compounds (solve candidates)')
out.append('  code (freq/blocks): compounds where the OTHER side is solved. □=this code.')
out.append('='*90)
unsolved = [c for c in code_freq if f'{c:04x}' not in K and code_freq[c]>=8]
unsolved.sort(key=lambda c:-code_freq[c])
for c in unsolved[:120]:
    comps=[]
    for (a,b),f in pair_freq.items():
        if f<4: continue
        if a==c and f'{b:04x}' in K:
            comps.append((f,len(pair_blocks[(a,b)]),f'□{name(b)}'))
        elif b==c and f'{a:04x}' in K:
            comps.append((f,len(pair_blocks[(a,b)]),f'{name(a)}□'))
    comps.sort(reverse=True)
    if not comps: continue
    ak = after_kana.get(c, collections.Counter()).most_common(3)
    out.append(f'\n{c:04x} (freq={code_freq[c]}, blk={len(code_blocks[c])}): ' +
               '  '.join(f'{w} {f}x/{bl}b' for f,bl,w in comps[:5]))
open('font_work/sweep_report.txt','w').write('\n'.join(out))
print(f'dup chars: {len(dups)}, unsolved(freq>=8): {len(unsolved)}')
print('wrote font_work/sweep_report.txt', len(out), 'lines')
