#!/usr/bin/env python3
"""
MASTER DATABASE builder — the single source of truth for the WA2 retranslation.

One row per US# slot (the `10 0c` message index in STGEVT). Every other tool (wiki, coverage,
gap-check, and eventually the inserter) should GENERATE from game_script/wa2_db.json instead of
re-deriving from scattered per-file maps. This kills the mapping-drift bug class.

Each row:
  us         int    US# slot index (0..N-1), the universal key
  block      int    STGEVT block = byte_offset // UBLK
  en         str    in-game English (localization) with {n} name-codes preserved  [from STGEVT]
  jp         str    block-decoded Japanese (residual <codes> possible)             [from JP disc]
  jp_clean   bool   True if jp has no unsolved <...> codes and contains kana/kanji
  is_examine bool   JP starts with the ＊/* examine marker (readable panel, no speaker)
  lit        str    literal translation           (migrated from insert file, "" if none)
  re         str    final retranslation, " / "-joined lines (migrated, "" if none)
  speaker    str    parsed speaker label          (migrated, "" if none)
  tier       int    1=story spine / 2=ambient-fit / 0=untriaged  (set by tier step later)
  status     str    deep | firstpass | placeholder
  src_file   str    insert file this row's translation came from ("" if none)
  area       str    guide-area code (from src_file mapping, "" if untranslated)

Usage:
  python3 tools_wa2/build_db.py             # rebuild game_script/wa2_db.json
  python3 tools_wa2/build_db.py --stats     # rebuild + print summary
"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INS  = os.path.join(ROOT, 'insert')
OUT  = os.path.join(ROOT, 'game_script', 'wa2_db.json')

US_BIN = 'Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin'
US_LBA, US_SIZE, UBLK = 12586, 10813440, 90112

CJK = re.compile(r'[぀-ヿ㐀-鿿]')

# =========================================================================================
# SINGLE SOURCE OF TRUTH for ALL shared config. build_wiki / coverage_report / script_gap
# import these from here (no private copies) — that is what eliminates the mapping-drift bug
# class (the Kanon-1.15 and blk23 mis-maps). Edit a mapping ONCE, here.
# =========================================================================================

# ---- guide spine: authoritative area list (Syonyx GameFAQs walkthrough), in play order ----
GUIDE_AREAS = {
 1: [('WR','Withered Ruins'),('MP','Millennium Puzzle'),('BI',"Brad's Intro"),
     ('MR','Town of Meria'),('SC','Sword Cathedral'),('VC','Valeria Chateau'),
     ('IP','Illsveil Prison'),('UT','Under Traffic'),('DZ','Damzen City'),
     ('TT','Telepath Tower'),('CC','Mt. Chug-Chug'),('LR','Live Reflector'),
     ('GP','Golgotha Prison'),('SD','Sylvaland Castle'),('HM','Halmetz'),('HL','Holst'),
     ('AM','Aguel Mine Shaft'),('RO','Raline Observatory'),('BV','Baskar Village'),
     ('HT','Hidden Trial Arena'),('WV','Warwing Varukisas'),('TS','Tunnel to Sielje Region'),
     ('SR','Sielje Region'),('GB','Gate Bridge'),('GH','Greenhell'),('TB',"T'Bok Village"),
     ('QT','Quartly'),('SY','Slayheim Castle'),('AP','Alchemic Plant'),('EZ','Emulator Zone'),
     ('GG','Guild Galad'),('CM','Closed Mine Shaft'),('CE','Coffin of 100 Eyes'),
     ('DP','Diablo Pillar Ptolomea'),('DC','Diablo Pillar Caina'),('DA','Diablo Pillar Antenora'),
     ('LC','Lost City Archeim'),('DJ','Diablo Pillar Judecca'),('HG','Heimdal Gazzo')],
 2: [('MM','Memory Maze'),('MZ','Millennium Puzzle (2)'),('SA','Sacrificial Altar'),
     ('GL','Grotto of Lourdes'),('LG','Lost Garden'),('SV','Sleeping Volcano'),
     ('PV','Palace Village'),('RF','Raypoint Flam'),('RG','Raypoint Geo'),('RW','Raypoint Wing'),
     ('RM','Raypoint Muse'),('TZ','Trapezohedron'),('FW','Fiery Wreckage'),('ST','Spiral Tower'),
     ('GGa','Glaive Le Gable')],
 3: [('OD','Odd Headquarters'),('WT',"Wind Tiger's Den"),('TL','Thunder Lion Cage'),
     ('IO','Island Outpost'),('DR','Dark Reason'),('AI','Abandoned Icebox'),
     ('SG','Shining Garden'),('MC','Meteorite Crater'),('WD',"Werewolf's Den"),
     ('CS','Crimson Castle'),('PC','Promised Catacombs'),('GLo','The Guardian Lords'),
     ('GZ','Good Luck Zone'),('FL','Fab Science Lab'),('PW',"Pirate's Warren"),
     ('MA','Monster Album'),('SM','Sealed Monsters')],
}
DISC_LABEL = {1: 'DISC 1', 2: 'DISC 2', 3: 'OPTIONAL AREAS'}

# ---- scene registry: deep FINAL file -> (area, subtitle, block). Order within area = list order. ----
SCENES = [
 ('ashley_opening_FINAL.txt','WR',"Withered Ruins prologue → rail-gun standoff",'70'),
 ('ashley_intro_ruins_FINAL.txt','WR',"Inside the ruins: Musketeer push + the kidnapper gang",'23'),
 ('lilka_intro_FINAL.txt','MP',"Magic Lesson with her sister",'25'),
 ('brad_intro_FINAL.txt','BI',"Fugitive in the Rain",'24'),
 ('m1_meria_FINAL.txt','MR','Ceremony morning','3'),
 ('m1_meria_npc_FINAL.txt','MR','Town NPCs & ambient (bakery, kids, inn, tutorials, Ashley/Marina argument)','3'),
 ('m1_swordcathedral_lore_FINAL.txt','SC',"Argetlahm / Sword Magess legend (readable panels)",'5'),
 ('m1_swordcathedral_FINAL.txt','VC',"King of Meria Boule — recurring throne-room audience (spans whole game)",'5'),
 ('m1_library_history_FINAL.txt','VC',"Library history books — the war-criminal hero + 3 nations",'5'),
 ('m1_crimson_noble_FINAL.txt','VC',"Crimson Noble lore panel (Isabel Graceland / Marivel's clan)",'5'),
 ('m1_chateau_hub_FINAL.txt','VC',"Ambient hub chatter (132 recurring NPC/King lines — light-touch fit pass)",'5'),
 ('m_summit_tablets_briefing_FINAL.txt','WV',"Filgaia Summit + Data Tablets briefing (launches the mid-game)",'5'),
 ('m_summit_debate_FINAL.txt','WV',"The 71st Summit conference debate (cross-border rights / Treaty of Iscariot)",'63'),
 ('m2_telepathtower_FINAL.txt','TT','Odessa hijack','29'),
 ('m2_telepath_lore_FINAL.txt','TT','Empathite lore scrolls','29'),
 ('m3_livereflector_FINAL.txt','LR','Startup (intro)','31'),
 ('m3_livereflector_cont_FINAL.txt','LR','Medium awakening','31'),
 ('m4_halmetz_FINAL.txt','HM','The Odessa trap','32'),
 ('m_slayheim_backstory_FINAL.txt','SY',"Liberation Army backstory — Vinsfeld's betrayal + the true hero",'18'),
 ('m_caina_taunt_FINAL.txt','LG',"Caina's taunt + hollow victory (Odessa broadcast / Frozen Lake)",'53'),
 ('m_raline_lizard_FINAL.txt','RO',"Liz & Ard rescue + the Germatron / Odessa reveal (comic scene)",'38'),
 # ---- Disc 2 endgame spine (STGEVT is one whole-game file, byte-identical on both discs) ----
 ('m_swordmagess_truth_FINAL.txt','GGa',"The Sword Magess Anastasia's truth: desire, Lucied, Lord Blazer",'92'),
 ('m_vinsfeld_farewell_FINAL.txt','GGa',"Vinsfeld's farewell blow (|Heroes| don't die) boss taunt",'91'),
 ('m_lordblazer_credo_FINAL.txt','GGa',"Lord Blazer's mockery + the party's 'we don't need a hero' credo",'113'),
 ('m_final_heroes_prayer_FINAL.txt','GGa',"Before the Final Battle: the |heroes| prayer (come back safely)",'111'),
 ('m_anastasia_meeting_FINAL.txt','GGa',"Ashley meets the Sword Magess Anastasia between life and death",'116'),
 ('m_kanon_pillar_FINAL.txt','GGa',"Kanon / Vinsfeld's hero philosophy / Marina refuses the Pillar",'117'),
]

# ---- first-pass registry: auto-generated files (localization reflowed, US#-verified) ----
FIRSTPASS = [
 ('blk27_IP_GP.txt',['IP','GP'],'27','Illsveil / Golgotha Prison'),
 ('blk12_DZ_CC.txt',['DZ','CC'],'12','Damzen City / Mt. Chug-Chug'),
 ('blk13_UT_HL.txt',['UT'],'13','Under Traffic'),
 ('blk14_SD.txt',['SD','HL'],'14','Sylvaland Castle / Holst'),
 ('blk16_BV_HT.txt',['BV','HT'],'16','Baskar Village / Hidden Trial Arena'),
 ('blk17_TS_SR_GB_GH.txt',['TS','SR','GB','GH'],'17','Tunnel to Sielje / Sielje / Gate Bridge / Greenhell'),
 ('blk18_SY.txt',['SY'],'18','Slayheim Castle'),
 ('blk20_GG_AP.txt',['GG','AP'],'20','Guild Galad / Alchemic Plant'),
 ('blk38_CE.txt',['CE'],'38','Coffin of 100 Eyes'),
 ('blk39_DP.txt',['DP','DC','DA'],'39','Diablo Pillars (Ptolomea/Caina/Antenora)'),
 ('blk40_DC.txt',['DC'],'40','Diablo Pillar Caina (cont.)'),
 ('blk44_HG.txt',['HG'],'44','Heimdal Gazzo (part)'),
 ('blk45_LC.txt',['LC'],'45','Lost City Archeim (a)'),
 ('blk46_LC.txt',['LC'],'46','Lost City Archeim (b)'),
 ('blk47_LC.txt',['LC'],'47','Lost City Archeim (c)'),
 ('blk49_HG_DP.txt',['HG','DJ','DA'],'49','Heimdal Gazzo / Diablo Pillars'),
 ('blk69_DP.txt',['DP'],'69','Diablo Pillar Ptolomea (part)'),
]

# ---- game-script section id -> guide-area codes it contains (placeholder + gap anchor) ----
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
# extra area->section for areas the guide files under a differently-coded section
AREA_SECTION_EXTRA = {'FL':'0.7','GP':'1.05'}

# ---- derived maps (do NOT hand-edit; computed from the registries above) ----
SCENE_AREA = {f: area for f, area, _sub, _blk in SCENES}
FP_AREAS   = {f: codes for f, codes, _blk, _label in FIRSTPASS}

# ---- STGEVT: EN text + block per US# slot ----
def us_slots():
    ud = W.readfile(US_BIN, US_LBA, US_SIZE)
    offs = []; i = -1
    while True:
        i = ud.find(b'\x10\x0c', i+1)
        if i < 0: break
        offs.append(i)
    return ud, offs

def uen(ud, offs, i):
    e = offs[i+1] if i+1 < len(offs) else len(ud)
    raw = ud[offs[i]:e].split(b'\x00')[0]
    out = []; j = 0
    while j < len(raw):
        b = raw[j]
        if b == 0x0a and j+1 < len(raw) and 0x30 <= raw[j+1] <= 0x39:
            out.append('{'+chr(raw[j+1])+'}'); j += 2; continue
        if 0x20 <= b < 0x7f: out.append(chr(b))
        elif b == 0x0d: out.append(' ')
        j += 1
    return ' '.join(''.join(out).split())

# ---- JP disc: decoded text per US# slot (same-index within block) ----
def jp_by_block():
    """Return {block: [decoded_jp per in-block slot]} for all blocks."""
    jd = W.load_jp()
    out = {}
    JBLK = W.JBLK
    nblocks = len(jd)//JBLK + 1
    for blk in range(nblocks):
        seg = W.block_bytes(jd, blk)
        jm = []; i = -1
        while True:
            i = seg.find(b'\x10\x0c', i+1)
            if i < 0: break
            jm.append(i)
        texts = []
        for k in range(len(jm)):
            s = jm[k]+2; e = jm[k+1] if k+1 < len(jm) else s+400
            texts.append(' '.join(W.decode_block(seg[s:min(e,s+400)], blk).replace('\n',' / ').split()))
        out[blk] = texts
    return out

def jp_clean(t):
    b = t.strip()
    return bool(b) and '<' not in b and bool(CJK.search(b))

# ---- migrate LIT/RE/speaker from an insert file, keyed by US# ----
def parse_insert(path):
    rows = {}
    cur = None
    for ln in open(path, encoding='utf-8').read().split('\n'):
        m = re.match(r'^\[US#(\d+)\]\s*(.*)$', ln)
        if m:
            cur = int(m.group(1))
            spk = m.group(2).strip()
            spk = re.sub(r'^\(', '', spk); spk = re.split(r'[)\[]', spk)[0].strip()
            rows[cur] = {'lit':'', 're':[], 'speaker':spk}; continue
        if cur is None: continue
        ml = re.match(r'^\s{2}LIT\s*:\s?(.*)$', ln)
        mr = re.match(r'^\s{2}RE\s*:\s?(.*)$', ln)
        if ml: rows[cur]['lit'] = ml.group(1).strip()
        elif mr: rows[cur]['re'].append(mr.group(1).rstrip())
        elif rows[cur]['re'] is not None and re.match(r'^\s{7}\S', ln) and not ln.lstrip().startswith(('JP','LIT','EN','#')):
            rows[cur]['re'].append(ln.strip())
    return rows

def main():
    ud, offs = us_slots()
    nslot = len(offs)
    jpb = jp_by_block()

    # migrate translations: build us -> (lit, re, speaker, src_file, status, area)
    tr = {}
    def ingest(path, status, area_of):
        recs = parse_insert(path)
        fn = os.path.basename(path)
        for us, r in recs.items():
            re_join = ' / '.join(x for x in r['re'] if x.strip())
            # deep beats firstpass if a slot appears in both
            if us in tr and tr[us]['status'] == 'deep' and status == 'firstpass':
                continue
            tr[us] = {'lit':r['lit'], 're':re_join, 'speaker':r['speaker'],
                      'src_file':fn, 'status':status, 'area':area_of(fn, us)}
    # deep first (so they win), then firstpass
    for fn, area in SCENE_AREA.items():
        p = os.path.join(INS, fn)
        if os.path.exists(p): ingest(p, 'deep', lambda f,u,a=area: a)
    for fn, areas in FP_AREAS.items():
        p = os.path.join(INS, 'firstpass', fn)
        if os.path.exists(p): ingest(p, 'firstpass', lambda f,u,a=areas: a[0])

    # cross-block cleanup files: one file spanning many blocks; area is looked up per-US by block.
    blk_area = {}   # block -> primary area (first area that claims it)
    for f, area, _s, blk in SCENES:
        for b in str(blk).split(): blk_area.setdefault(int(b), area)
    for f, codes, blk, _l in FIRSTPASS:
        blk_area.setdefault(int(blk), codes[0])
    for fn in ('disc1_cleanup_FINAL.txt',):
        p = os.path.join(INS, fn)
        if os.path.exists(p):
            ingest(p, 'deep', lambda f, u: blk_area.get(offs[u] // UBLK, ''))

    rows = []
    for us in range(nslot):
        blk = offs[us] // UBLK
        # in-block index for JP alignment
        b_first = None
        # compute lazily: first slot whose block==blk
        # (cache per block)
        rows.append([us, blk])
    # build block->first-us cache
    first_us = {}
    for us in range(nslot):
        blk = offs[us]//UBLK
        if blk not in first_us: first_us[blk] = us

    db = []
    for us in range(nslot):
        blk = offs[us]//UBLK
        en = uen(ud, offs, us)
        k = us - first_us[blk]
        jp = jpb.get(blk, [])[k] if k < len(jpb.get(blk, [])) else ''
        t = tr.get(us, {})
        db.append({
            'us': us, 'block': blk,
            'en': en,
            'jp': jp[:400],
            'jp_clean': jp_clean(jp),
            'is_examine': jp.lstrip().startswith(('＊','*')),
            'lit': t.get('lit',''),
            're': t.get('re',''),
            'speaker': t.get('speaker',''),
            'tier': 0,
            'status': t.get('status','placeholder'),
            'src_file': t.get('src_file',''),
            'area': t.get('area',''),
        })
    json.dump({'nslot': nslot, 'rows': db}, open(OUT,'w'), ensure_ascii=False)
    print(f"wrote {OUT}: {nslot} rows")

    if '--stats' in sys.argv:
        deep = sum(1 for r in db if r['status']=='deep')
        fp   = sum(1 for r in db if r['status']=='firstpass')
        ph   = sum(1 for r in db if r['status']=='placeholder')
        clean= sum(1 for r in db if r['jp_clean'])
        haslit=sum(1 for r in db if r['lit'] and 'pending' not in r['lit'] and r['lit']!='__LIT_TODO__')
        print(f"  status : deep {deep} · firstpass {fp} · placeholder {ph}")
        print(f"  jp     : clean {clean}/{nslot} ({round(100*clean/nslot)}%)")
        print(f"  lit    : real literals {haslit}")
        print(f"  blocks : {len({r['block'] for r in db})}")

if __name__ == '__main__':
    main()
