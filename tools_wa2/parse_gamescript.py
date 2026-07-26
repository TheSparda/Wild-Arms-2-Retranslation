#!/usr/bin/env python3
"""
Parse the Unos Hambalos GameFAQs game-script transcript (english_script/game script.rtf)
into a structured, per-section, speaker-tagged script — the MASTER COVERAGE ANCHOR.

Output:
  game_script/manifest.json         — sections, per-section box counts + speaker rosters
  game_script/[X.YY].txt            — one flat file per guide section (speaker-tagged boxes)

The transcript is the only source with verbatim SPEAKER ATTRIBUTION + scene boundaries,
so it drives per-area coverage ("what should exist") that the raw STGEVT US# dump can't.

Also emits PER-LOCATION files keyed by guide-area code, split on the transcript's own
~~Location~~ markers (the authoritative scene boundaries) rather than the coarse [1.02]
chapter headers. This is what makes placeholder/gap content land under the RIGHT area.

Usage: python3 tools_wa2/parse_gamescript.py
"""
import subprocess, re, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_db as DB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RTF  = os.path.join(ROOT, 'english_script', 'game script.rtf')
OUT  = os.path.join(ROOT, 'game_script')
LOC  = os.path.join(OUT, 'loc')

# ---- resolve a ~~Location~~ marker to a guide-area code ----
_NAME_CODE = {name: code for d in DB.GUIDE_AREAS for code, name in DB.GUIDE_AREAS[d]}
_AREA_NAME = {code: name for name, code in _NAME_CODE.items()}   # code -> name (for labels)
def _norm(s): return re.sub(r'[^a-z0-9]', '', s.lower())
_BYNORM = {_norm(n): c for n, c in _NAME_CODE.items()}
# spelling variants in the transcript that differ from our canonical area names
_ALIAS = {'aguelitemineshaft': 'AM'}
def loc_to_code(loc):
    n = _norm(loc)
    return _BYNORM.get(n) or _ALIAS.get(n)

SEC_RE   = re.compile(r'^\s*#\[([0-9]+\.[0-9]+)\]\s+(.*?)\s*#*\s*$')
OPT_RE   = re.compile(r'^\s*#\[(0\.[0-9]+)\]\s+(.*?)\s*#*\s*$')
SUB_RE   = re.compile(r'^\s*~~\s*(.*?)\s*~~\s*$')
DIR_RE   = re.compile(r'^\s*\[(.*)\]\s*$')
# Speaker line: optional @, a Name (letters/digits/space/.'?()/-{}), then ':' then optional text.
SPK_RE   = re.compile(r'^(@?)([A-Z][A-Za-z0-9 .()/?\'’{}\-]{0,28}?):\s{2,}(.*)$')
SPK_BARE = re.compile(r'^(@?)([A-Z][A-Za-z0-9 .()/?\'’{}\-]{0,28}?):\s*$')
CHOICE_RE= re.compile(r'^\s*->\s*[0-9]+\.\s*(.*)$')
CONT_COL = 14  # continuation lines are indented to ~col 14

def load_text():
    return subprocess.run(['textutil','-convert','txt','-stdout',RTF],
                          capture_output=True, text=True).stdout

def parse(text):
    lines = text.split('\n')
    sections = []   # {id,title,disc,boxes:[{speaker,text,kind}]}
    cur = None
    pending = None  # a box being accumulated (speaker + continuation lines)

    def flush():
        nonlocal pending
        if pending and cur is not None:
            pending['text'] = ' '.join(pending['text'].split())
            pending['loc'] = cur.get('loc')      # tag with the location active when it started
            if pending['text'] or pending['kind'] != 'speaker':
                cur['boxes'].append(pending)
        pending = None

    for ln in lines:
        m = SEC_RE.match(ln) or OPT_RE.match(ln)
        if m:
            flush()
            sid, title = m.group(1), m.group(2).strip()
            cur = {'id': sid, 'title': title,
                   'disc': 0 if sid.startswith('0.') else int(sid.split('.')[0]),
                   'boxes': [], 'loc': None}
            sections.append(cur)
            continue
        if cur is None:
            continue
        sm = SUB_RE.match(ln)
        if sm:
            flush()
            loc = sm.group(1).strip()
            cur['loc'] = loc                     # remember current location for box tagging
            cur['boxes'].append({'kind':'subarea','speaker':None,'text':loc,'loc':loc})
            continue
        dm = DIR_RE.match(ln)
        if dm:
            flush()
            cur['boxes'].append({'kind':'dir','speaker':None,'text':dm.group(1).strip(),'loc':cur.get('loc')})
            continue
        cm = CHOICE_RE.match(ln)
        if cm:
            # choices attach to the current speaker box as continuation
            if pending: pending['text'] += ' [choice: '+cm.group(1).strip()+']'
            else: cur['boxes'].append({'kind':'choice','speaker':None,'text':cm.group(1).strip(),'loc':cur.get('loc')})
            continue
        sp = SPK_RE.match(ln)
        if sp:
            flush()
            pending = {'kind':'speaker','speaker':sp.group(2).strip(),'text':sp.group(3).strip()}
            continue
        sb = SPK_BARE.match(ln)
        if sb:
            flush()
            pending = {'kind':'speaker','speaker':sb.group(2).strip(),'text':''}
            continue
        if pending is not None and ln.strip():
            pending['text'] += ' ' + ln.strip()
    flush()
    return sections

def main():
    os.makedirs(OUT, exist_ok=True)
    text = load_text()
    sections = parse(text)
    manifest = {'source':'english_script/game script.rtf','sections':[]}
    for s in sections:
        dlg = [b for b in s['boxes'] if b['kind']=='speaker']
        spk = {}
        for b in dlg: spk[b['speaker']] = spk.get(b['speaker'],0)+1
        roster = sorted(spk.items(), key=lambda kv:(-kv[1],kv[0]))
        fn = os.path.join(OUT, s['id']+'.txt')
        with open(fn,'w') as f:
            f.write(f"# [{s['id']}] {s['title']}  (disc {s['disc']})\n")
            f.write(f"# dialogue boxes: {len(dlg)}   speakers: {len(spk)}\n")
            f.write("# ============================================================\n")
            for b in s['boxes']:
                if b['kind']=='subarea': f.write(f"\n~~ {b['text']} ~~\n")
                elif b['kind']=='dir':   f.write(f"  [{b['text']}]\n")
                elif b['kind']=='choice':f.write(f"    -> {b['text']}\n")
                else:                    f.write(f"{b['speaker']}: {b['text']}\n")
        manifest['sections'].append({
            'id':s['id'],'title':s['title'],'disc':s['disc'],
            'boxes':len(dlg),'speakers':len(spk),
            'roster':roster[:12],'file':'game_script/'+s['id']+'.txt'})
    json.dump(manifest, open(os.path.join(OUT,'manifest.json'),'w'), indent=1, ensure_ascii=False)
    tot = sum(x['boxes'] for x in manifest['sections'])
    print(f"parsed {len(sections)} sections, {tot} dialogue boxes -> game_script/")

    # ---- PER-LOCATION output: split on the transcript's own ~~Location~~ markers, keyed by
    # guide-area code. This is the authoritative area boundary (55/56 markers map to a code).
    os.makedirs(LOC, exist_ok=True)
    loc_boxes = {}       # area_code -> [box,...] in transcript order
    unmapped = {}        # location name -> count (markers we couldn't map)
    for s in sections:
        for b in s['boxes']:
            loc = b.get('loc')
            if not loc: continue
            code = loc_to_code(loc)
            if not code:
                unmapped[loc] = unmapped.get(loc, 0) + 1
                continue
            loc_boxes.setdefault(code, []).append(b)
    loc_manifest = {}
    for code, boxes in loc_boxes.items():
        dlg = [b for b in boxes if b['kind']=='speaker']
        spk = {}
        for b in dlg: spk[b['speaker']] = spk.get(b['speaker'],0)+1
        with open(os.path.join(LOC, code+'.txt'),'w') as f:
            f.write(f"# area {code} — {_AREA_NAME.get(code,'?')}  ({len(dlg)} dialogue boxes)\n")
            f.write("# from the game-script ~~Location~~ markers (authoritative area boundary)\n")
            f.write("# ============================================================\n")
            for b in boxes:
                if b['kind']=='subarea': f.write(f"\n~~ {b['text']} ~~\n")
                elif b['kind']=='dir':   f.write(f"  [{b['text']}]\n")
                elif b['kind']=='choice':f.write(f"    -> {b['text']}\n")
                else:                    f.write(f"{b['speaker']}: {b['text']}\n")
        loc_manifest[code] = {'name':_AREA_NAME.get(code,'?'),'boxes':len(dlg),
                              'roster':sorted(spk.items(),key=lambda kv:(-kv[1],kv[0]))[:8],
                              'file':'game_script/loc/'+code+'.txt'}
    json.dump({'locations':loc_manifest,'unmapped':unmapped},
              open(os.path.join(OUT,'location_map.json'),'w'), indent=1, ensure_ascii=False)
    ltot = sum(v['boxes'] for v in loc_manifest.values())
    print(f"\nper-LOCATION: {len(loc_manifest)} areas, {ltot} dialogue boxes -> game_script/loc/")
    if unmapped: print(f"  unmapped markers: {unmapped}")
    for code in sorted(loc_manifest, key=lambda c: -loc_manifest[c]['boxes'])[:12]:
        v = loc_manifest[code]
        top = ', '.join(f"{n}({c})" for n,c in v['roster'][:3])
        print(f"  {code:4} {v['name'][:24]:24} {v['boxes']:4d} boxes | {top}")

if __name__=='__main__':
    main()
