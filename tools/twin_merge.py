#!/usr/bin/env python3
"""Twin-merge: propagate solved block-local kanji across byte-identical/near-identical blocks.

WA2 reuses whole scripts in multiple STGEVT blocks (e.g. the lore-encyclopedia lives in 8/9/11).
Twins share their block-local subtable, so a code solved in one twin is solved in all — provided
the byte CONTEXT around that code matches (same preceding/following bytes), which proves it's the
same glyph slot and not a coincidental code collision.

Algorithm:
  1. For every block, index each local code (>=0x8a38) -> set of (prev2, next2) byte fingerprints.
  2. Pair blocks with >=THRESH fingerprint overlap on >=MINSHARED shared codes; union-find into clusters.
  3. Within a cluster, for each code: collect the readings proposed by members that already solved
     it AND whose fingerprint matches the target. If all agree -> propagate. If they DISAGREE
     (same code+context, different reading) -> that solve is unreliable; REMOVE it from every
     cluster member (a wrong decode is worse than an unsolved <b:xxxx>).
  MERGES into font_work/block_tables.json (never overwrites unrelated blocks).

Usage: python3 tools/twin_merge.py [--dry]
"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W

THRESH=0.90; MINSHARED=30
BT='font_work/block_tables.json'
KHI={0x88,0x89,0x8a,0x8b}

def local_fps(seg):
    out={}; j=0; n=len(seg)
    while j<n:
        c=seg[j]
        if c in KHI and j+1<n:
            code=(c<<8)|seg[j+1]
            if code>=0x8a38:
                fp=(bytes(seg[max(0,j-2):j]), bytes(seg[j+2:j+4]))
                out.setdefault(code,set()).add(fp); j+=2; continue
        j+=1
    return out

def main():
    dry='--dry' in sys.argv
    jd=W.load_jp(); nblocks=len(jd)//W.JBLK+1
    tabs={b:local_fps(W.block_bytes(jd,b)) for b in range(nblocks)}
    tabs={b:t for b,t in tabs.items() if t}
    blks=sorted(tabs)
    # union-find clusters
    parent={b:b for b in blks}
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def union(a,b): parent[find(a)]=find(b)
    for i,x in enumerate(blks):
        for y in blks[i+1:]:
            common=set(tabs[x])&set(tabs[y])
            if len(common)<MINSHARED: continue
            m=sum(1 for c in common if tabs[x][c]&tabs[y][c])
            if m/len(common)>=THRESH: union(x,y)
    clusters={}
    for b in blks: clusters.setdefault(find(b),[]).append(b)
    clusters={k:v for k,v in clusters.items() if len(v)>1}

    bt=json.load(open(BT))
    added=0; removed=0; conflicts=[]
    for members in clusters.values():
        # every local code seen anywhere in the cluster
        allcodes=set()
        for b in members: allcodes|=set(tabs[b])
        for code in allcodes:
            h=f'{code:04x}'
            # readings proposed by members that solved this code
            proposals={}   # reading -> [blocks]
            for b in members:
                r=bt.get(str(b),{}).get(h)
                if r: proposals.setdefault(r,[]).append(b)
            if not proposals: continue
            if len(proposals)>1:
                # disagreement: only a conflict if the disagreeing members share fingerprints
                conflicts.append((h,{r:bs for r,bs in proposals.items()}))
                for b in members:
                    if h in bt.get(str(b),{}):
                        del bt[str(b)][h]; removed+=1
                continue
            reading=next(iter(proposals))
            src_fps=set()
            for b in proposals[reading]: src_fps|=tabs[b].get(code,set())
            for b in members:
                if code not in tabs[b]: continue
                if h in bt.get(str(b),{}): continue
                if tabs[b][code]&src_fps:   # fingerprint match required
                    bt.setdefault(str(b),{})[h]=reading; added+=1
    if not dry:
        json.dump({k:dict(sorted(bt[k].items())) for k in sorted(bt,key=lambda x:int(x))},
                  open(BT,'w'), ensure_ascii=False, indent=0)
    print(f"clusters: {sorted(sorted(v) for v in clusters.values())}")
    print(f"{'DRY: ' if dry else ''}propagated +{added} solves | removed {removed} conflicted | {len(conflicts)} conflict codes")
    for h,p in conflicts[:20]: print(f"  conflict {h}: {p}")

if __name__=='__main__': main()
