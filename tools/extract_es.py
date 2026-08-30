#!/usr/bin/env python3
"""
Spanish (gadesx v1.01) box extractor — a THIRD, offset-exact witness for the box model.

WHY THIS IS GROUND TRUTH, AND WHAT IT IS *NOT*
  gadesx translated from the US release and patched the US disc in place. So:
    * ES pairs to EN by RAW OFFSET, exactly. 12,470 / 13,090 EN boxes (95.3%) have a Spanish
      box at the identical offset. No DP, no guessing, no `conf` flag — unlike the EN<->JP
      alignment in extract_boxes.align(), which is only ~38% accurate within +-1.
    * That makes ES an INDEPENDENT CONFIRMATION OF OUR BOX SEGMENTATION: a second human
      (working years ago, by hand, without our tooling) cut the script at the same boundaries
      we do. Where our EN box and the ES box at the same offset are not translations of each
      other, our segmentation is wrong there.
    * ES carries NO Japanese information. It is a daughter of the EN script, so it can never
      arbitrate an EN-vs-JP divergence. Do not use it to "check" the retranslation's meaning.

  What it IS good for:
    1. Box-model validation (above).
    2. FIT BUDGET. Every ES box is an existence proof that N characters fit in that box on real
       hardware. Measured, not assumed: median ES/EN length ratio is 0.89 and p90 is 1.02, i.e.
       gadesx mostly had to COMPRESS to fit -- but 14.3% of boxes do run longer than the English,
       and the longest shipped ES box is 359 chars. See --fit.
    3. Glyph slots. ES_MAP below is the set of font slots gadesx proved are repointable.

CHARACTER MAP (solved from context, verified against Spanish orthography)
  gadesx reused the unused ASCII symbol slots rather than extending the font:
    0x5c \\ -> ¡    0x5e ^ -> ¿    0x5f _ -> ñ    0x7b { -> ú
    0x7c | -> ó    0x7d } -> í    0x7e ~ -> é    0x7f     -> á
  Uppercase accents are not mapped; gadesx wrote capitals unaccented.

INPUT
  WA2_CD1_spanish.bin -- the US disc with the gadesx PPF applied (PPF-o-matic 3).
  Both that .bin and spanish_patch/ are gitignored: gadesx's patch is his work, not ours.

USAGE
  python3 tools/extract_es.py --block 3     # EN | ES side by side for one block
  python3 tools/extract_es.py --dump        # write data/script/es_boxes.json
  python3 tools/extract_es.py --fit         # measured box-length budget (the useful bit)
  python3 tools/extract_es.py --audit       # boxes where EN/ES disagree = suspect segmentation
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W
import extract_boxes as X

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ES_BIN = os.path.join(ROOT, 'WA2_CD1_spanish.bin')
OUT    = os.path.join(ROOT, 'data/script', 'es_boxes.json')
NBLK   = 120

ES_MAP = {0x5c: '¡', 0x5e: '¿', 0x5f: 'ñ', 0x7b: 'ú',
          0x7c: 'ó', 0x7d: 'í', 0x7e: 'é', 0x7f: 'á'}


def load():
    if not os.path.exists(ES_BIN):
        sys.exit(f"missing {ES_BIN}\n  -> apply spanish_patch/*CD1*(normal).ppf to a COPY of the US disc")
    return W.readfile(X.US_BIN, X.US_LBA, X.US_SIZE), W.readfile(ES_BIN, X.US_LBA, X.US_SIZE)


def es_boxes(ed, blk):
    return X.en_boxes(ed, blk, cmap=ES_MAP)


def joined(ud, ed, blk):
    """EN boxes for `blk`, each with the ES box at the SAME offset (or None). Offset-exact."""
    es = {(b['off'], b['sub']): b['text'] for b in es_boxes(ed, blk)}
    return [dict(b, es=es.get((b['off'], b['sub']))) for b in X.en_boxes(ud, blk)]


def main():
    ud, ed = load()
    a = sys.argv

    if '--block' in a:
        blk = int(a[a.index('--block') + 1])
        for b in joined(ud, ed, blk):
            if b['panel']:
                continue
            print(f"0x{b['off']:06x}  EN {b['text'][:78]}")
            print(f"          ES {b['es'][:78] if b['es'] else '-- (no ES box at this offset)'}\n")
        return

    rows = []
    for blk in range(NBLK):
        for b in joined(ud, ed, blk):
            rows.append({'blk': blk, 'off': b['off'], 'sub': b['sub'], 'en': b['text'],
                         'es': b['es'], 'panel': b['panel']})
    hit = [r for r in rows if r['es']]

    if '--fit' in a:
        # Measured budget: ES proves this many chars fit in a box that held this much EN.
        ratio = sorted(len(r['es']) / max(1, len(r['en'])) for r in hit)
        longest = max(hit, key=lambda r: len(r['es']))
        over = [r for r in hit if len(r['es']) > len(r['en'])]
        print(f"joined boxes            {len(hit):,} / {len(rows):,} EN ({len(hit)/len(rows)*100:.1f}%)")
        print(f"ES/EN length ratio      median {ratio[len(ratio)//2]:.2f}   "
              f"p90 {ratio[int(len(ratio)*.9)]:.2f}   max {ratio[-1]:.2f}")
        print(f"ES longer than EN       {len(over):,} boxes ({len(over)/len(hit)*100:.1f}%) "
              f"-- each one proves the EN length is NOT the ceiling")
        print(f"longest shipped ES box  {len(longest['es'])} chars (EN was {len(longest['en'])})")
        print(f"  blk {longest['blk']} 0x{longest['off']:x}: {longest['es'][:110]}")
        print("\nBUDGET RULE: a retranslated box may run to at least the ES length at that offset;")
        print("gadesx shipped it and the game does not freeze.")
        return

    if '--audit' in a:
        # THE honest segmentation signal. gadesx patched the US disc in place, so if our EN box
        # at (off,sub) is a real box, a Spanish box must sit at the same (off,sub). Where none
        # does, one of the two extractions is cutting the script wrong -- that is a lead.
        # (A token-overlap check was tried here and dropped: translation legitimately replaces
        # every long word, so it flagged 39% of correct pairs. It measured nothing.)
        miss = [r for r in rows if not r['es']]
        byblk = {}
        for r in miss:
            byblk[r['blk']] = byblk.get(r['blk'], 0) + 1
        print(f"{len(miss):,} / {len(rows):,} EN boxes ({len(miss)/len(rows)*100:.1f}%) have NO ES box "
              f"at the same (off,sub) -- suspect segmentation")
        worst = sorted(byblk.items(), key=lambda kv: -kv[1])[:8]
        print("worst blocks: " + ', '.join(f"blk{b}={n}" for b, n in worst))
        print("\nsample (EN text with no Spanish counterpart at its offset):")
        for r in miss[:10]:
            print(f"  blk {r['blk']} 0x{r['off']:x}.{r['sub']}  {r['en'][:72]}")
        return

    if '--dump' in a:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        json.dump({'charmap': {f'{k:#04x}': v for k, v in ES_MAP.items()},
                   'joined': len(hit), 'en_total': len(rows), 'rows': rows},
                  open(OUT, 'w'), ensure_ascii=False)
        print(f"wrote {OUT}: {len(rows):,} EN boxes, {len(hit):,} with an offset-exact ES pair")
        return

    print(__doc__)


if __name__ == '__main__':
    main()
