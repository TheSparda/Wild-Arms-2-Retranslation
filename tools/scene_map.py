"""
Batch scene-mapper: for a list of story threads (each = JP search terms + EN label),
cluster all mentions into scenes (consecutive msgs within a gap), tag alignment confidence,
and emit a master index. One alignment pass covers every thread.
"""
import sys, re, collections
sys.path.insert(0, 'tools')
import importlib, align_v6 as V, wa2_kanji_map, wa2_jp_decode
importlib.reload(wa2_kanji_map); importlib.reload(wa2_jp_decode); importlib.reload(V)
from wa2_jp_decode import decode

m, conf, blocks = V.build_map()
JTX = [decode(V.JD[V.JM[i]+2:V.JM[i]+2+400]) for i in range(len(V.JM))]
def ut(i):
    seg = V.UD[V.UM[i]+2:V.UM[i]+2+400].split(b'\x00')[0]
    try: return seg.decode('ascii','replace')
    except: return ''
UTX = [ut(i) for i in range(len(V.UM))]
BLK = 110592

# threads: label -> list of JP substrings to match (katakana names, solved-kanji terms, quoted)
THREADS = {
    'Sword Magess / Anastasia': ['アナスタシア', '剣の巫女', 'ソードマギス'],
    'Guardians / Mediums': ['ガーディアン', 'ミーディアム'],
    'Odessa (org & plan)': ['オデッサ'],
    'Kuiper Belt threat': ['カイバーベルト'],
    'Argetlahm (the sword)': ['アガートラーム'],
    'ARMS (the unit)': ['ＡＲＭＳ'],
    'Vinsfeld': ['ヴィンスフェルト'],
    'Antenora (Cocytus)': ['アンテノーラ'],
    'Judecca (Cocytus)': ['ジュデッカ'],
    'Ptolomea (Cocytus)': ['トロメア', 'プトレマイオス'],
    'Cocytus (the quartet)': ['コキュートス'],
    'Lombardia (airship)': ['ロンバルディア'],
    'Slayheim (Brad backstory)': ['スレイハイム'],
    'Filgaia (the world)': ['ファルガイア'],
    'Heimdal Gazzo': ['ヘイムダル'],
    'Crimson Nobles / Marivel': ['ノーブルレッド', 'クリムゾン', 'マリアベル'],
    'Ashley Winchester': ['ウィンチェスター'],
    'Kanon / Aisha': ['アイシャ', 'ベルデナット'],
    'hero=sacrifice theme': ['英雄', '生け'],  # 生け贄 (贄=8b21 solved)
    'Drifters (渡り鳥)': ['渡り'],
}

def clusters(idxs, gap=15):
    if not idxs: return []
    idxs=sorted(set(idxs)); out=[]; cur=[idxs[0]]
    for x in idxs[1:]:
        if x-cur[-1]<=gap: cur.append(x)
        else: out.append(cur); cur=[x]
    out.append(cur); return out

def readable(s):
    tot=len([c for c in s if 0x3040<=ord(c)<=0x30ff or 0x4e00<=ord(c)<=0x9fff or c=='<'])
    gap=s.count('<')
    return tot, gap

if __name__=='__main__':
    # threads with >40 scenes are ubiquitous words (Filgaia/Odessa/ARMS/Slayheim) — their
    # "scenes" are noise; mark them REFERENCE-ONLY. Focused threads (<25 scenes) are the useful ones.
    out=['# WA2 — Master Scene Index (all major threads)',
         '# Built via v6 alignment. Each thread: JP mention clusters -> scenes (JP msg range, block, EN snippet).',
         '# conf = alignment confidence of the first line; <n> gaps = unsolved kanji in that line.',
         '#',
         '# USABILITY: threads marked [FOCUSED] have discrete, followable scenes. Threads marked',
         '# [UBIQUITOUS] use a word that appears game-wide (Filgaia/Odessa/ARMS/Slayheim/Guardian) —',
         '# their clusters are density heat-maps, not clean scenes; use for "where is X densest", not scene lists.',
         '='*80]
    for label, terms in THREADS.items():
        idxs=[i for i,s in enumerate(JTX) if any(t in s for t in terms)]
        scs=clusters(idxs)
        tag='[FOCUSED]' if len(scs)<=25 else '[UBIQUITOUS]'
        out.append(f'\n## {label} {tag} — {len(idxs)} mentions, {len(scs)} scenes')
        for sc in scs:
            lo,hi=sc[0],sc[-1]; blk=V.JM[lo]//BLK
            en=UTX[m[lo]].strip()[:60] or UTX[min(m[lo]+1,len(V.UM)-1)].strip()[:60]
            out.append(f'  JP#{lo}-{hi} ({len(sc)}msg, blk{blk}, {conf[lo]}) EN~: {en}')
    open('WA2_SCENE_INDEX.md','w').write('\n'.join(out))
    print(f'wrote WA2_SCENE_INDEX.md — {len(THREADS)} threads')
    # print a summary table to console
    for label,terms in THREADS.items():
        idxs=[i for i,s in enumerate(JTX) if any(t in s for t in terms)]
        print(f'  {label:34} {len(idxs):4} mentions  {len(clusters(idxs)):3} scenes')
