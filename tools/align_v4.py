"""
JP<->US alignment v4 — dense anchors from ALL harvested katakana + hand nouns.
No linear-expectation filter (that hurt v3). Method: for every distinctive katakana term,
pair its k-th JP occurrence with its k-th US occurrence (occurrence lists track ~1:1),
pool all pairs, take the longest strictly-increasing-in-US subsequence (rejects mispairs),
interpolate US index between anchors. Tag confidence by bracketing-anchor tightness.
"""
import sys, re, bisect, collections
sys.path.insert(0, 'tools')
import importlib, wa2_kanji_map, wa2_jp_decode
importlib.reload(wa2_kanji_map); importlib.reload(wa2_jp_decode)
from wa2_jp_decode import readfile, decode

def rf(p, lba, size):
    RAW, USER, HDR = 2352, 2048, 24
    with open(p, 'rb') as f:
        o = bytearray(); n = (size+USER-1)//USER
        for s in range(n): f.seek((lba+s)*RAW+HDR); o += f.read(USER)
    return bytes(o[:size])
def msgs(d):
    o=[]; i=0
    while True:
        i=d.find(b'\x10\x0c', i+1)
        if i<0 or i+2>=len(d): break
        o.append(i)
    return o
JD = rf('Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin', 12601, 13271040)
UD = rf('Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin', 12586, 10813440)
JM = msgs(JD); UM = msgs(UD)
JTX = [decode(JD[JM[i]+2:JM[i]+2+400]) for i in range(len(JM))]
def ut(i):
    seg = UD[UM[i]+2:UM[i]+2+400].split(b'\x00')[0]
    try: return seg.decode('ascii', 'replace')
    except: return ''
UTX = [ut(i).lower() for i in range(len(UM))]

from align_v3 import romaji  # reuse the romaji table

# generic loanwords that romaji-match spurious US text — never use as anchors
STOP={'ポイント','アイテム','メニュー','システム','エネルギー','ボタン','データ','レベル',
'ゲート','パーティ','キャラクター','マップ','モンスター','ミッション','デモ','タイプ','シャトー',
'テロリスト','ガーディアン','ミーディアム','パワー','ドラゴン','ロード'}
def harvest_terms():
    kat=collections.Counter()
    for s in JTX:
        for m in re.findall(r'[ァ-ヴ][ァ-ヴー]{4,}', s): kat[m]+=1  # >=5 chars only
    terms={}
    for k,c in kat.items():
        if k in STOP: continue
        if 3<=c<=40:            # distinctive: not too rare, not too common
            r=romaji(k)
            if len(r)>=6: terms[k]=r  # longer romaji = less spurious matching
    # always include the reliable hand-mapped proper nouns
    HAND={'ファルガイア':'filgaia','オデッサ':'odessa','ヴァレリア':'valeria','スレイハイム':'slayheim',
'アガートラーム':'argetlahm','ヴィンスフェルト':'vinsfeld','ロンバルディア':'lombardia',
'カイバーベルト':'kuiper','コキュートス':'cocytus','ジュデッカ':'judecca','アンテノーラ':'antenora',
'メリアブール':'meria','カイーナ':'caina','グラウスヴァイン':'grausvein','ギルドグラード':'guildgrade'}
    terms.update(HAND)
    return terms

def build_anchors():
    terms=harvest_terms()
    cands=[]
    for kata,rom in terms.items():
        js=[i for i,s in enumerate(JTX) if kata in s]
        if not js: continue
        us=[i for i,t in enumerate(UTX) if rom in t]
        if not us: continue
        if abs(len(js)-len(us)) <= max(4, 0.35*max(len(js),len(us))):
            for a in range(min(len(js),len(us))):
                cands.append((js[a],us[a]))
    # DEMO-LINE anchors: 'unavailable in the Demo Version' exists in both, in matched pairs
    # throughout — a dense content-independent grid that covers the late-game proper-noun void.
    jdemo=[i for i,s in enumerate(JTX) if '使用することができません' in s or '体験版' in s]
    udemo=[i for i,t in enumerate(UTX) if 'demo version' in t or 'unavailable' in t]
    for a in range(min(len(jdemo),len(udemo))):
        cands.append((jdemo[a],udemo[a]))
    cands=sorted(set(cands))
    # LIS on US axis
    tails=[]; ti=[]; par=[-1]*len(cands)
    for i,(j,u) in enumerate(cands):
        p=bisect.bisect_left(tails,u)
        if p==len(tails): tails.append(u); ti.append(i)
        else: tails[p]=u; ti[p]=i
        par[i]=ti[p-1] if p>0 else -1
    lis=[]; cur=ti[-1] if ti else -1
    while cur!=-1: lis.append(cands[cur]); cur=par[cur]
    lis.reverse()
    return lis, len(cands)

def build_map():
    lis,ncand=build_anchors()
    A=[(0,0)]+lis+[(len(JM)-1,len(UM)-1)]
    clean=[A[0]]
    for j,u in A[1:]:
        if j>clean[-1][0] and u>=clean[-1][1]: clean.append((j,u))
    A=clean
    jp2us={}; conf={}
    for (j0,u0),(j1,u1) in zip(A,A[1:]):
        sj=j1-j0; su=u1-u0
        for j in range(j0,j1):
            f=(j-j0)/sj if sj else 0
            jp2us[j]=min(max(round(u0+f*su),0),len(UM)-1)
            conf[j]='HIGH' if sj<=8 else ('MED' if sj<=30 else 'LOW')
    jp2us[len(JM)-1]=len(UM)-1; conf[len(JM)-1]='HIGH'
    return jp2us, conf, A, ncand

if __name__=='__main__':
    m,conf,A,ncand=build_map()
    c=collections.Counter(conf.values())
    print(f'candidate pairs={ncand}  anchors(LIS)={len(A)}  HIGH={c["HIGH"]} MED={c["MED"]} LOW={c["LOW"]} ({c["HIGH"]/len(m)*100:.0f}/{c["MED"]/len(m)*100:.0f}/{c["LOW"]/len(m)*100:.0f})')
    # tiered accuracy: proper-noun cross-check with +-2 tolerance
    NM={'ファルガイア':'filgaia','オデッサ':'odessa','ヴァレリア':'valeria','スレイハイム':'slayheim','アガートラーム':'argetlahm','ガーディアン':'guardian','ヴィンスフェルト':'vinsfeld','ロンバルディア':'lombardia','カイバーベルト':'kuiper','カイーナ':'caina','コキュートス':'cocytus'}
    tier=collections.defaultdict(lambda:[0,0])
    for j in range(len(JM)):
        for k,v in NM.items():
            if k in JTX[j]:
                hit=any(v in UTX[min(max(m[j]+d,0),len(UM)-1)] for d in range(-2,3))
                tier[conf[j]][0 if hit else 1]+=1
                break
    for t in ['HIGH','MED','LOW']:
        ok,bad=tier[t]; tot=ok+bad
        print(f'  {t}: {ok}/{tot} = {ok/tot*100:.0f}%' if tot else f'  {t}: -')
    import json
    json.dump({str(k):[v,conf[k]] for k,v in m.items()}, open('data/jp_us_alignment.json','w'))
    print('saved data/jp_us_alignment.json')
    for j in [3,35,860,5347,6021,7969]:
        print(f'  JP#{j}->US#{m[j]} [{conf[j]}]: {ut(m[j])[:46]}')
