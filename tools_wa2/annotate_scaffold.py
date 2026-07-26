"""Annotate every translate/blkNNN.txt box with a per-box confidence + flags header line,
and prepend a block summary. Real metadata (no fabricated translations). Makes all 120
blocks a prioritized first-draft workspace."""
import sys, os, json, re
sys.path.insert(0,'tools_wa2')
import importlib, wa2_kanji_map, wa2_jp_decode
importlib.reload(wa2_kanji_map); importlib.reload(wa2_jp_decode)
from wa2_jp_decode import readfile, decode

JD=readfile('Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin',12601,13271040)
def jmsgs(d):
    o=[];i=0
    while True:
        i=d.find(b'\x10\x0c',i+1)
        if i<0 or i+2>=len(d):break
        o.append(i)
    return o
JM=jmsgs(JD)
def jtext(i): return decode(JD[JM[i]+2:JM[i]+2+400])

def conf_for(aln, uns):
    if aln=='HIGH' and uns==0: return 'OK'
    if aln=='LOW': return 'JP-ONLY'   # ignore EN, translate purely from JP
    if uns>=3: return 'SHAKY'
    if aln=='HIGH': return 'FAIR' if uns<=2 else 'SHAKY'
    return 'FAIR'  # MED, few unsolved

files=sorted(f for f in os.listdir('translate') if re.match(r'blk\d+\.txt$',f))
total_ok=total_fair=total_shaky=total_jponly=0
for fn in files:
    path='translate/'+fn
    lines=open(path).read().split('\n')
    out=[]; boxstat=[]
    for ln in lines:
        m=re.match(r'\[JP#(\d+)\]\s+gaps=\d+\s+aln=(\w+)',ln)
        if m:
            j=int(m.group(1)); aln=m.group(2)
            t=jtext(j)
            uns=len(re.findall(r'<8[0-9a-f]{3}>',t))
            c=conf_for(aln,uns)
            boxstat.append(c)
            out.append(ln.rstrip()+f'  CONF={c} unsolved={uns}')
        else:
            out.append(ln)
    # counts
    from collections import Counter
    cc=Counter(boxstat)
    total_ok+=cc.get('OK',0); total_fair+=cc.get('FAIR',0)
    total_shaky+=cc.get('SHAKY',0); total_jponly+=cc.get('JP-ONLY',0)
    # insert a summary after the header comment block (first '====' line)
    summ=f"# DRAFT STATUS: {len(boxstat)} boxes | OK={cc.get('OK',0)} FAIR={cc.get('FAIR',0)} SHAKY={cc.get('SHAKY',0)} JP-ONLY={cc.get('JP-ONLY',0)}"
    for k,l in enumerate(out):
        if l.startswith('===='):
            out.insert(k+1, summ); break
    open(path,'w').write('\n'.join(out))
print(f'annotated {len(files)} blocks')
print(f'TOTAL boxes: OK={total_ok} FAIR={total_fair} SHAKY={total_shaky} JP-ONLY={total_jponly}')
