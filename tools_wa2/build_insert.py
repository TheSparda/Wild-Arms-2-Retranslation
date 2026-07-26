"""
Build the EN-slot-centric INSERTION workspace.
One row per US (EN) box = the insertable slot. For each box we show:
  - the box's HARD budget: visible-char count + line count (the size the retranslation must fit)
  - the current EN text (what's there now)
  - the JP source that maps to this box (reverse of v6 alignment) + its confidence
  - a FIT field: the retranslation, constrained to the budget (hand-filled)
This is the correct frame: we fill existing EN boxes, we don't create new ones.
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

def jp_text(i): return decode(JD[JM[i]+2:JM[i]+2+400]).replace('\n',' / ')
def us_raw(i):
    e = UM[i+1] if i+1<len(UM) else len(UD)
    return UD[UM[i]:e].split(b'\x00')[0]
def us_disp(i):
    seg = us_raw(i)
    out=[]
    for b in seg:
        if b==0x0d: out.append('\n         ')      # line break -> newline in display
        elif 0x20<=b<0x7f and b!=0x40: out.append(chr(b))
        elif b==0x40: out.append('')                # @ speaker marker, hide in display
    return ''.join(out).strip()
def budget(i):
    seg=us_raw(i)
    vis=len([b for b in seg if 0x20<=b<0x7f and b!=0x40])
    lines=seg.count(b'\x0d')+1
    return vis, lines

# reverse the v6 map: US box -> the JP msg(s) that map to it
AL = json.load(open('jp_us_alignment.json'))
us2jp = {}
for js,(u,c) in AL.items():
    us2jp.setdefault(int(u), []).append((int(js),c))

def build(us_lo, us_hi, path, title=''):
    out=[f"# WA2 INSERTION workspace {title}".rstrip(),
    "# One row per US BOX (the slot we fill). Retranslation MUST fit budget.",
    "# budget = max visible chars / lines available in this box (same-size safe insert).",
    "# JP = source line(s) mapped to this box (aln conf). FIT = retranslation within budget (TODO).",
    "="*84]
    for u in range(us_lo, us_hi):
        vis,lines = budget(u)
        if vis==0: continue   # control-only box, nothing to translate
        cur = us_disp(u)
        jps = us2jp.get(u, [])
        jp_str = ' || '.join(f'JP#{j}[{c}]: {jp_text(j)[:80]}' for j,c in jps[:2]) or '(no JP mapped)'
        out.append(f"\n[US#{u}] budget={vis}ch/{lines}ln")
        out.append(f"  NOW: {cur}")
        out.append(f"  JP : {jp_str}")
        out.append(f"  FIT: <<TODO — <={vis} chars, {lines} line(s), <=35/line>>")
    open(path,'w').write('\n'.join(out))
    return sum(1 for l in out if l.startswith('[US#'))

if __name__=='__main__':
    if len(sys.argv)>=3:
        lo,hi=int(sys.argv[1]),int(sys.argv[2]); path=sys.argv[3] if len(sys.argv)>3 else 'WA2_insert.txt'
        n=build(lo,hi,path); print(f'wrote {path}: {n} slots')
    else:
        import os
        os.makedirs('insert',exist_ok=True)
        UBLK=90112
        def blk(i): return UM[i]//UBLK
        cur=blk(0); start=0; nf=0
        for i in range(1,len(UM)+1):
            if i==len(UM) or blk(i)!=cur:
                build(start,i,f'insert/blk{cur:03d}.txt',f'US block {cur} (US#{start}-{i-1})'); nf+=1
                if i<len(UM): cur=blk(i); start=i
        print(f'wrote {nf} insertion block files to insert/')
