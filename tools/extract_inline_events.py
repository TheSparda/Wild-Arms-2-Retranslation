#!/usr/bin/env python3
"""
Inline-event text extractor — captures the SECOND class of STGEVT dialogue that the
`10 0c`-indexed dumper (build_db.py us_slots/uen) silently skipped.

WHY THIS EXISTS
  build_db.py enumerates boxes by the `\x10\x0c` index marker and reads ONE box per gap
  (uen() takes text up to the first NUL). But WA2 event scripts inline MANY additional
  dialogue boxes framed as `\x06@...` / `...\x05N\r@...` between index markers — cutscene
  and event dialogue (Brad's Intro flashback, the puppy scene, the cliff monologue, most
  of the story spine). Those never entered the DB, so coverage was measured against the
  wrong denominator.

  A game text box = a run that starts with `@` (0x40), contains printable ASCII + `\r`
  line breaks + `\n`-digit name codes, and terminates at NUL (0x00) or the next box
  marker. This tool scans the WHOLE STGEVT region for EVERY such `@`-run, decodes it the
  same way uen() does, tags each with its block, and flags which are NEW (not already a
  substring-match of an indexed DB box).

OUTPUT
  data/script/inline_events.json  — [{off, block, en, indexed(bool), new(bool)}]
  --verify  prints the Brad's-Intro / puppy / cliff scenes for eyeball QA (do this FIRST;
            never trust the count until the known scenes read correctly).
  --stats   summary counts.
"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, 'data/script', 'inline_events.json')
DB   = os.path.join(ROOT, 'data/script', 'wa2_db.json')

US_BIN = os.path.join(ROOT, 'Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin')
US_LBA, US_SIZE, UBLK = 12586, 10813440, 90112


def decode_run(raw):
    """Decode one @-run's payload bytes exactly like build_db.uen (name codes, \\r->space)."""
    out = []; j = 0
    while j < len(raw):
        b = raw[j]
        if b == 0x0a and j+1 < len(raw) and 0x30 <= raw[j+1] <= 0x39:
            out.append('{'+chr(raw[j+1])+'}'); j += 2; continue
        if 0x20 <= b < 0x7f: out.append(chr(b))
        elif b == 0x0d: out.append(' ')
        j += 1
    return ' '.join(''.join(out).split())


def _framed(ud, i):
    """Is the `@` at offset i a real box opener?  Recognized frames (from raw inspection):
       10 0c @   indexed box   (the old dumper's marker)
       06 @      inline event box open
       05 N \r @ inline continuation-of-box (N = a small tag byte, then CR)
       .. \r @   continuation after a CR line break inside a multi-box run
    A bare `@` in binary/pointer data (no such frame) is rejected — that was the source of
    the 8k->4k false positives (e.g. 'CNA', 'DOB' pointer bytes)."""
    if i >= 2 and ud[i-2] == 0x10 and ud[i-1] == 0x0c: return 'indexed'
    if i >= 1 and ud[i-1] == 0x06: return 'inline'
    if i >= 3 and ud[i-1] == 0x0d and ud[i-3] == 0x05: return 'inline'
    if i >= 2 and ud[i-1] == 0x0d and ud[i-2] == 0x05: return 'inline'
    # `\r@` where the byte before the CR is printable = nameplate/continuation box open
    # (e.g. "Posse Leader\r@An ID card..."). Always control-free in the region, so safe.
    if i >= 2 and ud[i-1] == 0x0d and 0x20 <= ud[i-2] < 0x7f: return 'inline'
    return None


def find_boxes(ud):
    """Yield (offset_of_@, decoded_en, indexed_bool) for every FRAMED dialogue box.

    A box opens at a framed `@` (0x40); its text runs (printable ASCII / \\r / \\n-digit)
    until NUL or another control byte. indexed=True when opened by the `\x10\x0c` marker."""
    n = len(ud); i = 0
    while True:
        i = ud.find(b'@', i)
        if i < 0: break
        frame = _framed(ud, i)
        if not frame:
            i += 1; continue
        j = i + 1; k = j
        while k < n:
            b = ud[k]
            if b == 0x00: break
            if b == 0x0d: k += 1; continue                      # line break
            if b == 0x0a and k+1 < n and 0x30 <= ud[k+1] <= 0x39:
                k += 2; continue                                # {n} name code
            if 0x20 <= b < 0x7f: k += 1; continue
            break                                               # any other control ends the run
        raw = ud[j:k]
        en = decode_run(raw)
        letters = sum(1 for c in en if c.isalpha())
        if len(en) >= 3 and letters >= 2:
            yield i, en, (frame == 'indexed')
            i = k
        else:
            i = i + 1


def norm(s):
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower()).split())


def main():
    ud = W.readfile(US_BIN, US_LBA, US_SIZE)
    boxes = list(find_boxes(ud))

    # already-captured EN (from the indexed DB) for dedup
    have = set()
    if os.path.exists(DB):
        for r in json.load(open(DB))['rows']:
            nt = norm(r['en'])
            if len(nt) >= 6:
                have.add(nt)

    recs = []
    for off, en, indexed in boxes:
        nt = norm(en)
        # NEW = not already represented by an indexed DB box (substring either direction)
        new = bool(nt) and not any(nt in h or h in nt for h in have)
        recs.append({'off': off, 'block': off // UBLK, 'en': en,
                     'indexed': indexed, 'new': new})

    if '--verify' in sys.argv:
        # print the three known Brad's-Intro scenes for eyeball QA
        probes = ['chased him', 'blast on through', 'a puppy', 'turning back once',
                  'Point 12', 'Slayheim Liberation Army soldier']
        print("=== VERIFY: known Brad's Intro (block 24) cutscene boxes ===")
        for r in recs:
            if r['block'] == 24 and any(p.lower() in r['en'].lower() for p in probes):
                tag = 'idx' if r['indexed'] else 'INLINE'
                print(f"  [{tag}] blk{r['block']} @{r['off']}: {r['en'][:70]}")
        return

    json.dump(recs, open(OUT, 'w'), ensure_ascii=False)
    tot = len(recs)
    idx = sum(1 for r in recs if r['indexed'])
    inl = tot - idx
    new = sum(1 for r in recs if r['new'])
    print(f"wrote {OUT}")
    print(f"  total @-boxes found : {tot}")
    print(f"  indexed (10 0c)     : {idx}")
    print(f"  inline (event)      : {inl}")
    print(f"  NEW (not in DB)     : {new}")

    if '--stats' in sys.argv:
        from collections import defaultdict
        by = defaultdict(int)
        for r in recs:
            if r['new']: by[r['block']] += 1
        print("\n  top blocks by NEW inline boxes:")
        for b, c in sorted(by.items(), key=lambda x: -x[1])[:30]:
            print(f"    blk{b}: {c}")


if __name__ == '__main__':
    main()
