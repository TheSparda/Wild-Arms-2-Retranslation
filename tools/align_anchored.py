"""
Anchored JP<->US alignment for WA2 STGEVT — v2.
Key finding: the JP->US index offset starts ~0 and drifts monotonically to ~-120..-190
by end (accumulating local insertions). Proper-noun occurrence lists track ~1:1, so
their k-th<->k-th pairings form a dense, globally-monotonic anchor scatter. We take the
longest strictly-increasing subsequence of all pairings (robust to a few mispairs), then
linearly interpolate US index between anchors. Confidence = tightness of bracketing anchors.
"""
import sys, re
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
def jt(i): return decode(JD[JM[i]+2:JM[i]+2+400])
def ut(i):
    seg = UD[UM[i]+2:UM[i]+2+400].split(b'\x00')[0]
    try: return seg.decode('ascii', 'replace')
    except: return ''

# rare, distinctive nouns first (best anchors); include common ones for density
NOUNS = [('アガートラーム','Argetlahm'),('カイバーベルト','Kuiper'),('ロンバルディア','Lombardia'),
('ミーディアム','Medium'),('ヴィンスフェルト','Vinsfeld'),('スレイハイム','Slayheim'),
('ヴァレリア','Valeria'),('ガーディアン','Guardian'),('オデッサ','Odessa'),('ファルガイア','Filgaia'),
('コキュートス','Cocytus'),('ジュデッカ','Judecca'),('アンテノーラ','Antenora'),('メリアブール','Meria')]

def occ():
    J={}; U={}
    for kata,latin in NOUNS:
        J[latin]=[i for i in range(len(JM)) if kata in jt(i)]
        U[latin]=[i for i in range(len(UM)) if latin in ut(i)]
    return J,U

def build_anchors():
    J,U=occ()
    cands=[]
    for _,latin in NOUNS:
        js,us=J[latin],U[latin]
        k=min(len(js),len(us))
        for a in range(k):
            cands.append((js[a],us[a]))
    # dedupe + sort by JP
    cands=sorted(set(cands))
    # longest strictly-increasing (in US) subsequence  -> O(n log n) patience sorting
    import bisect
    tails=[]; tails_idx=[]; parent=[-1]*len(cands); pos=[0]*len(cands)
    for i,(j,u) in enumerate(cands):
        p=bisect.bisect_left(tails,u)
        if p==len(tails): tails.append(u); tails_idx.append(i)
        else: tails[p]=u; tails_idx[p]=i
        parent[i]=tails_idx[p-1] if p>0 else -1
        pos[i]=p
    # reconstruct
    lis=[]; cur=tails_idx[-1] if tails_idx else -1
    while cur!=-1: lis.append(cands[cur]); cur=parent[cur]
    lis.reverse()
    return lis

def build_map():
    A=[(0,0)]+build_anchors()+[(len(JM)-1,len(UM)-1)]
    # ensure strictly increasing
    clean=[A[0]]
    for j,u in A[1:]:
        if j>clean[-1][0] and u>=clean[-1][1]: clean.append((j,u))
    A=clean
    jp2us={}; conf={}
    for (j0,u0),(j1,u1) in zip(A,A[1:]):
        sj=j1-j0; su=u1-u0
        for j in range(j0,j1):
            frac=(j-j0)/sj if sj else 0
            jp2us[j]=min(max(round(u0+frac*su),0),len(UM)-1)
            conf[j]='HIGH' if sj<=8 else ('MED' if sj<=30 else 'LOW')
    jp2us[len(JM)-1]=len(UM)-1; conf[len(JM)-1]='HIGH'
    return jp2us,conf,A

if __name__=='__main__':
    m,conf,A=build_map()
    from collections import Counter
    c=Counter(conf.values())
    print(f'anchors={len(A)}  mapped={len(m)}  conf={dict(c)}')
    print(f'HIGH={c["HIGH"]/len(m)*100:.1f}%  MED={c["MED"]/len(m)*100:.1f}%  LOW={c["LOW"]/len(m)*100:.1f}%')
    print('\nspot check:')
    for j in [3,35,200,860,1266,5006,5347,6021,7969]:
        if j in m:
            print(f'  JP#{j}: {jt(j)[:30].strip():32} -> US#{m[j]}: {ut(m[j])[:46].strip()}  [{conf[j]}]')
