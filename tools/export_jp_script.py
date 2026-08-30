#!/usr/bin/env python3
"""
Export the full Japanese script, organised for READING — by area, in story order, with the
English alongside and each box's decode quality marked.

WHY
  translation/dumps_jp/disc1_STGEVT_decoded.txt already exists and is real, but it is keyed to
  the superseded 8,516-slot `10 0c` model, so it never saw the ~11,000 boxes the corrected
  extractor finds; it decodes at 7.8% placeholders against 5.6% now; and it is a flat list with
  no area structure and no English beside it. This replaces it: all 19,904 boxes, grouped by
  area in story order. This is the artifact
  you read to understand an area's narrative, a story arc's shape, or a character's register —
  as opposed to data/voices.json, which MEASURES register but does not let you read a scene.

WHAT IT IS NOT
  Not a translation and not an alignment. The English is printed beside the Japanese only as
  orientation; the pairing comes from the DP aligner and is unreliable (see issue #4), so it is
  labelled with its confidence and must not be read as "this JP means that EN".

DECODE QUALITY, PRINTED PER BOX
  Kanji the game stores in its own private block are shown as <b:xxxx> where still unsolved.
  Measured over all 19,904 boxes: 34.8% decode fully, 37.4% carry a few placeholders and remain
  readable, 27.8% are heavily obscured. Each box is marked ○ / ◐ / ● so a reader knows how much
  weight to put on it, and area summaries report the mix.

USAGE
  python3 tools/export_jp_script.py            # -> translation/dumps_jp/by_area/*.md + INDEX.md
  python3 tools/export_jp_script.py --area VC  # one area to stdout
"""
import os, sys, re, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W
import extract_boxes as X
import build_db as DB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, 'translation', 'dumps_jp', 'by_area')
PLACEHOLDER = re.compile(r'<b:[0-9a-f]{4}>|<[0-9a-f]{4}>|\[[0-9a-f]{2}\]')

# area code -> readable name, and the guide's story order, both from build_db's guide tables
AREA_NAME, AREA_ORDER = {}, []
for disc, pairs in sorted(DB.GUIDE_AREAS.items()):
    for code, name in pairs:
        AREA_NAME[code] = name
        AREA_ORDER.append((disc, code))
ORDER_IX = {c: i for i, (_d, c) in enumerate(AREA_ORDER)}


def quality(text):
    """○ fully decoded · ◐ a few placeholders, still readable · ● heavily obscured"""
    n = len(PLACEHOLDER.findall(text))
    if n == 0: return '○'
    return '◐' if n / max(len(text), 1) < 0.06 else '●'


def block_areas():
    """block -> area code, taken from the hand-annotated rows in the master DB."""
    rows = json.load(open(os.path.join(ROOT, 'data/script/wa2_db.json')))['rows']
    tally = collections.defaultdict(collections.Counter)
    for r in rows:
        a = r.get('area')
        if isinstance(a, str) and a:
            tally[r['block']][a] += 1
    return {b: c.most_common(1)[0][0] for b, c in tally.items()}


def speaker_of(jp_text):
    """JP boxes often carry a nameplate before the quote: 徴集同２ 「... — the only speaker
    signal that lives in the Japanese itself."""
    m = re.match(r'^([^「『＊\s]{1,12})\s*[「『]', jp_text)
    return m.group(1) if m else ''


def collect():
    jd = W.load_jp()
    ud = W.readfile(X.US_BIN, X.US_LBA, X.US_SIZE)
    barea = block_areas()
    out = collections.defaultdict(list)
    for blk in range(120):
        jpb = X.jp_boxes(jd, blk)
        if not jpb:
            continue
        enb = X.en_boxes(ud, blk)
        pairs, _n, _m = X.align(enb, jpb)
        # align() pairs EN->JP; invert so a JP box can show its EN counterpart + confidence
        jp_to_en = {}
        for p in pairs:
            if p['jp']:
                jp_to_en.setdefault(p['jp'], (p['en'], p['conf']))
        area = barea.get(blk, '??')
        for b in jpb:
            en, conf = jp_to_en.get(b['text'], ('', ''))
            out[area].append({
                'blk': blk, 'jp': b['text'], 'en': en, 'conf': conf,
                'panel': b['panel'], 'spk': speaker_of(b['text']), 'q': quality(b['text']),
            })
    return out


def render(area, rows):
    name = AREA_NAME.get(area, 'Unlabelled blocks')
    qc = collections.Counter(r['q'] for r in rows)
    blocks = sorted({r['blk'] for r in rows})
    L = [f"# {name}  `{area}`", "",
         f"{len(rows)} Japanese boxes across block(s) {', '.join(map(str, blocks))}.",
         f"Decode quality: ○ {qc['○']} fully · ◐ {qc['◐']} minor gaps · ● {qc['●']} heavily obscured.", "",
         "The English is orientation only — it is paired by the DP aligner, which is unreliable",
         "(issue #4). `anchor`/`term` are corroborated; `approx` is a guess. Read the Japanese.", ""]
    cur = None
    for r in rows:
        if r['blk'] != cur:
            cur = r['blk']
            L += ["", f"## block {cur}", ""]
        head = f"{r['q']} "
        if r['spk']: head += f"**{r['spk']}** "
        if r['panel']: head += "*(examine panel)* "
        L.append(head.rstrip())
        L.append(f"> {r['jp']}")
        if r['en']:
            tag = f" `{r['conf']}`" if r['conf'] else ""
            L.append(f"> ")
            L.append(f"> _EN{tag}:_ {r['en']}")
        L.append("")
    return "\n".join(L) + "\n"


def main():
    data = collect()
    if '--area' in sys.argv:
        a = sys.argv[sys.argv.index('--area') + 1]
        print(render(a, data.get(a, [])))
        return
    os.makedirs(OUTDIR, exist_ok=True)
    keys = sorted(data, key=lambda a: (ORDER_IX.get(a, 999), a))
    idx = ["# Japanese script, by area", "",
           "Generated by `tools/export_jp_script.py` — **do not hand-edit**.", "",
           "Areas follow the Syonyx walkthrough order used by `docs/WA2_CHAPTER_MAP.md`, which is",
           "the project's authoritative table of contents. Read these to get an area's narrative,",
           "an arc's shape, or a character's register in the original.", "",
           "| area | name | boxes | ○ full | ◐ minor | ● obscured |", "|---|---|---:|---:|---:|---:|"]
    total = 0
    for a in keys:
        rows = data[a]
        total += len(rows)
        qc = collections.Counter(r['q'] for r in rows)
        fn = f"{a}.md"
        open(os.path.join(OUTDIR, fn), 'w').write(render(a, rows))
        idx.append(f"| [`{a}`]({fn}) | {AREA_NAME.get(a,'(unlabelled)')} | {len(rows)} | {qc['○']} | {qc['◐']} | {qc['●']} |")
    idx += ["", f"**{total:,} Japanese boxes** across {len(keys)} areas.", "",
            "Boxes in blocks with no area label are collected under `??`."]
    open(os.path.join(OUTDIR, 'INDEX.md'), 'w').write("\n".join(idx) + "\n")
    print(f"wrote {len(keys)} area files + INDEX.md to {os.path.relpath(OUTDIR, ROOT)}")
    print(f"  {total:,} JP boxes")


if __name__ == '__main__':
    main()
