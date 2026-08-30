"""
JP<->US alignment v6 — LINEBREAK-SEQUENCE alignment (the winner).
Discovery: the per-message linebreak count (0x0d) is script-structural and survives
translation almost exactly. Aligning the two linebreak-count sequences with difflib
matches ~72% of messages EXACTLY, with 57% in confident runs of >=4. We use those
matching runs as dense anchors, fill gaps by interpolation, and tag confidence by
whether a message is inside a matched run (HIGH) or an interpolated gap (MED/LOW).
Falls back to nothing else needed — this supersedes noun/block anchoring for coverage.
"""
import sys, difflib
sys.path.insert(0, 'tools')
import importlib, wa2_jp_decode
importlib.reload(wa2_jp_decode)
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
def _lb(d, s, e): return d[s:e].count(b'\x0d')
JL = [_lb(JD, JM[i], JM[i+1] if i+1<len(JM) else len(JD)) for i in range(len(JM))]
UL = [_lb(UD, UM[i], UM[i+1] if i+1<len(UM) else len(UD)) for i in range(len(UM))]

def _ut(i):
    seg = UD[UM[i]+2:UM[i]+2+400].split(b'\x00')[0]
    try: return seg.decode('ascii','replace')
    except: return ''

# guide-derived location/glossary anchors (JP katakana -> US spelling, counts verified close)
GUIDE_ANCHORS = {'damzen':'ダムツェン','sylvaland':'シルヴァラント','heimdal':'ヘイムダル','baskar':'バスカー',
'guild galad':'ギルドグラード','halmetz':'ハルメッツ','holst':'ホルスト','sielje':'シエルジェ',
'trapezohedron':'トラペゾヘドロン','grauswein':'グラウスヴァイン','lombardia':'ロンバルディア',
'argetlahm':'アガートラーム','telepath':'テレパス','golgotha':'ゴルゴダ','greenhell':'グリーンヘル',
'ptolomea':'トロメア','kuiper':'カイバーベルト','meria boule':'メリアブール','gias':'ギアス',
'pooka':'プーカ','quartly':'クアトリー','trapezohedron':'トラペゾヘドロン'}

def build_map():
    sm = difflib.SequenceMatcher(a=JL, b=UL, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size>0]
    jp2us = {}; conf = {}
    # 1) direct anchors from matching runs
    for b in blocks:
        for k in range(b.size):
            jp2us[b.a+k] = b.b+k
            conf[b.a+k] = 'HIGH' if b.size>=4 else 'MED'
    # 2) fill gaps between consecutive matched runs by interpolation
    anchors = sorted((b.a, b.b, b.size) for b in blocks)
    A = [(0,0,0)] + anchors + [(len(JM)-1, len(UM)-1, 1)]
    for (j0,u0,s0),(j1,u1,s1) in zip(A, A[1:]):
        gstart = j0 + s0          # first unmapped JP after this run
        gend = j1                 # next run start
        if gend <= gstart: continue
        uu0 = u0 + s0; uu1 = u1
        span_j = gend - gstart; span_u = uu1 - uu0
        for j in range(gstart, gend):
            if j in jp2us: continue
            frac = (j-gstart)/span_j if span_j else 0
            jp2us[j] = min(max(round(uu0 + frac*span_u), 0), len(UM)-1)
            conf[j] = 'LOW' if span_j > 8 else 'MED'
    for j in range(len(JM)):
        jp2us.setdefault(j, min(j, len(UM)-1)); conf.setdefault(j, 'LOW')
    # 3) guide-anchor refinement: for LOW lines containing a guide katakana term, snap to the
    # nearest US msg (within the current estimate ±40) that contains the matching EN spelling.
    JTX=[decode(JD[JM[i]+2:JM[i]+2+120]) for i in range(len(JM))]
    UL_txt=[None]*len(UM)
    def utl(i):
        if UL_txt[i] is None:
            seg=UD[UM[i]+2:UM[i]+2+200].split(b'\x00')[0]
            try: UL_txt[i]=seg.decode('ascii','replace').lower()
            except: UL_txt[i]=''
        return UL_txt[i]
    fixed=0
    for j in range(len(JM)):
        if conf[j]!='LOW': continue
        for en,ja in GUIDE_ANCHORS.items():
            if ja in JTX[j]:
                cur=jp2us[j]
                best=None
                for u in range(max(0,cur-40),min(len(UM),cur+41)):
                    if en in utl(u): best=u if best is None or abs(u-cur)<abs(best-cur) else best
                if best is not None and best!=cur:
                    jp2us[j]=best; conf[j]='MED'; fixed+=1
                break
    return jp2us, conf, blocks

if __name__=='__main__':
    import collections
    m, conf, blocks = build_map()
    c = collections.Counter(conf.values())
    tot = len(m)
    print(f'matching runs={len(blocks)}  HIGH={c["HIGH"]} MED={c["MED"]} LOW={c["LOW"]} ({c["HIGH"]/tot*100:.0f}/{c["MED"]/tot*100:.0f}/{c["LOW"]/tot*100:.0f})')
    # accuracy: proper-noun cross-check ±2
    from wa2_jp_decode import decode as dc
    JTX=[dc(JD[JM[i]+2:JM[i]+2+400]) for i in range(len(JM))]
    UTX=[_ut(i).lower() for i in range(len(UM))]
    NM={'ファルガイア':'filgaia','オデッサ':'odessa','ヴァレリア':'valeria','スレイハイム':'slayheim','アガートラーム':'argetlahm','ヴィンスフェルト':'vinsfeld','ロンバルディア':'lombardia','カイバーベルト':'kuiper','カイーナ':'caina','コキュートス':'cocytus'}
    tier=collections.defaultdict(lambda:[0,0])
    for j in range(len(JM)):
        for k,v in NM.items():
            if k in JTX[j]:
                hit=any(v in UTX[min(max(m[j]+d,0),len(UM)-1)] for d in range(-2,3))
                tier[conf[j]][0 if hit else 1]+=1
                break
    for t in ['HIGH','MED','LOW']:
        ok,bad=tier[t]; tt=ok+bad
        print(f'  {t}: {ok}/{tt} = {ok/tt*100:.0f}%' if tt else f'  {t}: -')
    import json
    json.dump({str(k):[v,conf[k]] for k,v in m.items()}, open('data/jp_us_alignment.json','w'))
    print('saved data/jp_us_alignment.json')
    for j in [3,35,860,5347,6021,7969]:
        print(f'  JP#{j}->US#{m[j]} [{conf[j]}]: {_ut(m[j])[:46]}')
