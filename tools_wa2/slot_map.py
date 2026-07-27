#!/usr/bin/env python3
"""Build the insertion slot map for one block: which US (English) box slot each translated
JP box's RE should be patched into.

Method (EN<->LIT English matching — possible now that translations exist):
  1. Collect this block's translated boxes from insert/*FINAL*.txt / *PROPAGATED.txt:
     positional label US#, its JP in-block index k = US# - first_us, and its LIT (fallback RE)
     English text.
  2. For each translated box, token-match its LIT against the ORIGINAL US EN of every slot in a
     window around k. Score = |shared content words| / |LIT content words| (stopwords dropped).
  3. Anchors = matches with score >= MIN_SCORE and a clear margin over the runner-up.
  4. Longest-increasing-subsequence over anchors (monotonicity kills mispairs).
  5. Non-anchored boxes between two LIS anchors that AGREE on offset inherit it (MED).
     Runs where brackets DISAGREE are flagged REVIEW — a localization cut/merge sits inside.

Output: insert/slot_map_blk<N>.json
  { "block": N, "entries": [ {jp_k, label_us, mapped_us, offset, conf, score} ], stats }

conf: ANCHOR (direct English match), BRACKET (inherited offset), REVIEW (bracket disagreement
or no bracket). Per feedback-verify-tool-claims: treat these as *candidates* — spot-check
before trusting; the tool prints samples for exactly that.

Usage: python3 tools_wa2/slot_map.py <block> [--window 12] [--min-score 0.34]
"""
import sys, os, re, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, USER, HDR = 2352, 2048, 24
US_BIN = os.path.join(ROOT, "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin")
US_LBA, US_SIZE = 12586, 10813440

STOP = set('''the a an and or but of to in on at is are was were be been it its this that these
those i you he she we they me him her us them my your his our their not no yes do does did done
will would can could should must may might have has had if then than so as for with from by'''.split())

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

def toks(s):
    return set(w for w in re.findall(r"[a-z']+", s.lower()) if len(w) > 2 and w not in STOP)

def build(blk, window=12, min_score=0.34):
    UD = rf(US_BIN, US_LBA, US_SIZE); UM = msgs(UD)
    def ut(i):
        return UD[UM[i] + 2:UM[i] + 2 + 500].split(b'\x00')[0].decode('ascii', 'replace')

    db = json.load(open(os.path.join(ROOT, 'game_script', 'wa2_db.json')))['rows']
    us_list = sorted(int(r['us']) for r in db if int(r['block']) == blk)
    first_us, last_us = us_list[0], us_list[-1]

    # translated boxes for this block: label US# -> LIT (fallback: RE joined)
    lits = {}
    for f in glob.glob(os.path.join(ROOT, 'insert', '*.txt')):
        t = open(f, errors='ignore').read()
        if 'RE :' not in t: continue
        for m in re.finditer(r'\[US#(\d+)\][^\n]*\n(.*?)(?=\n\[US#|\Z)', t, re.S):
            us = int(m.group(1))
            if not (first_us <= us <= last_us): continue
            lm = re.search(r'  LIT: (.*?)\n', m.group(2))
            body = lm.group(1) if lm else None
            if not body:
                # RE with its 7-space continuation lines (propagated files have no LIT)
                rm = re.search(r'  RE : (.*?)(?=\n(?!       )|\Z)', m.group(2), re.S)
                body = ' '.join(rm.group(1).split()) if rm else None
            if body and not body.strip().startswith('['):
                lits.setdefault(us, body)

    us_toks = {u: toks(ut(u)) for u in range(max(0, first_us - window), min(len(UM), last_us + window + 1))}

    # pass 1: anchors by best-in-window English match
    anchors = []
    for label_us, lit in sorted(lits.items()):
        lt = toks(lit)
        if len(lt) < 4: continue
        k = label_us  # positional guess: label already = first_us + jp_k
        cands = []
        for u in range(max(first_us, k - window), min(last_us, k + window) + 1):
            ovl = len(lt & us_toks.get(u, set()))
            cands.append((ovl / max(1, len(lt)), u))
        cands.sort(reverse=True)
        best, second = cands[0], (cands[1] if len(cands) > 1 else (0, -1))
        if best[0] >= min_score and best[0] >= second[0] + 0.12:
            anchors.append((label_us, best[1], round(best[0], 2)))

    # pass 2: LIS on (label_us, mapped_us) — strictly increasing in mapped_us
    import bisect
    seq = sorted(anchors)
    tails, tidx, parent = [], [], [-1] * len(seq)
    for i, (_, mu, _) in enumerate(seq):
        p = bisect.bisect_left(tails, mu)
        if p == len(tails): tails.append(mu); tidx.append(i)
        else: tails[p] = mu; tidx[p] = i
        parent[i] = tidx[p - 1] if p > 0 else -1
    lis = []
    cur = tidx[-1] if tidx else -1
    while cur != -1:
        lis.append(seq[cur]); cur = parent[cur]
    lis.reverse()
    # shift-confirmation guard: a LONE anchor whose offset differs from BOTH neighbors is
    # likely a false word-overlap match (e.g. sword/wield/Filgaia matching the wrong line).
    # Require a shifted offset to be confirmed by 2+ consecutive anchors OR score >= 0.8.
    pruned = []
    for i, (a, mu, sc) in enumerate(lis):
        off = mu - a
        prev_off = (lis[i-1][1] - lis[i-1][0]) if i > 0 else None
        next_off = (lis[i+1][1] - lis[i+1][0]) if i + 1 < len(lis) else None
        lone = (prev_off is not None and off != prev_off) and (next_off is not None and off != next_off)
        if lone and sc < 0.8:
            continue
        pruned.append((a, mu, sc))
    lis = pruned

    # pass 3: assign every translated box
    entries = []
    lis_by_label = {a: (b, s) for a, b, s in lis}
    labels = sorted(lits.keys())
    for label in labels:
        if label in lis_by_label:
            mu, sc = lis_by_label[label]
            entries.append({'label_us': label, 'mapped_us': mu, 'offset': mu - label,
                            'conf': 'ANCHOR', 'score': sc})
    # bracket interpolation for non-anchored
    anch = [(e['label_us'], e['offset']) for e in entries]
    for label in labels:
        if label in lis_by_label: continue
        left = max((a for a in anch if a[0] < label), default=None, key=lambda x: x[0])
        right = min((a for a in anch if a[0] > label), default=None, key=lambda x: x[0])
        if left and right and left[1] == right[1]:
            entries.append({'label_us': label, 'mapped_us': label + left[1], 'offset': left[1],
                            'conf': 'BRACKET', 'score': None})
        else:
            off = left[1] if left else (right[1] if right else 0)
            entries.append({'label_us': label, 'mapped_us': label + off, 'offset': off,
                            'conf': 'REVIEW', 'score': None})
    entries.sort(key=lambda e: e['label_us'])
    stats = {'translated': len(labels), 'anchors_raw': len(anchors), 'anchors_lis': len(lis),
             'ANCHOR': sum(1 for e in entries if e['conf'] == 'ANCHOR'),
             'BRACKET': sum(1 for e in entries if e['conf'] == 'BRACKET'),
             'REVIEW': sum(1 for e in entries if e['conf'] == 'REVIEW')}
    return {'block': blk, 'first_us': first_us, 'entries': entries, 'stats': stats}, ut, lits

if __name__ == '__main__':
    blk = int(sys.argv[1])
    window = int(sys.argv[sys.argv.index('--window') + 1]) if '--window' in sys.argv else 12
    ms = float(sys.argv[sys.argv.index('--min-score') + 1]) if '--min-score' in sys.argv else 0.34
    res, ut, lits = build(blk, window, ms)
    print(f"block {blk}: {res['stats']}")
    from collections import Counter
    offs = Counter(e['offset'] for e in res['entries'])
    print("offset distribution:", dict(sorted(offs.items())))
    out = os.path.join(ROOT, 'insert', f'slot_map_blk{blk}.json')
    json.dump(res, open(out, 'w'), indent=1)
    print(f"wrote {out}")
    # spot-check samples: 6 ANCHOR spread across the block + all REVIEW (capped 10)
    ent = res['entries']
    anc = [e for e in ent if e['conf'] == 'ANCHOR']
    print("\n--- SPOT-CHECK: 6 anchors (does LIT really describe the mapped EN slot?) ---")
    for e in anc[::max(1, len(anc) // 6)][:6]:
        print(f"label US#{e['label_us']} -> slot {e['mapped_us']} (off {e['offset']:+d}, score {e['score']})")
        print(f"   LIT: {lits[e['label_us']][:90]}")
        print(f"   EN : {ut(e['mapped_us'])[:90]}")
    rev = [e for e in ent if e['conf'] == 'REVIEW']
    print(f"\n--- REVIEW slots ({len(rev)}) ---")
    for e in rev[:10]:
        print(f"label US#{e['label_us']} (off {e['offset']:+d}): LIT: {lits[e['label_us']][:70]}")
