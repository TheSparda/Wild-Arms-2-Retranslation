#!/usr/bin/env python3
"""
Unified box extractor — the CORRECT model for WA2 STGEVT dialogue, for BOTH languages.

Supersedes the buggy `10 0c`-split logic in build_db.py (us_slots/uen + jp_by_block), which
treated one `\x10\x0c`-delimited segment as one box. That marker is an event OPCODE; each gap
between markers holds MANY boxes. See memory: wa2-extraction-two-framings.

CORRECT MODEL (verified on blocks 24/3/12/17):
  A dialogue box is a text run that ends at NUL (0x00), opened by a FRAME byte:
    \x10\x0c   indexed box   (the only kind the old dumper half-caught)
    \x06       inline event box open
    \x0d       continuation / nameplate+text
  EN runs then start with `@` (0x40) + ASCII.
  JP runs then start with an SJIS lead byte (0x81-0x9f, 0xe0-0xef): 「=81 75, ＊=81 96, 『=81 71.

ALIGNMENT (verified): within a block, EN and JP story boxes appear in the SAME ORDER. JP has a
few extra nameplate/continuation splits, so pair by ORDERED sequence match, not raw index.
(Positional index pairing is INVALID: EN blk24=45 boxes, JP blk24=79 story boxes, JBLK!=UBLK.)

USAGE
  python3 tools_wa2/extract_boxes.py --block 24        # show aligned EN|JP for one block
  python3 tools_wa2/extract_boxes.py --dump            # write game_script/boxes.json (all blocks)
  python3 tools_wa2/extract_boxes.py --verify          # spot-check known Brad's-Intro lines
"""
import os, sys, json, difflib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, 'game_script', 'boxes.json')
US_BIN = os.path.join(ROOT, 'Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin')
US_LBA, US_SIZE, UBLK = 12586, 10813440, 90112
JBLK = W.JBLK


def _is_jp_lead(b):
    return 0x81 <= b <= 0x9f or 0xe0 <= b <= 0xef


def _extract(data, lo, hi, jp, blk=0):
    """Return ordered list of dialogue boxes in [lo,hi). Each: {off, text, indexed, panel}."""
    out = []; i = lo; hi = min(hi, len(data))
    while i < hi - 1:
        b = data[i]; frame = None
        if b == 0x10 and data[i+1] == 0x0c: frame = 'idx'; i += 1
        elif b == 0x06: frame = 'inline'
        elif b == 0x0d: frame = 'cont'
        if frame:
            s = i + 1
            if s >= hi:
                i += 1; continue
            ok = _is_jp_lead(data[s]) if jp else (data[s] == 0x40)
            if ok:
                if not jp: s += 1                        # skip the '@'
                k = s
                while k < hi and data[k] != 0x00: k += 1
                chunk = data[s:k]
                # a run may bundle several logical boxes separated by an internal \x10\x0c
                # (JP especially: "逃亡者「...\x10\x0c「..."). Split so EN/JP box counts match.
                for sub in chunk.split(b'\x10\x0c'):
                    if not sub: continue
                    if jp:
                        t = ' '.join(W.decode_block(sub, blk).replace('\n', ' ').split())
                        cjk = sum(1 for c in t if '぀' <= c <= 'ヿ' or '一' <= c <= '鿿')
                        good = cjk >= 2
                        panel = t.lstrip('「『 ').startswith('＊')
                    else:
                        # each sub may itself start with '@'; strip a leading one
                        raw = sub[1:] if sub[:1] == b'@' else sub
                        t = ''.join(chr(x) if 0x20 <= x < 0x7f else (' ' if x == 0x0d else '')
                                    for x in raw)
                        t = ' '.join(t.split())
                        good = sum(c.isalpha() for c in t) >= 2
                        panel = t.startswith('*')
                    if good:
                        out.append({'off': i, 'text': t, 'indexed': frame == 'idx', 'panel': panel})
                i = k; continue
        i += 1
    return out


def en_boxes(ud, blk):
    return _extract(ud, blk * UBLK, (blk + 1) * UBLK, jp=False)


def jp_boxes(jd, blk):
    return _extract(jd, blk * JBLK, (blk + 1) * JBLK, jp=True, blk=blk)


def align(enb, jpb):
    """Pair EN story boxes to JP story boxes by ORDERED position (best available, not perfect).

    VERIFIED on block 24: story boxes run in the same order in both languages and match 1:1
    for long stretches (boxes 0-20 pair semantically exactly). Residual drift of +-1..2 appears
    where JP splits a nameplate into its own box that EN inlines, so DO NOT trust the pairing
    blindly deep in a block — the JP column is a strong hint to be eyeball-confirmed against the
    EN at translation time, never an authoritative 1:1 map. (A content-based cross-language
    aligner was attempted and abandoned: no reliable language-agnostic signal.) Panels are
    paired within their own stream. Nameplate-only JP boxes (「-name lines) stay attached to the
    following dialogue by the internal-\\x10\\x0c split already done in _extract."""
    en_story = [b['text'] for b in enb if not b['panel']]
    jp_story = [b['text'] for b in jpb if not b['panel']]
    pairs = []
    for i in range(max(len(en_story), len(jp_story))):
        pairs.append({'i': i,
                      'en': en_story[i] if i < len(en_story) else '',
                      'jp': jp_story[i] if i < len(jp_story) else ''})
    return pairs, len(en_story), len(jp_story)


def main():
    ud = W.readfile(US_BIN, US_LBA, US_SIZE)
    jd = W.load_jp()

    if '--block' in sys.argv:
        blk = int(sys.argv[sys.argv.index('--block') + 1])
        enb = en_boxes(ud, blk); jpb = jp_boxes(jd, blk)
        pairs, ne, nj = align(enb, jpb)
        print(f"block {blk}: EN boxes={len(enb)} (story {ne}), JP boxes={len(jpb)} (story {nj})")
        print("=== aligned story boxes (ordered sequence) ===")
        for p in pairs:
            print(f"[{p['i']:>3}] EN: {p['en'][:52]}")
            print(f"      JP: {p['jp'][:44]}")
        return

    if '--verify' in sys.argv:
        enb = en_boxes(ud, 24); jpb = jp_boxes(jd, 24)
        pairs, ne, nj = align(enb, jpb)
        probes = ['chased him', 'Barghests', 'Point 12', 'a puppy', 'Namumi']
        print("=== VERIFY block 24 (Brad's Intro) EN|JP pairing ===")
        for p in pairs:
            if any(pr.lower() in p['en'].lower() for pr in probes):
                print(f"  EN: {p['en'][:48]}\n  JP: {p['jp'][:40]}\n")
        return

    if '--dump' in sys.argv:
        nblocks = min(len(ud) // UBLK, len(jd) // JBLK) + 1
        allboxes = {}
        for blk in range(nblocks):
            enb = en_boxes(ud, blk); jpb = jp_boxes(jd, blk)
            if not enb and not jpb: continue
            pairs, ne, nj = align(enb, jpb)
            allboxes[blk] = {'en_total': len(enb), 'jp_total': len(jpb),
                             'en_story': ne, 'jp_story': nj, 'pairs': pairs}
        json.dump(allboxes, open(OUT, 'w'), ensure_ascii=False)
        tot_en = sum(v['en_total'] for v in allboxes.values())
        tot_jp = sum(v['jp_total'] for v in allboxes.values())
        print(f"wrote {OUT}: {len(allboxes)} blocks, {tot_en} EN boxes, {tot_jp} JP boxes")
        return

    print(__doc__)


if __name__ == '__main__':
    main()
