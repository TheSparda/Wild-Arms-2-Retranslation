#!/usr/bin/env python3
"""Print everything a translation agent needs for ONE lore-encyclopedia block (or a US# sub-range of it).

Usage: python3 tools/translate_agent_brief.py <block> [us_start] [us_end]

Emits every content box (US#, decoded JP, aligned EN) for the block (or the given
US# range, inclusive), marking which are jp_clean (fully decoded, translate from JP)
vs residual (some <b:xxxx>/<xxxx> codes remain, translate from EN + readable JP).
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W

blk = int(sys.argv[1])
us_start = int(sys.argv[2]) if len(sys.argv) > 2 else None
us_end = int(sys.argv[3]) if len(sys.argv) > 3 else None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db = json.load(open(os.path.join(ROOT, 'data/script', 'wa2_db.json')))['rows']
rows = [r for r in db if r['block'] == blk and r['en'].strip() and len(r['en'].strip()) >= 2]
if us_start is not None:
    rows = [r for r in rows if us_start <= r['us'] <= us_end]

# The DB `jp` field bleeds the NEXT message's bytes into each box (decode doesn't stop
# at the 0x00 terminator). Re-decode each box from the raw disc, truncated at its own
# 0x00, so agents get clean per-box JP instead of hand-fixing it.
_jd = W.load_jp()
_seg = W.block_bytes(_jd, blk)
_jm = []; _i = -1
while True:
    _i = _seg.find(b'\x10\x0c', _i + 1)
    if _i < 0: break
    _jm.append(_i)
def clean_box_jp(k):
    if k < 0 or k >= len(_jm): return None
    s = _jm[k] + 2
    e = _jm[k+1] if k+1 < len(_jm) else len(_seg)
    raw = _seg[s:e].split(b'\x00')[0]   # stop at this box's own terminator
    return ' '.join(W.decode_block(raw, blk).replace('\n', ' / ').split())
# map block-local in-block index (k) onto each row by counting 10 0c markers up to its US#
first_us = min(r['us'] for r in db if r['block'] == blk)
for r in rows:
    k = r['us'] - first_us
    fixed = clean_box_jp(k)
    if fixed is not None:
        r = r  # keep DB fields, override jp + recompute clean
        r['jp'] = fixed
        r['jp_clean'] = ('<' not in fixed) and bool(re.search(r'[぀-ヿ㐀-鿿]', fixed))

clean = [r for r in rows if r['jp_clean']]
residual = [r for r in rows if not r['jp_clean']]

print(f"### BLOCK {blk}: {len(rows)} content boxes ({len(clean)} clean-JP, {len(residual)} residual)\n")
print("## CLEAN-JP boxes (translate from JP; EN is a loose Rosetta reference only)")
for r in clean:
    print(f"[US#{r['us']}] JP: {r['jp'][:200]}")
    print(f"          EN: {r['en'][:150]}")
print(f"\n## RESIDUAL boxes ({len(residual)} — some kanji unsolved; use EN as primary, readable JP fragments as secondary)")
for r in residual:
    print(f"[US#{r['us']}] JP: {r['jp'][:200]}")
    print(f"          EN: {r['en'][:150]}")
