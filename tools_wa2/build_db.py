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

# ---- file -> area maps (the LAST place these live; everything else will read the DB) ----
SCENE_AREA = {
 'ashley_opening_FINAL.txt':'WR','ashley_intro_ruins_FINAL.txt':'WR','lilka_intro_FINAL.txt':'MP',
 'brad_intro_FINAL.txt':'BI','m1_meria_FINAL.txt':'MR','m1_swordcathedral_lore_FINAL.txt':'SC',
 'm1_swordcathedral_FINAL.txt':'VC','m1_library_history_FINAL.txt':'VC','m1_crimson_noble_FINAL.txt':'VC',
 'm1_chateau_hub_FINAL.txt':'VC','m_summit_tablets_briefing_FINAL.txt':'WV','m_summit_debate_FINAL.txt':'WV',
 'm2_telepathtower_FINAL.txt':'TT','m2_telepath_lore_FINAL.txt':'TT','m3_livereflector_FINAL.txt':'LR',
 'm3_livereflector_cont_FINAL.txt':'LR','m4_halmetz_FINAL.txt':'HM','m_slayheim_backstory_FINAL.txt':'SY',
 'm_caina_taunt_FINAL.txt':'LG',
}
FP_AREAS = {
 'blk27_IP_GP.txt':['IP','GP'],'blk12_DZ_CC.txt':['DZ','CC'],'blk13_UT_HL.txt':['UT'],'blk14_SD.txt':['SD'],
 'blk16_BV_HT.txt':['BV','HT'],'blk17_TS_SR_GB_GH.txt':['TS','SR','GB','GH'],'blk18_SY.txt':['SY'],
 'blk20_GG_AP.txt':['GG','AP'],'blk38_CE.txt':['CE'],'blk39_DP.txt':['DP','DC','DA'],'blk40_DC.txt':['DC'],
 'blk44_HG.txt':['HG'],'blk45_LC.txt':['LC'],'blk46_LC.txt':['LC'],'blk47_LC.txt':['LC'],
 'blk49_HG_DP.txt':['HG','DJ','DA'],'blk69_DP.txt':['DP'],
}

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
