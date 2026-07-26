"""
JP<->US alignment v3 — dense auto-anchoring via romanized katakana.
Katakana loanwords/names romanize to something close to their US spelling. We harvest
all distinctive katakana tokens, romanize them, and match each JP occurrence to the US
message (near the expected position) whose text contains the romanized form. This yields
hundreds of anchors spread across the whole script, not just a dozen hand-picked nouns.
"""
import sys, re, bisect, collections
sys.path.insert(0, 'tools_wa2')
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
UTX = [ut(i).lower() for i in range(len(UM))]

# minimal katakana->romaji (consonant+vowel); enough for fuzzy substring matching
ROMA = {
'ヴァ':'va','ヴィ':'vi','ヴェ':'ve','ヴォ':'vo','ヴ':'v','ファ':'fa','フィ':'fi','フェ':'fe','フォ':'fo',
'ディ':'di','ドゥ':'du','ティ':'ti','トゥ':'tu','チェ':'che','シェ':'she','ジェ':'je',
'キャ':'kya','キュ':'kyu','キョ':'kyo','シャ':'sha','シュ':'shu','ショ':'sho','チャ':'cha','チュ':'chu','チョ':'cho',
'ニャ':'nya','ヒャ':'hya','ミャ':'mya','リャ':'rya','リュ':'ryu','リョ':'ryo','ギャ':'gya','ジャ':'ja','ジュ':'ju','ジョ':'jo','ビャ':'bya','ピャ':'pya',
'ア':'a','イ':'i','ウ':'u','エ':'e','オ':'o','カ':'ka','キ':'ki','ク':'ku','ケ':'ke','コ':'ko',
'サ':'sa','シ':'shi','ス':'su','セ':'se','ソ':'so','タ':'ta','チ':'chi','ツ':'tsu','テ':'te','ト':'to',
'ナ':'na','ニ':'ni','ヌ':'nu','ネ':'ne','ノ':'no','ハ':'ha','ヒ':'hi','フ':'fu','ヘ':'he','ホ':'ho',
'マ':'ma','ミ':'mi','ム':'mu','メ':'me','モ':'mo','ヤ':'ya','ユ':'yu','ヨ':'yo',
'ラ':'ra','リ':'ri','ル':'ru','レ':'re','ロ':'ro','ワ':'wa','ヲ':'wo','ン':'n',
'ガ':'ga','ギ':'gi','グ':'gu','ゲ':'ge','ゴ':'go','ザ':'za','ジ':'ji','ズ':'zu','ゼ':'ze','ゾ':'zo',
'ダ':'da','ヂ':'ji','ヅ':'zu','デ':'de','ド':'do','バ':'ba','ビ':'bi','ブ':'bu','ベ':'be','ボ':'bo',
'パ':'pa','ピ':'pi','プ':'pu','ペ':'pe','ポ':'po','ー':'','ッ':'',
}
def romaji(kata):
    out=[]; i=0
    while i<len(kata):
        if i+1<len(kata) and kata[i:i+2] in ROMA: out.append(ROMA[kata[i:i+2]]); i+=2
        elif kata[i] in ROMA: out.append(ROMA[kata[i]]); i+=1
        else: i+=1
    return ''.join(out)

def harvest():
    kat=collections.Counter()
    for i in range(len(JM)):
        for m in re.findall(r'[ァ-ヴ][ァ-ヴー]{3,}', jt(i)): kat[m]+=1
    # keep distinctive (appear 2-80 times), romaji length >=4
    terms={}
    for k,c in kat.items():
        if 2<=c<=80:
            r=romaji(k)
            if len(r)>=4: terms[k]=r
    return terms

def build_anchors():
    terms=harvest()
    # precompute JP occurrence indices per term
    cands=[]
    for kata,rom in terms.items():
        js=[i for i in range(len(JM)) if kata in jt(i)]
        if not js: continue
        # match each JP occurrence to a US msg containing the romaji, choosing the US index
        # closest to a rough linear expectation (US ~ JP * (len(UM)/len(JM)))
        scale=len(UM)/len(JM)
        us_hits=[i for i in range(len(UM)) if rom in UTX[i]]
        if not us_hits: continue
        for a,j in enumerate(js):
            exp=j*scale
            # nearest US hit to expectation
            b=min(us_hits,key=lambda u:abs(u-exp))
            if abs(b-exp)<400:  # reject wild matches
                cands.append((j,b))
    cands=sorted(set(cands))
    # longest strictly-increasing-in-US subsequence
    tails=[]; tails_i=[]; parent=[-1]*len(cands)
    for i,(j,u) in enumerate(cands):
        p=bisect.bisect_left(tails,u)
        if p==len(tails): tails.append(u); tails_i.append(i)
        else: tails[p]=u; tails_i[p]=i
        parent[i]=tails_i[p-1] if p>0 else -1
    lis=[]; cur=tails_i[-1] if tails_i else -1
    while cur!=-1: lis.append(cands[cur]); cur=parent[cur]
    lis.reverse()
    return lis

def build_map():
    A=[(0,0)]+build_anchors()+[(len(JM)-1,len(UM)-1)]
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
    c=collections.Counter(conf.values())
    print(f'anchors={len(A)}  conf HIGH={c["HIGH"]} MED={c["MED"]} LOW={c["LOW"]}  ({c["HIGH"]/len(m)*100:.0f}/{c["MED"]/len(m)*100:.0f}/{c["LOW"]/len(m)*100:.0f})')
    # noun accuracy check
    NM={'ファルガイア':'filgaia','オデッサ':'odessa','ヴァレリア':'valeria','スレイハイム':'slayheim','アガートラーム':'argetlahm','ガーディアン':'guardian','ヴィンスフェルト':'vinsfeld','カイーナ':'caina'}
    ok=bad=0
    for j in range(len(JM)):
        jp=jt(j)
        for k,v in NM.items():
            if k in jp:
                if v in UTX[m[j]]: ok+=1
                else: bad+=1
                break
    print(f'ALL-msg noun cross-check: {ok}/{ok+bad} = {ok/(ok+bad)*100:.0f}% land on the right US msg')
    for j in [6021,7969]:
        print(f'  JP#{j} -> US#{m[j]}: {ut(m[j])[:50]}')
