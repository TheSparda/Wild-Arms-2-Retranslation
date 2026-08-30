"""Option-1 helper: for a given block, list its UNSOLVED local codes (>=0x8a38) ranked by
in-block frequency, each with up to N decoded contexts (block-aware) so they can be solved
from okurigana + neighbors. Also can WRITE solved readings into font_work/block_tables.json."""
import sys, json, collections, re
sys.path.insert(0,'tools')
import importlib, wa2_kanji_map, wa2_jp_decode
importlib.reload(wa2_kanji_map); importlib.reload(wa2_jp_decode)
from wa2_jp_decode import readfile, decode
K=wa2_kanji_map.KANJI
JD=readfile('Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin',12601,13271040)
JBLK=110592
BT_PATH='font_work/block_tables.json'
def load_bt(): 
    try: return json.load(open(BT_PATH))
    except: return {}
def save_bt(bt): json.dump(bt,open(BT_PATH,'w'),ensure_ascii=False,indent=0)
def msgs(d):
    o=[];i=0
    while True:
        i=d.find(b'\x10\x0c',i+1)
        if i<0 or i+2>=len(d):break
        o.append(i)
    return o
jm=msgs(JD)

def block_decode(block, code_override=None):
    """decode all msgs of a block, applying global map + this block's table + overrides"""
    bt=load_bt().get(str(block),{})
    if code_override: bt={**bt,**code_override}
    def dec(seg):
        out=[];j=0
        while j<len(seg):
            c=seg[j]
            if c in (0x88,0x89,0x8a,0x8b) and j+1<len(seg):
                code=(c<<8)|seg[j+1]; h=f'{code:04x}'
                if code>=0x8a38:
                    out.append(bt.get(h, K.get(h,'<b:'+h+'>')) if h in bt else '<b:'+h+'>' if h not in K else K[h])
                    # prefer block table; fall back to '<b:>' for unsolved (ignore global for local tier)
                    out[-1]= bt.get(h) or ('<b:'+h+'>')
                    j+=2; continue
                else:
                    out.append(K.get(h,'<'+h+'>')); j+=2; continue
            # delegate rest to standard decode for correctness on kana/controls
            # (simplify: use global decode on a 1-char slice won't work; fallback below)
            j+=1
        return None
    # Simpler: use global decode() then post-substitute local codes via a raw re-scan
    res=[]
    for mi in range(len(jm)):
        if jm[mi]//JBLK != block: continue
        e=jm[mi+1] if mi+1<len(jm) else len(JD)
        seg=JD[jm[mi]:e].split(b'\x00')[0]
        txt=decode(seg)
        # post-fix: any <xxxx> or globally-mapped char for a >=8a38 code — re-scan raw to override
        # Build ordered list of local codes in this msg:
        locals_in=[]; j=0
        while j<len(seg)-1:
            c=seg[j]
            if c in (0x88,0x89,0x8a,0x8b):
                code=(c<<8)|seg[j+1]
                if code>=0x8a38: locals_in.append(f'{code:04x}')
                j+=2
            elif c in (0xf0,0x05,0x0a,0x0b,0x10,0x11,0x13,0x16,0x17,0x18): j+=2
            else: j+=1
        res.append((mi, seg, txt, locals_in))
    return res

def list_unsolved(block, topn=40, ctxn=3):
    bt=load_bt().get(str(block),{})
    freq=collections.Counter(); ctx=collections.defaultdict(list)
    for mi in range(len(jm)):
        if jm[mi]//JBLK!=block: continue
        e=jm[mi+1] if mi+1<len(jm) else len(JD)
        seg=JD[jm[mi]:e].split(b'\x00')[0]
        j=0
        while j<len(seg)-1:
            c=seg[j]
            if c in (0x88,0x89,0x8a,0x8b):
                code=(c<<8)|seg[j+1]; h=f'{code:04x}'
                if code>=0x8a38 and h not in bt:
                    freq[h]+=1
                    if len(ctx[h])<ctxn:
                        # decode a window using block table so neighbors show
                        wtxt=decode(seg[max(0,j-14):j+16])
                        ctx[h].append(wtxt.replace('\n','/'))
                j+=2
            elif c in (0xf0,0x05,0x0a,0x0b,0x10,0x11,0x13,0x16,0x17,0x18): j+=2
            else: j+=1
    print(f'BLOCK {block}: {len(freq)} unsolved local codes, {sum(freq.values())} occurrences')
    for h,n in freq.most_common(topn):
        print(f'  {h} x{n}')
        for cx in ctx[h]: print(f'      …{cx}…')

def solve(block, mapping:dict):
    bt=load_bt()
    b=str(block); bt.setdefault(b,{})
    bt[b].update(mapping)
    save_bt(bt)
    print(f'block {block}: +{len(mapping)} readings -> {len(bt[b])} total')

if __name__=='__main__':
    cmd=sys.argv[1]
    if cmd=='list': list_unsolved(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv)>3 else 40)
    elif cmd=='solve':
        block=int(sys.argv[2]); m=json.loads(sys.argv[3]); solve(block,m)
