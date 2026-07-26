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

# game-script section id -> guide-area codes that live in it (from the guide TOC + our SCENES/FIRSTPASS)
SECTION_AREAS = {
 '1.01': ['WR','MP','BI'],           '1.02': ['MR','SC'],
 '1.03': ['VC'],                     '1.04': ['VC'],
 '1.05': ['IP'],                     '1.06': ['UT','DZ','CC'],
 '1.07': ['TT','CC','LR'],           '1.08': ['SD','HL','SY'],
 '1.09': ['AM','HM','BV','HT','WV'], '1.10': ['BV','TB','GH','RO'],
 '1.11': ['WV'],                     '1.12': ['TS','SR'],
 '1.13': ['GB'],                     '1.14': ['GH','TB'],
 '1.15': ['SY','CM'],                '1.16': ['AP'],
 '1.17': ['GG','QT'],                '1.18': ['CM'],
 '1.19': ['CE'],                     '1.20': ['DP','DC','DA','DJ','LC'],
 '1.21': ['HG'],
 '2.01': ['MM','MZ'],                '2.02': ['MM'],
 '2.03': ['SA','GL'],                '2.04': ['LG'],
 '2.05': ['SV'],                     '2.06': ['PV'],
 '2.07': ['RF','RG','RW','RM'],      '2.08': ['TZ'],
 '2.09': ['FW'],                     '2.10': ['ST','GGa'],
 '2.11': ['GGa'],                    '2.12': [],
 '0.1': ['CS'],  '0.2': ['PC'],  '0.3': ['IO'],  '0.4': ['GLo'],
 '0.5': ['WD'],  '0.6': ['GLo'], '0.7': ['DR'],
}

# which insert files cover which area (deep + firstpass), mirrors build_wiki
SCENE_AREA = {  # file -> area
 'ashley_opening_FINAL.txt':'WR','ashley_intro_ruins_FINAL.txt':'WR','lilka_intro_FINAL.txt':'MP','brad_intro_FINAL.txt':'BI',
 'm1_meria_FINAL.txt':'MR','m1_swordcathedral_lore_FINAL.txt':'SC','m1_swordcathedral_FINAL.txt':'VC',
 'm1_library_history_FINAL.txt':'VC','m1_crimson_noble_FINAL.txt':'VC','m1_chateau_hub_FINAL.txt':'VC',
 'm_summit_tablets_briefing_FINAL.txt':'WV','m_summit_debate_FINAL.txt':'WV',
 'm2_telepathtower_FINAL.txt':'TT','m2_telepath_lore_FINAL.txt':'TT',
 'm3_livereflector_FINAL.txt':'LR','m3_livereflector_cont_FINAL.txt':'LR','m4_halmetz_FINAL.txt':'HM',
 'm_slayheim_backstory_FINAL.txt':'SY','m_caina_taunt_FINAL.txt':'LG',
}
FP_AREAS = {  # firstpass file -> area codes
 'blk27_IP_GP.txt':['IP'],'blk12_DZ_CC.txt':['DZ','CC'],'blk13_UT_HL.txt':['UT'],
 'blk14_SD.txt':['SD'],'blk16_BV_HT.txt':['BV','HT'],'blk17_TS_SR_GB_GH.txt':['TS','SR','GB','GH'],
 'blk18_SY.txt':['SY'],'blk20_GG_AP.txt':['GG','AP'],'blk38_CE.txt':['CE'],
 'blk39_DP.txt':['DP','DC','DA'],'blk40_DC.txt':['DC'],'blk44_HG.txt':['HG'],
 'blk45_LC.txt':['LC'],'blk46_LC.txt':['LC'],'blk47_LC.txt':['LC'],'blk49_HG_DP.txt':['HG','DJ','DA'],
 'blk69_DP.txt':['DP'],
}

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
