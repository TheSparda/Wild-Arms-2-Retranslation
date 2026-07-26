#!/usr/bin/env python3
"""
Mapping audit: catch files mapped to the WRONG guide area/section.

Both known errors (1.15 Kanon->Slayheim, blk23->Ashley-intro-not-ClosedMine) had the same shape:
a translated file's content matched a DIFFERENT game-script section than the one it was filed under.

For each insert file (deep + first-pass), this scores its pooled EN text against EVERY game-script
section by word-overlap, then compares the best-matching section to the section(s) its mapped area
belongs to. If the best match is a different section AND scores materially higher, it's flagged.

  python3 tools_wa2/mapping_audit.py
"""
import re, os, glob
import script_gap as SG   # reuse SECTION_AREAS, SCENE_AREA, FP_AREAS, norm, box_ens

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GS   = os.path.join(ROOT, 'game_script')
INS  = os.path.join(ROOT, 'insert')

# area code -> set of section ids that contain it
AREA_SIDS = {}
for sid, codes in SG.SECTION_AREAS.items():
    for c in codes: AREA_SIDS.setdefault(c, set()).add(sid)

def section_words(sid):
    p = os.path.join(GS, sid + '.txt'); ws = set()
    if not os.path.exists(p): return ws
    for ln in open(p, encoding='utf-8').read().split('\n'):
        if ln.startswith('#') or not ln.strip(): continue
        s = ln.strip()
        m = re.match(r'^([^:]{1,30}):\s*(.*)$', s)
        txt = m.group(2) if m else (s if not s.startswith(('~~','[','->')) else '')
        ws.update(SG.norm(txt).split())
    return ws

SEC_W = {sid: section_words(sid) for sid in SG.SECTION_AREAS}

# IDF: a word in FEW sections is distinctive; a word in MANY sections is generic.
import math
_NSEC = len(SEC_W)
_df = {}
for sid, ws in SEC_W.items():
    for w in ws:
        if len(w) > 2: _df[w] = _df.get(w, 0) + 1
def _idf(w): return math.log(_NSEC / (1 + _df.get(w, 0)))

def file_words(path):
    ws = set()
    for e in SG.box_ens(path): ws.update(SG.norm(e).split())
    return {w for w in ws if len(w) > 2}

def score(fw, sid):
    """IDF-weighted overlap: sum of idf(shared words) / sum of idf(file words).
    Distinctive vocabulary (proper nouns, scene-specific terms) dominates; generic
    words shared by every section barely move the score, killing the section-size bias."""
    sw = SEC_W.get(sid, set())
    if not fw: return 0.0
    denom = sum(_idf(w) for w in fw)
    if denom <= 0: return 0.0
    return sum(_idf(w) for w in fw & sw) / denom

def audit_file(path, areas):
    fw = file_words(path)
    if len(fw) < 8:  # too little text to judge
        return None
    mapped_sids = set()
    for a in areas: mapped_sids |= AREA_SIDS.get(a, set())
    # best section overall
    ranked = sorted(SG.SECTION_AREAS, key=lambda s: score(fw, s), reverse=True)
    best = ranked[0]; best_sc = score(fw, best)
    mapped_best = max((score(fw, s) for s in mapped_sids), default=0.0)
    flag = best not in mapped_sids and best_sc > mapped_best + 0.08 and best_sc > 0.25
    return dict(file=os.path.basename(path), areas=areas, best=best, best_sc=best_sc,
                mapped_sids=sorted(mapped_sids), mapped_best=mapped_best, flag=flag,
                top3=[(s, round(score(fw,s),2)) for s in ranked[:3]])

def main():
    results = []
    for f, a in SG.SCENE_AREA.items():
        r = audit_file(os.path.join(INS, f), [a])
        if r: results.append(('deep', r))
    for f, areas in SG.FP_AREAS.items():
        p = os.path.join(INS, 'firstpass', f)
        if os.path.exists(p):
            r = audit_file(p, areas)
            if r: results.append(('fp', r))
    flagged = [r for k, r in results if r['flag']]
    print(f"Audited {len(results)} files. {len(flagged)} possible mapping errors:\n")
    for r in flagged:
        print(f"  !! {r['file']}  (mapped areas {r['areas']} -> sections {r['mapped_sids']})")
        print(f"     best match: {r['best']} ({r['best_sc']:.2f}) vs mapped best {r['mapped_best']:.2f}   top3 {r['top3']}")
    print("\n--- all files, best-matching section (for eyeballing) ---")
    for k, r in sorted(results, key=lambda x: x[1]['best_sc'], reverse=True):
        mark = ' <-- FLAG' if r['flag'] else ''
        print(f"  [{k}] {r['file']:34} areas={','.join(r['areas']):10} best={r['best']}({r['best_sc']:.2f}) mappedbest={r['mapped_best']:.2f}{mark}")

if __name__ == '__main__':
    main()
