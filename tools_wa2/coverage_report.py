#!/usr/bin/env python3
"""
Coverage diff: game-script sections (the "should exist" anchor) vs what we've translated.

For each of the 40 game-script sections it reports:
  script_boxes  — verbatim dialogue boxes in the transcript (the target)
  translated    — boxes we have insert text for (deep FINAL + first-pass), by area code
  pct           — translated / script_boxes
  state         — done (>=90%) / partial / firstpass-only / placeholder (0)

Section<->area linkage is SECTION_AREAS below (guide TOC -> our area codes).
Emits game_script/coverage.json for the wiki to consume.

Usage: python3 tools_wa2/coverage_report.py
"""
import json, os, re, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GS   = os.path.join(ROOT, 'game_script')
INS  = os.path.join(ROOT, 'insert')

# all area maps imported from build_db (single source of truth)
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_db as DB
SECTION_AREAS = DB.SECTION_AREAS
SCENE_AREA    = DB.SCENE_AREA     # deep file -> area
FP_AREAS      = DB.FP_AREAS       # firstpass file -> [area,...]

def count_boxes(path):
    if not os.path.exists(path): return 0
    n = 0
    for ln in open(path, encoding='utf-8', errors='replace'):
        if re.match(r'^\[US#\d+\]', ln.strip()): n += 1
    return n

def area_counts():
    """area code -> (deep_boxes, fp_boxes)."""
    deep = {}; fp = {}
    for f, area in SCENE_AREA.items():
        deep[area] = deep.get(area,0) + count_boxes(os.path.join(INS, f))
    for f, areas in FP_AREAS.items():
        c = count_boxes(os.path.join(INS,'firstpass',f))
        share = c // max(1,len(areas))
        for a in areas: fp[a] = fp.get(a,0) + share
    return deep, fp

def main():
    manifest = json.load(open(os.path.join(GS,'manifest.json')))
    deep, fp = area_counts()
    rows = []
    for s in manifest['sections']:
        sid = s['id']; areas = SECTION_AREAS.get(sid, [])
        d = sum(deep.get(a,0) for a in areas)
        p = sum(fp.get(a,0)   for a in areas)
        target = s['boxes']
        have = d + p
        pct = round(100*have/target) if target else 0
        if d>0 and pct>=90: state='done'
        elif d>0:           state='partial'
        elif p>0:           state='firstpass'
        else:               state='placeholder'
        rows.append({'id':sid,'title':s['title'],'disc':s['disc'],'target':target,
                     'deep':d,'firstpass':p,'pct':min(pct,100),'state':state,'areas':areas})
    json.dump({'sections':rows}, open(os.path.join(GS,'coverage.json'),'w'), indent=1, ensure_ascii=False)

    def bar(pct):
        n=int(round(pct/10)); return '█'*n+'·'*(10-n)
    tt=sum(r['target'] for r in rows); td=sum(r['deep'] for r in rows); tf=sum(r['firstpass'] for r in rows)
    print(f"{'SECTION':52} {'TGT':>4} {'DEEP':>4} {'FP':>4} {'%':>4}  BAR         STATE")
    print('-'*100)
    for r in rows:
        print(f"[{r['id']}] {r['title'][:44]:44} {r['target']:4d} {r['deep']:4d} {r['firstpass']:4d} {r['pct']:3d}%  {bar(r['pct'])}  {r['state']}")
    print('-'*100)
    print(f"{'TOTAL':52} {tt:4d} {td:4d} {tf:4d} {round(100*(td+tf)/tt):3d}%  (deep {round(100*td/tt)}% / +fp {round(100*(td+tf)/tt)}%)")

if __name__=='__main__':
    main()
