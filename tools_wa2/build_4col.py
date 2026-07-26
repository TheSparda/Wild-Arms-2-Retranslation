"""
Build the 4-column translation working doc — v2, wired to v6 alignment.
Auto-fills:
  [1] JP raw decode
  [3] current EN, via align_v6 jp_us_alignment map (correct pairing) + confidence flag
Leaves TODO for hand translation:
  [2] JP->EN literal
  [4] retranslation from JP
Confidence flag tells the translator whether to trust col-3 (HIGH/MED) or ignore it and
translate purely from JP (LOW). Emits per block/scene so it's reviewable in chunks.
"""
import sys, re, json
sys.path.insert(0, 'tools_wa2')
import importlib, wa2_kanji_map, wa2_jp_decode
importlib.reload(wa2_kanji_map); importlib.reload(wa2_jp_decode)
from wa2_jp_decode import readfile, decode

JD = readfile('Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin', 12601, 13271040)
UD = readfile('Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin', 12586, 10813440)
def msgs(d):
    o=[]; i=0
    while True:
        i=d.find(b'\x10\x0c', i+1)
        if i<0 or i+2>=len(d): break
        o.append(i)
    return o
JM = msgs(JD); UM = msgs(UD)
def jt(i): return decode(JD[JM[i]+2:JM[i]+2+400]).replace('\n',' / ')
def ut(i):
    seg = UD[UM[i]+2:UM[i]+2+400].split(b'\x00')[0]
    try: return seg.decode('ascii','replace').replace('\n',' ')
    except: return ''

# load v6 alignment (build it if missing)
try:
    AL = json.load(open('jp_us_alignment.json'))
except FileNotFoundError:
    import align_v6 as V
    m,conf,_=V.build_map()
    AL={str(k):[v,conf[k]] for k,v in m.items()}
def us_of(j): return AL.get(str(j),[min(j,len(UM)-1),'LOW'])

def build(lo, hi, path, title=''):
    out=[]
    out.append(f"# WA2 4-col translation doc {title}".rstrip())
    out.append("# [1]JP raw  [2]JP->EN literal(TODO)  [3]current EN + [aln]  [4]retranslation from JP(TODO)")
    out.append("# aln HIGH/MED = col3 trustworthy as cross-check; aln LOW = ignore col3, translate from JP.")
    out.append("# <xxxx> = unsolved kanji.  Speaker codes [05xx]/[0Axx] = char IDs (not text).")
    out.append("="*84)
    for i in range(lo, hi):
        jp=jt(i)
        if not jp.strip() or jp.strip() in ('[17]','[07]'): continue
        u,c=us_of(i)
        gaps=jp.count('<')
        out.append(f"\n[JP#{i}] gaps={gaps}  aln={c}->US#{u}")
        out.append(f"  1|JP : {jp}")
        out.append(f"  2|LIT: <<TODO>>")
        out.append(f"  3|EN : {ut(u)}")
        out.append(f"  4|RE : <<TODO>>")
    open(path,'w').write('\n'.join(out))
    return sum(1 for line in out if line.startswith('[JP#'))

if __name__=='__main__':
    if len(sys.argv)>=3:
        lo,hi=int(sys.argv[1]),int(sys.argv[2])
        path=sys.argv[3] if len(sys.argv)>3 else 'WA2_4col.txt'
        n=build(lo,hi,path); print(f'wrote {path}: {n} lines')
    else:
        # full script, split into block-sized files under translate/
        import os
        os.makedirs('translate',exist_ok=True)
        BLK=110592
        # block index per msg
        def blk(i): return JM[i]//BLK
        cur=blk(0); start=0; nfiles=0
        for i in range(1,len(JM)+1):
            if i==len(JM) or blk(i)!=cur:
                path=f'translate/blk{cur:03d}.txt'
                build(start,i,path,f'block {cur} (JP#{start}-{i-1})')
                nfiles+=1;
                if i<len(JM): cur=blk(i); start=i
        print(f'wrote {nfiles} block files to translate/')
