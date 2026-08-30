#!/usr/bin/env python3
"""Regenerate web/data/jp_tables.json from the canonical Python tables.
Run from repo root whenever tools/wa2_kanji_map.py or font_work/block_tables.json change:
    python3 web/gen_tables.py
Also (re)writes web/tests/fixtures/jp_golden.json — the Python decoder's output for two
blocks, which web/tests/jp.test.mjs holds the JS port to, byte-for-byte."""
import sys, json, os
sys.path.insert(0, 'tools')
import wa2_jp_decode as W
import extract_boxes as X

tables = {
    'kanji': {k.hex(): v for k, v in W.KANJI.items()},
    'blocks': json.load(open('font_work/block_tables.json')),
    'f0': {f'{k:02x}': v for k, v in W.F0.items()},
    'kata': {f'{k:02x}': v for k, v in W.KATA.items()},
}
os.makedirs('web/data', exist_ok=True)
json.dump(tables, open('web/data/jp_tables.json', 'w'), ensure_ascii=False)
print(f"web/data/jp_tables.json: {len(tables['kanji'])} kanji, {len(tables['blocks'])} block tables")

# golden fixture: jp_boxes + align output for two verified blocks
jd = W.load_jp()
ud = W.readfile(X.US_BIN, X.US_LBA, X.US_SIZE)
gold = {}
for blk in (3, 24):
    enb = X.en_boxes(ud, blk); jpb = X.jp_boxes(jd, blk)
    pairs, n, m = X.align(enb, jpb)
    gold[str(blk)] = {
        'jp': [{'off': b['off'], 'sub': b['sub'], 'text': b['text'], 'panel': b['panel']} for b in jpb],
        'pairs': pairs, 'n': n, 'm': m,
    }
os.makedirs('web/tests/fixtures', exist_ok=True)
json.dump(gold, open('web/tests/fixtures/jp_golden.json', 'w'), ensure_ascii=False)
print(f"golden: blk3 jp={len(gold['3']['jp'])} pairs={len(gold['3']['pairs'])}, blk24 jp={len(gold['24']['jp'])}")
