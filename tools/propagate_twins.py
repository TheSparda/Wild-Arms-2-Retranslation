#!/usr/bin/env python3
"""Payload-propagate translated RE across the 6/7/8/9/10/11 lore-twin cluster.

Blocks 8/9/11 (and 6/7/10) reuse the same encyclopedia script, but at SHIFTED box
positions, not the same index. So we key on the EXACT JP box payload (the raw bytes
between one 10 0c marker and its 00 terminator). For each target box we look up its
payload in the index of already-translated boxes and copy that RE verbatim (name-slot
codes like {0}/[05] are byte-identical in identical payloads, so they transfer safely).

Builds a FINAL file per target block containing only the auto-filled boxes, tagged so a
human can see they came from propagation. Boxes with no payload match are listed as gaps
(they are the block's unique content, still needing translation).

Usage: python3 tools/propagate_twins.py <target_block> [more_blocks...]
       python3 tools/propagate_twins.py 9 11 8    # fill 9, 11, and block-8 gaps
"""
import sys, os, re, glob, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JD = W.load_jp()
# source blocks (translated lore twins) + any extra targets passed on the CLI get added below
CLUSTER = [6, 7, 8, 9, 10, 11, 21, 26]

def block_payloads(blk):
    """Return list of (in_block_index, raw_payload_bytes) for a block."""
    seg = W.block_bytes(JD, blk)
    marks = []; i = -1
    while True:
        i = seg.find(b'\x10\x0c', i + 1)
        if i < 0: break
        marks.append(i)
    out = []
    for k, m in enumerate(marks):
        s = m + 2; e = marks[k + 1] if k + 1 < len(marks) else len(seg)
        out.append((k, seg[s:e].split(b'\x00')[0]))
    return out

def is_trivial(pl):
    """A payload too generic to safely key on: empty, or a bare control code with no
    real text. Many boxes share these (e.g. b'\\x17'), so matching on them mis-propagates."""
    if pl is None or len(pl) < 4:
        return True
    # decode and require at least 4 real (kana/kanji/ascii-letter) chars
    txt = W.decode_block(pl, 6)
    real = re.sub(r'<[^>]*>|\[[^\]]*\]|[\s　/]', '', txt)
    real = re.sub(r'[^0-9A-Za-z぀-ヿ㐀-鿿]', '', real)
    return len(real) < 4

def norm_text(pl, blk):
    """Normalized decoded text key: strip unsolved <...> / [..] codes + spacing so the SAME
    line matches across twins even when their block-local kanji tables differ (raw bytes differ,
    decoded readable text is identical). Requires >=6 real chars to avoid generic collisions."""
    if pl is None:
        return None
    t = W.decode_block(pl, blk)
    key = re.sub(r'<[^>]*>|\[[^\]]*\]|[\s　/〜ッ]', '', t)
    real = re.sub(r'[^0-9A-Za-z぀-ヿ㐀-鿿]', '', key)
    return key if len(real) >= 6 else None

db = json.load(open(os.path.join(ROOT, 'data/script', 'wa2_db.json')))['rows']
def first_us(blk): return min(int(r['us']) for r in db if int(r['block']) == blk)
def block_of(us):
    for b in CLUSTER:
        ul = [int(r['us']) for r in db if int(r['block']) == b]
        if ul and min(ul) <= us <= max(ul): return b
    return None
def en_ok(blk, us):
    r = [x for x in db if int(x['block']) == blk and int(x['us']) == us]
    return bool(r) and len(r[0]['en'].strip()) >= 2

FU = {b: first_us(b) for b in CLUSTER}
BX = {b: block_payloads(b) for b in CLUSTER}

# Build indexes from every translated lore FINAL file: exact-payload AND normalized-text.
pay2re = {}       # raw JP payload bytes -> RE (exact twin match)
txt2re = {}       # normalized decoded text -> RE (cross-table twin match)
RE_RX = re.compile(r'\[US#(\d+)\](.*?)(?=\n\[US#|\Z)', re.S)
BODY_RX = re.compile(r'  RE : (.*?)(?=\n  (?:JP|LIT|EN) :|\n#|\n\[US#|\n\n|\Z)', re.S)
for f in glob.glob(os.path.join(ROOT, 'translation/insert', 'lore_blk*_FINAL.txt')):
    t = open(f).read()
    for m in RE_RX.finditer(t):
        us = int(m.group(1)); bm = BODY_RX.search(m.group(2))
        if not bm: continue
        re_txt = bm.group(1).rstrip()
        if re_txt.strip().startswith('['):  # [SKIP...] annotations are not real RE
            continue
        b = block_of(us)
        if b is None: continue
        k = us - FU[b]
        if 0 <= k < len(BX[b]):
            pl = BX[b][k][1]
            if pl and b'\x10\x0c' not in pl and not is_trivial(pl):
                pay2re.setdefault(pl, re_txt)
                nk = norm_text(pl, b)
                if nk: txt2re.setdefault(nk, re_txt)

# Which US# are already translated (any RE-bearing file), so we don't overwrite.
done_us = set()
for f in glob.glob(os.path.join(ROOT, 'translation/insert', '*.txt')):
    t = open(f, errors='ignore').read()
    if t.count('RE :') < 1: continue
    for m in re.finditer(r'\[US#(\d+)\]', t): done_us.add(int(m.group(1)))

def propagate(blk):
    fu = FU[blk]; filled = []; gaps = []
    for k, pl in BX[blk]:
        us = fu + k
        if not en_ok(blk, us): continue
        if us in done_us: continue          # already has a real translation
        if is_trivial(pl):                   # control-only/empty box: not a fillable slot
            continue
        re_txt = None; how = None
        if pl in pay2re:
            re_txt, how = pay2re[pl], 'exact'
        else:
            nk = norm_text(pl, blk)          # cross-table twin: same text, different kanji codes
            if nk and nk in txt2re:
                re_txt, how = txt2re[nk], 'text'
        if re_txt is not None:
            jp = ' '.join(W.decode_block(pl, blk).replace('\n', ' / ').split())
            filled.append((us, jp, re_txt, how))
        else:
            gaps.append(us)
    return filled, gaps

if __name__ == '__main__':
    targets = [int(x) for x in sys.argv[1:]] or [9, 11]
    print(f"payload index: {len(pay2re)} unique translated payloads\n")
    for blk in targets:
        filled, gaps = propagate(blk)
        outp = os.path.join(ROOT, 'translation/insert', f'lore_blk{blk}_PROPAGATED.txt')
        with open(outp, 'w') as o:
            o.write(f"# WA2 — Block {blk} — PROPAGATED from lore-twin cluster (payload-exact match)\n")
            o.write(f"# Auto-filled by tools/propagate_twins.py from already-translated twin boxes.\n")
            o.write(f"# Each RE is copied verbatim from a byte-identical JP box elsewhere in the 6/7/8/9/10/11\n")
            o.write(f"# cluster. {len(filled)} boxes filled; {len(gaps)} unique boxes still need translation.\n")
            o.write(f"# match: 'exact' = byte-identical payload; 'text' = same decoded text, different kanji table.\n\n")
            for us, jp, re_txt, how in filled:
                o.write(f"[US#{us}] (propagated:{how})\n")
                o.write(f"  JP : {jp[:200]}\n")
                o.write(f"  RE : {re_txt}\n\n")
        print(f"block {blk}: filled {len(filled)}, gaps {len(gaps)} -> {os.path.basename(outp)}")
        if gaps:
            # compress gap ranges
            runs = []; s = p = gaps[0]
            for u in gaps[1:]:
                if u == p + 1: p = u
                else: runs.append((s, p)); s = p = u
            runs.append((s, p))
            print("   gap ranges: " + ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in runs))
