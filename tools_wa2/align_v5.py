"""
JP<->US alignment v5 — BLOCK-ANCHORED.
Discovery: STGEVT is 120 fixed-size event blocks in BOTH versions (JP block=110592 B,
US block=90112 B), each marked by a "Sony" header. Same block order, same maps. Per-block
message counts are near-equal. So block boundaries are 120 HARD structural anchors that cap
drift to within a single block (~tens of msgs), independent of text. Within each block we
refine using proper-noun + demo-line anchors, else proportional interpolation.
"""
import sys, re, bisect, collections
sys.path.insert(0, 'tools_wa2')
import importlib, wa2_kanji_map, wa2_jp_decode
importlib.reload(wa2_kanji_map); importlib.reload(wa2_jp_decode)
from wa2_jp_decode import readfile, decode
from align_v3 import romaji

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
def _ut(i):
    seg = UD[UM[i]+2:UM[i]+2+400].split(b'\x00')[0]
    try: return seg.decode('ascii','replace')
    except: return ''
UTX = [_ut(i).lower() for i in range(len(UM))]
JB, UB = 110592, 90112

def block_anchors():
    """First JP msg-index and first US msg-index in each block b -> a hard (j,u) anchor."""
    jfirst={}; ufirst={}
    for idx,o in enumerate(JM):
        b=o//JB
        if b not in jfirst: jfirst[b]=idx
    for idx,o in enumerate(UM):
        b=o//UB
        if b not in ufirst: ufirst[b]=idx
    common=sorted(set(jfirst)&set(ufirst))
    return [(jfirst[b],ufirst[b]) for b in common]

# generic loanwords to skip
STOP={'ポイント','アイテム','メニュー','システム','エネルギー','ボタン','データ','レベル','ゲート',
'パーティ','キャラクター','マップ','モンスター','ミッション','デモ','タイプ','シャトー','テロリスト',
'ガーディアン','ミーディアム','パワー','ドラゴン','ロード'}
def term_anchors():
    kat=collections.Counter()
    for s in JTX:
        for m in re.findall(r'[ァ-ヴ][ァ-ヴー]{4,}', s): kat[m]+=1
    terms={}
    for k,c in kat.items():
        if k in STOP: continue
        if 3<=c<=40:
            r=romaji(k)
            if len(r)>=6: terms[k]=r
    HAND={'ファルガイア':'filgaia','オデッサ':'odessa','ヴァレリア':'valeria','スレイハイム':'slayheim',
'アガートラーム':'argetlahm','ヴィンスフェルト':'vinsfeld','ロンバルディア':'lombardia','カイバーベルト':'kuiper',
'コキュートス':'cocytus','ジュデッカ':'judecca','アンテノーラ':'antenora','メリアブール':'meria','カイーナ':'caina',
# confirmed location/town anchors (JP katakana -> actual US spelling, counts verified close)
'ダムツェン':'damzen','シルヴァラント':'sylvaland','ヘイムダル':'heimdal','パレスヴィレッジ':'palace village',
'クリムゾン':'crimson','シエルジェ':'sielje','バスカー':'baskar'}
    terms.update(HAND)
    cands=[]
    for kata,rom in terms.items():
        js=[i for i,s in enumerate(JTX) if kata in s]
        if not js: continue
        us=[i for i,t in enumerate(UTX) if rom in t]
        if not us: continue
        if abs(len(js)-len(us))<=max(4,0.35*max(len(js),len(us))):
            for a in range(min(len(js),len(us))): cands.append((js[a],us[a]))
    # demo lines
    jd_=[i for i,s in enumerate(JTX) if '使用することができません' in s or '体験版' in s]
    ud_=[i for i,t in enumerate(UTX) if 'demo version' in t or 'unavailable' in t]
    for a in range(min(len(jd_),len(ud_))): cands.append((jd_[a],ud_[a]))
    return cands

def _lis(cands):
    cands=sorted(set(cands))
    tails=[]; ti=[]; par=[-1]*len(cands)
    for i,(j,u) in enumerate(cands):
        p=bisect.bisect_left(tails,u)
        if p==len(tails): tails.append(u); ti.append(i)
        else: tails[p]=u; ti[p]=i
        par[i]=ti[p-1] if p>0 else -1
    lis=[]; cur=ti[-1] if ti else -1
    while cur!=-1: lis.append(cands[cur]); cur=par[cur]
    lis.reverse(); return lis

def build_map():
    # Pool block-boundary anchors (hard, structural) + term/demo anchors, run one global LIS.
    # Block anchors dominate because there are 118 of them, evenly spread and mutually consistent.
    cands = block_anchors() + term_anchors()
    lis=_lis(cands)
    A=[(0,0)]+lis+[(len(JM)-1,len(UM)-1)]
    clean=[A[0]]
    for j,u in A[1:]:
        if j>clean[-1][0] and u>=clean[-1][1]: clean.append((j,u))
    A=clean
    m={}; conf={}
    for (j0,u0),(j1,u1) in zip(A,A[1:]):
        sj=j1-j0; su=u1-u0
        for j in range(j0,j1):
            f=(j-j0)/sj if sj else 0
            m[j]=min(max(round(u0+f*su),0),len(UM)-1)
            conf[j]='HIGH' if sj<=8 else ('MED' if sj<=30 else 'LOW')
    m[len(JM)-1]=len(UM)-1; conf[len(JM)-1]='HIGH'
    return m, conf, A

if __name__=='__main__':
    m,conf,A=build_map()
    c=collections.Counter(conf.values())
    print(f'anchors={len(A)} (incl {len(block_anchors())} block-boundary)  HIGH={c["HIGH"]} MED={c["MED"]} LOW={c["LOW"]} ({c["HIGH"]/len(m)*100:.0f}/{c["MED"]/len(m)*100:.0f}/{c["LOW"]/len(m)*100:.0f})')
    NM={'ファルガイア':'filgaia','オデッサ':'odessa','ヴァレリア':'valeria','スレイハイム':'slayheim','アガートラーム':'argetlahm','ヴィンスフェルト':'vinsfeld','ロンバルディア':'lombardia','カイバーベルト':'kuiper','カイーナ':'caina','コキュートス':'cocytus'}
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
    biggest=max((A[i+1][0]-A[i][0]) for i in range(len(A)-1))
    print(f'  largest remaining gap: {biggest} msgs')
    import json
    json.dump({str(k):[v,conf[k]] for k,v in m.items()}, open('jp_us_alignment.json','w'))
    print('saved jp_us_alignment.json')
    for j in [3,35,860,5347,6021,7969]:
        print(f'  JP#{j}->US#{m[j]} [{conf[j]}]: {_ut(m[j])[:46]}')
