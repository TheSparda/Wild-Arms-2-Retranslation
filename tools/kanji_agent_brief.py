#!/usr/bin/env python3
"""Print everything a kanji-solving agent needs for ONE block, read-only.

Usage: python3 tools/kanji_agent_brief.py <block>

Emits, for the given STGEVT block:
  - ranked unsolved BLOCK-LOCAL codes (>=0x8a38) with in-block frequency + up to 5 contexts
  - the decoded JP for that block (unsolved codes shown as <b:xxxx>)
  - the aligned in-game EN for the same slots (Rosetta reference)
The agent reads this + WA2_KANJI_ENCODING.md + WA2_RE_STYLE_GUIDE.md and proposes solves.
It must NEVER write files; it returns structured proposals for the coordinator to verify.
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W
from collections import Counter

blk = int(sys.argv[1])
jd = W.load_jp()
seg = W.block_bytes(jd, blk)
dec = W.decode_block(seg, blk)

# ranked unsolved local codes with contexts
loc = Counter(); ctx = {}
for m in re.finditer(r'(.{0,6})<b:([0-9a-f]{4})>(.{0,6})', dec):
    c = m.group(2); loc[c] += 1
    ctx.setdefault(c, []).append((m.group(1)[-5:] + '○' + m.group(3)[:5]).replace('\n', ' '))

# cap output for dense blocks so agents don't time out chewing through huge briefs
TOPN = 25 if sum(loc.values()) > 400 else 60
ROWCAP = 60 if sum(loc.values()) > 400 else 999

print(f"### BLOCK {blk}: {sum(loc.values())} unsolved local occ, {len(loc)} distinct codes\n")
print(f"## RANKED UNSOLVED LOCAL CODES (top {TOPN} by frequency) — high freq = high value")
for c, n in loc.most_common(TOPN):
    print(f"b:{c} x{n:2}  " + ' | '.join(ctx[c][:5]))

# aligned EN via DB
db = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'data/script', 'wa2_db.json')))['rows']
rows = [r for r in db if r['block'] == blk and r['en'].strip()]
shown = 0
print(f"\n## DECODED JP  ||  ALIGNED EN  ({len(rows)} slots total, capped at {ROWCAP}) — use EN as the Rosetta meaning")
for r in rows:
    jp = r['jp'].strip()
    if '<b:' not in jp:   # only show slots that still carry an unsolved local code
        continue
    print(f"[US#{r['us']}] JP: {jp[:90]}")
    print(f"          EN: {r['en'][:88]}")
    shown += 1
    if shown >= ROWCAP:
        print(f"... ({len(rows)-shown} more slots omitted — use the ranked-code contexts above for those)")
        break
