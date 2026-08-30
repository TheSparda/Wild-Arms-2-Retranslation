"""Per-block local kanji table solver (codes >= 0x8a38).
Signals:
  A) TWIN LINES: messages whose GLOBAL-tier skeleton (kana + global kanji + controls) is identical
     across blocks -> their local codes at matching positions denote the SAME kanji.
     Propagates known readings between blocks (union-find over (block,code) slots).
  B) SEED READINGS: existing map entries >=0x8a38 seeded ONLY into the block(s) where their
     witness evidence lived is unknown -> instead seed from tutorial-solved lines whose block
     is known (blk0 tutorial solves are block-0-truth; twin lines spread them).
Output: font_work/block_tables.json  {block: {code_hex: kanji}}
"""
import sys, json, collections
sys.path.insert(0,'tools')
import importlib, wa2_kanji_map
importlib.reload(wa2_kanji_map)
from wa2_jp_decode import readfile
K = wa2_kanji_map.KANJI
JD = readfile('Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin',12601,13271040)
JBLK = 110592
BOUND = 0x8a38
CTRL2 = {0xf0,0x05,0x0a,0x0b,0x10,0x11,0x13,0x16,0x17,0x18}
KHI = {0x88,0x89,0x8a,0x8b}

def msgs(d):
    o=[];i=0
    while True:
        i=d.find(b'\x10\x0c',i+1)
        if i<0 or i+2>=len(d):break
        o.append(i)
    return o
jm = msgs(JD)
def raw(i):
    e=jm[i+1] if i+1<len(jm) else len(JD)
    return JD[jm[i]:e].split(b'\x00')[0]
def blk(i): return jm[i]//JBLK

# tokenize: produce (skeleton_key, local_positions) — skeleton replaces local codes with a
# placeholder; local_positions lists the local codes in order.
def tok(b):
    skel=[]; locs=[]
    j=0
    while j<len(b):
        c=b[j]
        if c in KHI and j+1<len(b):
            code=(c<<8)|b[j+1]
            if code>=BOUND:
                skel.append('L'); locs.append(code)
            else:
                skel.append(f'{code:04x}')
            j+=2
        elif c in CTRL2 and j+1<len(b):
            skel.append(f'c{c:02x}{b[j+1]:02x}'); j+=2
        else:
            skel.append(f'b{c:02x}'); j+=1
    return '|'.join(skel), locs

# group messages by skeleton
groups=collections.defaultdict(list)
for i in range(len(jm)):
    r=raw(i)
    if len(r)<8: continue
    s,l=tok(r)
    if not l: continue          # only care about msgs WITH local codes
    if s.count('L')==0: continue
    groups[s].append((i,tuple(l)))

# union-find over (block,code)
parent={}
def find(x):
    while parent.get(x,x)!=x: x=parent[x]=parent.get(parent.get(x,x),parent.get(x,x))
    return x
def union(a,b):
    ra,rb=find(a),find(b)
    if ra!=rb: parent[ra]=rb

twin_groups=0; twin_links=0
for s,members in groups.items():
    # dedupe same block (repeats within a block share codes trivially)
    seen={}
    for i,l in members:
        seen.setdefault(blk(i), l)
    bs=list(seen.items())
    if len(bs)<2: continue
    twin_groups+=1
    base_b, base_l = bs[0]
    for b2,l2 in bs[1:]:
        if len(l2)!=len(base_l): continue
        for x,y in zip(base_l,l2):
            union((base_b,x),(b2,y)); twin_links+=1

# seeds: current map's local entries — assign to EVERY block where using that reading the
# witness compound was found... we don't have that provenance; instead: tutorial-zone solves
# (blk0) are block-0 truth for these codes:
SEED_BLK0 = {0x8a38:'場',0x8a39:'限',0x8a3a:'仲?',0x8a3b:'守?',0x8a3d:'平',0x8a3e:'坦',
             0x8a53:'写',0x8a54:'真',0x8a55:'沿',0x8a56:'図',0x8a57:'図?',0x8a34:'右',0x8a33:'左'}
# NOTE: 8a33/8a34 < BOUND? 8a33<8a38 -> global. filter:
SEED_BLK0={c:ch for c,ch in SEED_BLK0.items() if c>=BOUND and not ch.endswith('?')}
# blk3 truths from batch-4 (solved in the PS-skills text which lives in blk3):
SEED_BLK3 = {0x8ab3:'習',0x8ab8:'効',0x8ab9:'費',0x8aba:'与',0x8abb:'制',0x8a52:'加',0x8a57:'事'}
SEED_BLK3={c:ch for c,ch in SEED_BLK3.items() if c>=BOUND}

cluster_read={}
conflicts=[]
for seeds,b in ((SEED_BLK0,0),(SEED_BLK3,3)):
    for c,ch in seeds.items():
        r=find((b,c))
        if r in cluster_read and cluster_read[r]!=ch:
            conflicts.append((r,cluster_read[r],ch))
        cluster_read[r]=ch

# build tables
tables=collections.defaultdict(dict)
solved=0
allslots=set(parent.keys())|{(b,c) for seeds,b in ((SEED_BLK0,0),(SEED_BLK3,3)) for c in seeds}
for slot in allslots:
    r=find(slot)
    if r in cluster_read:
        b,c=slot
        tables[b][f'{c:04x}']=cluster_read[r]
        solved+=1
print(f'twin groups (multi-block): {twin_groups}, links: {twin_links}')
print(f'cluster count: {len(set(find(x) for x in parent))}')
print(f'seeded readings: {len(cluster_read)}, conflicts: {len(conflicts)}')
print(f'slots solved via propagation: {solved} across {len(tables)} blocks')
json.dump({str(b):t for b,t in sorted(tables.items())}, open('font_work/block_tables.json','w'), ensure_ascii=False, indent=0)
