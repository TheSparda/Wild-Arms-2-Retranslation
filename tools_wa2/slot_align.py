#!/usr/bin/env python3
"""Per-US-slot JP-source alignment for one STGEVT block (the insertion bridge).

The DB pairs JP<->US positionally (box k == box k). That is WRONG for any block where
the US localization cut/merged boxes (e.g. block 12: JP has 30 more boxes than US), so
past the first edit the JP the agents translate is misaligned to the US slot it will be
inserted into.

This tool builds a trustworthy US-slot -> JP-box map for ONE block:
  1. The US disc box-stream index == the US# (verified), so the US side needs no alignment.
  2. Localization drift is LOCALLY LINEAR (block 12: 95% of slots share one constant offset),
     so we detect the dominant offset, then for each US slot pick the JP box in a small window
     that best matches on signals that SURVIVE localization:
        - examine-marker agreement  (US '*' / '@'  vs  JP '＊')
        - shared 2+ digit numbers
        - short-vs-short / long-vs-long box-length bucket
  3. Each slot gets a confidence: HIGH (unique strong match at the dominant offset),
     MED (match but off the dominant offset), LOW (weak/ambiguous -> human review).

Usage: python3 tools_wa2/slot_align.py <block> [--report] [--json out.json]

Prints the drift profile + a per-slot map, and flags the LOW-confidence slots (the real
localization edit points) for review. JSON output feeds the eventual inserter.
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W
from collections import Counter

RAW, USER, HDR = 2352, 2048, 24
US_BIN = "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin"
US_LBA, US_SIZE = 12586, 10813440

def rf(p, lba, size):
    o = bytearray(); n = (size + USER - 1) // USER
    with open(p, 'rb') as f:
        for s in range(n):
            f.seek((lba + s) * RAW + HDR); o += f.read(USER)
    return bytes(o[:size])

def msgs(d):
    o = []; i = -1
    while True:
        i = d.find(b'\x10\x0c', i + 1)
        if i < 0: break
        o.append(i)
    return o

def feats(txt, jp):
    f = {}
    f['examine'] = txt.lstrip().startswith('＊') if jp else txt.lstrip().startswith('*')
    f['nums'] = set(re.findall(r'\d{2,}', txt))
    f['short'] = len(txt.strip()) <= 6
    return f

def score(u, j):
    s = 0
    if u['examine'] == j['examine']: s += 2
    s += 3 * len(u['nums'] & j['nums'])
    if u['short'] == j['short']: s += 1
    return s

def align_block(blk):
    JD = W.load_jp(); UD = rf(US_BIN, US_LBA, US_SIZE)
    JM = msgs(JD); UM = msgs(UD)
    def jt(i): return W.decode_block(JD[JM[i] + 2:JM[i] + 2 + 400].split(b'\x00')[0], blk)
    def ut(i): return UD[UM[i] + 2:UM[i] + 2 + 400].split(b'\x00')[0].decode('ascii', 'replace')

    # locate this block's JP box range
    seg = W.block_bytes(JD, blk)
    seg_off = JD.find(seg[:64])
    jp_idx = [i for i, off in enumerate(JM) if seg_off <= off < seg_off + len(seg)]
    jp0, jpN = jp_idx[0], len(jp_idx)

    # US slots for this block: from DB
    db = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                      'game_script', 'wa2_db.json')))['rows']
    us_list = sorted(int(r['us']) for r in db if int(r['block']) == blk)
    us0 = us_list[0]; nUS = len(us_list)

    uf = {u: feats(ut(u), False) for u in us_list}
    jf = {ji: feats(jt(jp0 + ji), True) for ji in range(jpN)}

    # pass 1: per-slot best offset in window, to find the dominant drift
    WIN = range(-6, 16)
    chosen = {}
    for k, u in enumerate(us_list):
        best = None
        for dj in WIN:
            ji = k + dj
            if 0 <= ji < jpN:
                sc = score(uf[u], jf[ji])
                if best is None or sc > best[0]: best = (sc, dj)
        chosen[u] = best
    dom = Counter(chosen[u][1] for u in us_list).most_common(1)[0][0]

    # pass 2: assign map. Prefer the dominant offset; only deviate when it scores strictly better.
    out = []
    for k, u in enumerate(us_list):
        ji_dom = k + dom
        sc_dom = score(uf[u], jf[ji_dom]) if 0 <= ji_dom < jpN else -1
        # is there a strictly-better nearby offset?
        alt = None
        for dj in WIN:
            ji = k + dj
            if 0 <= ji < jpN and dj != dom:
                sc = score(uf[u], jf[ji])
                if sc > sc_dom and (alt is None or sc > alt[0]): alt = (sc, dj, ji)
        if alt and alt[0] >= sc_dom + 2:      # clearly better elsewhere -> real edit point
            conf = 'MED'; ji = alt[2]; sc = alt[0]
        else:
            ji = ji_dom; sc = sc_dom
            conf = 'HIGH' if sc >= 3 else 'LOW'
        out.append({'us': u, 'jp_box': jp0 + ji if 0 <= ji < jpN else None,
                    'jp_in_block': ji if 0 <= ji < jpN else None,
                    'offset': ji - k, 'score': sc, 'conf': conf})
    return {'block': blk, 'us0': us0, 'nUS': nUS, 'jp0': jp0, 'jpN': jpN,
            'dominant_offset': dom, 'slots': out}, jt, ut

if __name__ == '__main__':
    blk = int(sys.argv[1])
    res, jt, ut = align_block(blk)
    c = Counter(s['conf'] for s in res['slots'])
    print(f"### block {blk}: {res['nUS']} US slots, {res['jpN']} JP boxes, dominant offset {res['dominant_offset']:+d}")
    print(f"confidence: HIGH={c['HIGH']} MED={c['MED']} LOW={c['LOW']}  "
          f"({100*c['HIGH']/res['nUS']:.0f}% high)")
    print(f"\nLOW-confidence / edit-point slots (need review):")
    for s in res['slots']:
        if s['conf'] != 'HIGH':
            u = ut(s['us'])[:44].replace('\n', ' ')
            j = jt(s['jp_box'])[:36].replace('\n', ' ') if s['jp_box'] is not None else '(none)'
            print(f"  US#{s['us']} [{s['conf']} off{s['offset']:+d}] EN: {u!r}")
            print(f"            -> JP#{s['jp_box']}: {j!r}")
    if '--json' in sys.argv:
        out = sys.argv[sys.argv.index('--json') + 1]
        json.dump(res, open(out, 'w'), ensure_ascii=False, indent=1)
        print(f"\nwrote {out}")
