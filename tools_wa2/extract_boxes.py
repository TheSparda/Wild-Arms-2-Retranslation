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


def _decode_en(raw, cmap=None):
    """Decode an EN payload run. Handles the box framings the earlier @-only pass missed:
       @text                      classic
       Speaker\rtext              speaker-prefixed (\x06 Musketeer A \x0d (Did you...))
       \x05 N \r (text)           name-coded thought/paren box (\x06 \x05 0 \x0d (Draw...))
    Returns (display_text, stray_control_count). \x05 N is a name/speaker selector (dropped),
    \n-digit is a {n} name code (kept), \r is a line break (space), @ is the box-open (dropped).

    `cmap` remaps byte->glyph before the ASCII gate. The gadesx Spanish patch reuses the unused
    ASCII symbol slots for accented glyphs (see ES_MAP in extract_es.py); without the map those
    bytes fall through to the stray-control counter and the box gets rejected as binary."""
    out = []; j = 0; ctrl = 0
    n = len(raw)
    while j < n:
        b = raw[j]
        if b == 0x0a and j + 1 < n and 0x30 <= raw[j+1] <= 0x39:
            out.append('{' + chr(raw[j+1]) + '}'); j += 2; continue
        if b == 0x05 and j + 1 < n:              # name/speaker selector: drop marker + arg
            j += 2; continue
        if cmap and b in cmap:                   # remapped glyph slot (e.g. ES accents)
            out.append(cmap[b]); j += 1; continue
        if b == 0x40:                            # '@' box-open, not displayed
            j += 1; continue
        if 0x20 <= b < 0x7f:
            out.append(chr(b)); j += 1; continue
        if b == 0x0d:
            out.append(' '); j += 1; continue
        ctrl += 1; j += 1                         # any other control byte
    return ' '.join(''.join(out).split()), ctrl


def _extract(data, lo, hi, jp, blk=0, cmap=None):
    """Return ordered list of dialogue boxes in [lo,hi). Each: {off, text, indexed, panel}.

    A box = a run from a frame byte (\x10\x0c idx / \x06 inline / \x0d cont) to NUL, split on
    any internal \x10\x0c. Accepts ANY text run after the frame (not only @-led): speaker-
    prefixed and name-coded parenthetical boxes were being dropped by the earlier @-only gate.
    Binary/opcode runs are rejected by a letters>=3 + low stray-control-density test."""
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
            k = s
            while k < hi and data[k] != 0x00: k += 1
            chunk = data[s:k]
            emitted = False
            nsub = 0
            for sub in chunk.split(b'\x10\x0c'):
                if not sub: continue
                if jp:
                    # JP runs must start with an SJIS lead / kana / speaker-name char, else the
                    # run is a binary/opcode gap (removing this gate ballooned JP ~3x with junk).
                    if not (_is_jp_lead(sub[0]) if sub else False):
                        continue
                    t = ' '.join(W.decode_block(sub, blk).replace('\n', ' ').split())
                    cjk = sum(1 for c in t if '぀' <= c <= 'ヿ' or '一' <= c <= '鿿')
                    kana = sum(1 for c in t if '぀' <= c <= 'ゟ' or '゠' <= c <= 'ヿ')
                    good = cjk >= 2 or kana >= 3
                    panel = t.lstrip('「『 ').startswith('＊')
                else:
                    t, ctrl = _decode_en(sub, cmap)
                    letters = sum(c.isalpha() for c in t)
                    good = letters >= 3 and ctrl <= max(2, len(t) // 8)
                    panel = t.lstrip('({ ').startswith('*')
                if good:
                    # `off` is the FRAME byte, so every sub-box of one \x10\x0c chunk shares it
                    # (36.6% of boxes). `sub` disambiguates -- (off, sub) is the real box key,
                    # and it is what the EN<->ES offset join must pair on.
                    out.append({'off': i, 'sub': nsub, 'text': t,
                                'indexed': frame == 'idx', 'panel': panel})
                    nsub += 1
                    emitted = True
            if emitted and k > s:
                i = k; continue
        i += 1
    return out


def en_boxes(ud, blk, cmap=None):
    return _extract(ud, blk * UBLK, (blk + 1) * UBLK, jp=False, cmap=cmap)


def jp_boxes(jd, blk):
    return _extract(jd, blk * JBLK, (blk + 1) * JBLK, jp=True, blk=blk)


import re as _re, unicodedata as _ud


def _digits(s):
    return ''.join(_re.findall(r'\d', _ud.normalize('NFKC', s or '')))


def _pair_score(en, jp):
    """Language-agnostic EN<->JP box similarity. Deliberately weak: surface features only.
    A shared multi-digit run (survives translation, e.g. Point 12 <-> ポイント１２) is near-certain;
    length ratio is a faint hint. Empirically this tops out ~38% within +-1 (see align docstring)."""
    de, dj = _digits(en), _digits(jp)
    if de and dj and de == dj and len(de) >= 2:
        return 3.0
    le, lj = len(en), len(jp)
    if le < 2 or lj < 2:
        return 0.0
    return max(0.0, 1 - abs(le / lj - 1.7) / 2.5) * 0.4


def align(enb, jpb, diag=1.0, gap=-0.05):
    """Monotonic DP alignment of EN<->JP story boxes. EN boxes are AUTHORITATIVE (never dropped);
    each gets the JP box the DP pairs it to, or '' if the DP inserts a gap there.

    HONEST ACCURACY: ~38% of pairs land within +-1 of the true match on a 285-pair hand-aligned
    validation set (positional zip scored 0%). The drift between EN and JP box counts is monotonic
    (JP boxes drop out progressively; 102/120 blocks differ by >2) but surface features are too
    sparse to place the gaps reliably. So each pair carries a `conf`:
      'anchor' — matched on a shared digit-run (trust it)
      'approx' — DP's best guess (VERIFY against EN before using the JP)
    A definitive pairing requires reading the text (LLM/human). Panels align within their own
    stream. See memory: wa2-extraction-two-framings."""
    en_story = [b['text'] for b in enb if not b['panel']]
    jp_story = [b['text'] for b in jpb if not b['panel']]
    n, m = len(en_story), len(jp_story)
    NEG = -1e9
    dp = [[NEG] * (m + 1) for _ in range(n + 1)]
    bt = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            c = dp[i][j]
            if c == NEG and (i or j):
                continue
            if i < n and j < m:
                s = _pair_score(en_story[i], jp_story[j])
                pri = diag * (1 - abs(i / max(n, 1) - j / max(m, 1)))
                v = c + s + pri
                if v > dp[i+1][j+1]:
                    dp[i+1][j+1] = v; bt[i+1][j+1] = (i, j)
            if i < n and c + gap > dp[i+1][j]:
                dp[i+1][j] = c + gap; bt[i+1][j] = (i, j)
            if j < m and c + gap > dp[i][j+1]:
                dp[i][j+1] = c + gap; bt[i][j+1] = (i, j)
    mp = {}
    i, j = n, m
    while (i, j) != (0, 0):
        pi, pj = bt[i][j]
        if pi == i - 1 and pj == j - 1:
            mp[i-1] = j-1
        i, j = pi, pj
    pairs = []
    for i in range(n):
        jj = mp.get(i)
        jt = jp_story[jj] if jj is not None else ''
        conf = ''
        if jj is not None:
            de, dj = _digits(en_story[i]), _digits(jt)
            conf = 'anchor' if (de and de == dj and len(de) >= 2) else 'approx'
        pairs.append({'i': i, 'en': en_story[i], 'jp': jt, 'conf': conf})
    return pairs, n, m


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
