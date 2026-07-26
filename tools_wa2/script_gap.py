#!/usr/bin/env python3
"""
Cross-check our translated boxes against the local English game-script transcript, per section,
to surface dialogue we may be MISSING.

Our boxes are keyed by US# (STGEVT slot); the script is speaker-tagged prose. They share no IDs,
so we match by EN-text similarity: for each game-script line, find the best-matching box EN in the
sections' mapped areas. A script line with no good match (ratio < THRESH) is flagged as a possible gap.

Uses the SAME EN column our boxes carry (localization text), so a real match should score high.

  python3 tools_wa2/script_gap.py               # summary table (all sections)
  python3 tools_wa2/script_gap.py 2.01          # detail: list unmatched lines for one section
"""
import re, os, sys, glob, difflib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GS   = os.path.join(ROOT, 'game_script')
INS  = os.path.join(ROOT, 'insert')
THRESH = 0.60   # similarity below this = "not covered by any box"

# section -> area codes (mirrors build_wiki / coverage_report)
SECTION_AREAS = {
 '1.01':['WR','MP','BI'],'1.02':['MR','SC'],'1.03':['VC'],'1.04':['VC'],'1.05':['IP','GP'],
 '1.06':['UT','DZ','CC'],'1.07':['TT','CC','LR'],'1.08':['SD','HL','SY'],'1.09':['AM','HM','BV','HT','WV'],
 '1.10':['BV','TB','GH','RO'],'1.11':['WV'],'1.12':['TS','SR'],'1.13':['GB'],'1.14':['GH','TB'],
 '1.15':['SY','CM'],'1.16':['AP'],'1.17':['GG','QT'],'1.18':['CM'],'1.19':['CE'],
 '1.20':['DP','DC','DA','DJ','LC'],'1.21':['HG'],
 '2.01':['MM','MZ'],'2.02':['MM'],'2.03':['SA','GL'],'2.04':['LG'],'2.05':['SV'],'2.06':['PV'],
 '2.07':['RF','RG','RW','RM'],'2.08':['TZ'],'2.09':['FW'],'2.10':['ST','GGa'],'2.11':['GGa'],'2.12':[],
 '0.1':['CS'],'0.2':['PC'],'0.3':['IO'],'0.4':['GLo'],'0.5':['WD'],'0.6':['GLo'],'0.7':['DR','FL'],
}
# insert file -> area (deep) ; firstpass file -> areas
SCENE_AREA = {
 'ashley_opening_FINAL.txt':'WR','ashley_intro_ruins_FINAL.txt':'WR','lilka_intro_FINAL.txt':'MP','brad_intro_FINAL.txt':'BI',
 'm1_meria_FINAL.txt':'MR','m1_swordcathedral_lore_FINAL.txt':'SC','m1_swordcathedral_FINAL.txt':'VC',
 'm1_library_history_FINAL.txt':'VC','m1_crimson_noble_FINAL.txt':'VC','m1_chateau_hub_FINAL.txt':'VC',
 'm_summit_tablets_briefing_FINAL.txt':'WV','m_summit_debate_FINAL.txt':'WV',
 'm2_telepathtower_FINAL.txt':'TT','m2_telepath_lore_FINAL.txt':'TT',
 'm3_livereflector_FINAL.txt':'LR','m3_livereflector_cont_FINAL.txt':'LR','m4_halmetz_FINAL.txt':'HM',
 'm_slayheim_backstory_FINAL.txt':'SY','m_caina_taunt_FINAL.txt':'LG',
}
FP_AREAS = {
 'blk27_IP_GP.txt':['IP','GP'],'blk12_DZ_CC.txt':['DZ','CC'],'blk13_UT_HL.txt':['UT'],'blk14_SD.txt':['SD'],
 'blk16_BV_HT.txt':['BV','HT'],'blk17_TS_SR_GB_GH.txt':['TS','SR','GB','GH'],'blk18_SY.txt':['SY'],
 'blk20_GG_AP.txt':['GG','AP'],'blk38_CE.txt':['CE'],'blk39_DP.txt':['DP','DC','DA'],
 'blk40_DC.txt':['DC'],'blk44_HG.txt':['HG'],'blk45_LC.txt':['LC'],'blk46_LC.txt':['LC'],'blk47_LC.txt':['LC'],
 'blk49_HG_DP.txt':['HG','DJ','DA'],'blk69_DP.txt':['DP'],
}

def norm(t):
    t = re.sub(r'\{[0-9]\}', '', t)             # name codes
    t = re.sub(r'[|<>*@>_\-]', ' ', t)
    t = re.sub(r'[^a-z0-9 ]', ' ', t.lower())
    return ' '.join(t.split())

def box_ens(path):
    """all EN column values in an insert file."""
    out = []
    for ln in open(path, encoding='utf-8', errors='replace').read().split('\n'):
        m = re.match(r'^\s{2}EN\s*:\s?(.*)$', ln)
        if m and m.group(1).strip(): out.append(m.group(1).strip())
    return out

def area_box_ens():
    """area code -> list of normalized EN strings from our boxes."""
    d = {}
    for f, a in SCENE_AREA.items():
        for e in box_ens(os.path.join(INS, f)):
            d.setdefault(a, []).append(norm(e))
    for f, areas in FP_AREAS.items():
        p = os.path.join(INS, 'firstpass', f)
        if not os.path.exists(p): continue
        for e in box_ens(p):
            for a in areas: d.setdefault(a, []).append(norm(e))
    return d

def script_lines(sid):
    """[(speaker, text)] dialogue lines for a section; splits multi-sentence boxes on the guide's
    '  ' run so long merged lines still match individual box EN."""
    p = os.path.join(GS, sid + '.txt')
    if not os.path.exists(p): return []
    out = []
    for ln in open(p, encoding='utf-8').read().split('\n'):
        if ln.startswith('#') or not ln.strip(): continue
        s = ln.strip()
        if s.startswith(('~~','[','->')) and not re.match(r'^[^:]{1,30}:', s): continue
        m = re.match(r'^([^:]{1,30}):\s*(.*)$', s)
        if m: out.append((m.group(1), m.group(2)))
    return out

def word_coverage(nline, blob_words):
    """Fraction of the script line's content words that appear in the pooled box-text word set.
    Handles the guide's box-merging: a long script paragraph is 'covered' if most of its words
    exist somewhere in the area's boxes. Ignores 3 most-common English stopwords lightly."""
    ws = [w for w in nline.split() if len(w) > 2]
    if not ws: return 1.0   # only tiny/filler words -> treat as covered
    hit = sum(1 for w in ws if w in blob_words)
    return hit / len(ws)

def analyze(sid, boxes_by_area):
    areas = SECTION_AREAS.get(sid, [])
    pool = []
    for a in areas: pool += boxes_by_area.get(a, [])
    blob_words = set()
    for p in pool: blob_words.update(p.split())
    lines = script_lines(sid)
    missing = []
    for spk, txt in lines:
        nt = norm(txt)
        if len(nt) < 6:  # trivial/filler ("..." "Yes!") — skip
            continue
        if word_coverage(nt, blob_words) < THRESH:
            missing.append((spk, txt))
    return len(lines), len(missing), missing

def main():
    boxes = area_box_ens()
    sids = sorted(SECTION_AREAS)
    if len(sys.argv) > 1:
        sid = sys.argv[1]
        tot, nmiss, missing = analyze(sid, boxes)
        print(f"[{sid}]  {tot} script lines · {nmiss} not covered by any translated box (thresh {THRESH})\n")
        for spk, txt in missing:
            print(f"  {spk}: {txt[:100]}")
        return
    print(f"{'SECTION':8} {'LINES':>5} {'UNMATCHED':>9}  coverage")
    print('-'*60)
    for sid in sids:
        tot, nmiss, _ = analyze(sid, boxes)
        cov = round(100*(tot-nmiss)/tot) if tot else 0
        flag = '' if not tot else ('  <-- check' if cov < 50 and tot > 5 else '')
        print(f"{sid:8} {tot:5d} {nmiss:9d}  {cov:3d}%{flag}")

if __name__ == '__main__':
    main()
