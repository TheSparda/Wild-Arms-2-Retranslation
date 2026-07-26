#!/usr/bin/env python3
"""
Per-area COMPLETION report — the "what's left in this area" checklist we run as we finish each area.

The wiki's "Not yet translated in this area" block only shows game-script CUTSCENE lines. The bigger
miss is NPC/ambient dialogue: STGEVT US# slots inside an area's block(s) that have real English text
but no RE yet (status=placeholder). This tool lists those exact slots so "completing an area" means
clearing them, not just translating the story spine.

Reads the master DB (game_script/wa2_db.json). Area->block mapping derived from build_db.SCENES +
FIRSTPASS. A block can hold >1 area, so slots are reported per BLOCK the area occupies (with a note).

  python3 tools_wa2/area_todo.py                 # summary: every area, translated vs untranslated slots
  python3 tools_wa2/area_todo.py <AREA>          # list the untranslated US# slots (with EN) for one area
  python3 tools_wa2/area_todo.py <AREA> --clean  # only slots whose decoded JP is clean (ready to translate)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_db as DB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBJ = os.path.join(ROOT, 'game_script', 'wa2_db.json')

def area_blocks():
    ab = {}
    for f, area, sub, blk in DB.SCENES:
        for b in str(blk).replace('+', ' ').split(): ab.setdefault(area, set()).add(int(b))
    for f, codes, blk, label in DB.FIRSTPASS:
        for c in codes: ab.setdefault(c, set()).add(int(blk))
    return ab

def is_content(en):
    return bool(en) and 'Demo Version' not in en and en.strip() not in ('', '...')

def load():
    db = json.load(open(DBJ))['rows']
    byblk = {}
    for r in db: byblk.setdefault(r['block'], []).append(r)
    return db, byblk

def area_rows(area, byblk, ab):
    blks = ab.get(area, set())
    rows = [r for b in sorted(blks) for r in byblk.get(b, [])]
    return blks, rows

def summary():
    db, byblk = load(); ab = area_blocks()
    # area name lookup
    names = {c: n for d in DB.GUIDE_AREAS for c, n in DB.GUIDE_AREAS[d]}
    print(f"{'AREA':5}{'NAME':26}{'BLK':10}{'DONE':>5}{'TODO':>6}{'TODO-clean':>11}")
    print('-'*70)
    tot_todo = 0
    for area in sorted(ab):
        blks, rows = area_rows(area, byblk, ab)
        done = [r for r in rows if r['status'] != 'placeholder']
        todo = [r for r in rows if r['status'] == 'placeholder' and is_content(r['en'])]
        todoc = [r for r in todo if r['jp_clean']]
        tot_todo += len(todo)
        flag = '  <--' if len(todo) >= 10 else ''
        print(f"{area:5}{names.get(area,'?')[:25]:26}{str(sorted(blks)):10}{len(done):5}{len(todo):6}{len(todoc):11}{flag}")
    print('-'*70)
    print(f"total untranslated-with-EN slots across mapped areas: {tot_todo}")
    print("(NOTE: a block can hold >1 area, so an area's TODO counts every untranslated slot in its")
    print(" block(s); use `area_todo.py <AREA>` to see the actual US# lines before translating.)")

def detail(area, clean_only):
    db, byblk = load(); ab = area_blocks()
    blks, rows = area_rows(area, byblk, ab)
    names = {c: n for d in DB.GUIDE_AREAS for c, n in DB.GUIDE_AREAS[d]}
    todo = [r for r in rows if r['status'] == 'placeholder' and is_content(r['en'])]
    if clean_only: todo = [r for r in todo if r['jp_clean']]
    print(f"=== {area} {names.get(area,'?')} — block(s) {sorted(blks)} — {len(todo)} untranslated slots"
          + (" (clean JP only)" if clean_only else "") + " ===\n")
    for r in todo:
        cj = '' if r['jp_clean'] else '  [JP has unsolved codes]'
        print(f"[US#{r['us']}] blk{r['block']}{cj}")
        print(f"   EN: {r['en'][:90]}")
        if r['jp_clean']: print(f"   JP: {r['jp'][:90]}")

def emit_json():
    """Write game_script/area_todo.json: area -> {done, todo, todo_clean} for the wiki to read."""
    db, byblk = load(); ab = area_blocks()
    out = {}
    for area in ab:
        blks, rows = area_rows(area, byblk, ab)
        todo = [r for r in rows if r['status'] == 'placeholder' and is_content(r['en'])]
        out[area] = {
            'blocks': sorted(blks),
            'done': sum(1 for r in rows if r['status'] != 'placeholder'),
            'todo': len(todo),
            'todo_clean': sum(1 for r in todo if r['jp_clean']),
        }
    p = os.path.join(ROOT, 'game_script', 'area_todo.json')
    json.dump(out, open(p, 'w'), indent=1)
    print(f"wrote {p}: {len(out)} areas")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'json':
        emit_json()
    elif len(sys.argv) > 1 and not sys.argv[1].startswith('--'):
        detail(sys.argv[1], '--clean' in sys.argv)
    else:
        summary()
