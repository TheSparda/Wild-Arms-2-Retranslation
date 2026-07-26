import struct, json, sys, re
RAW,USER,HDR=2352,2048,24
def readfile(path,lba,size):
    f=open(path,"rb");o=bytearray();l=lba
    while len(o)<size:f.seek(l*RAW+HDR);o+=f.read(USER);l+=1
    return bytes(o[:size])

EN="games/Wild Arms 2/Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin"
ES="games/Wild Arms 2/WA2_CD1_spanish.bin"
ft=json.load(open("games/Wild Arms 2/filetable_cd1.json"))

def decode(bs):
    # printable ASCII + show control codes as <XX>
    out=[]
    for b in bs:
        if 32<=b<127: out.append(chr(b))
        else: out.append(f"<{b:02x}>")
    return ''.join(out)

def extract_ascii_strings(d, minlen=3):
    """Return list of (offset, rawbytes) for printable-ASCII runs."""
    res=[]; i=0
    while i<len(d):
        if 32<=d[i]<127:
            j=i
            while j<len(d) and 32<=d[j]<127: j+=1
            if j-i>=minlen: res.append((i, d[i:j]))
            i=j
        else: i+=1
    return res

def build(fname, lba, size, minlen=3):
    en=readfile(EN,lba,size); es=readfile(ES,lba,size)
    en_str=extract_ascii_strings(en,minlen)
    # index ES strings by offset for alignment
    es_map={off:raw for off,raw in extract_ascii_strings(es,minlen)}
    pairs=[]
    for off,raw in en_str:
        e=raw.decode('ascii')
        s=es_map.get(off)
        s_txt=s.decode('ascii','replace') if s else None
        changed = (s is not None and s!=raw)
        pairs.append({"file":fname,"offset":off,"offset_hex":hex(off),
                      "en":e,"es":s_txt if s_txt else "","changed":changed})
    return pairs

allpairs=[]
for fname in ["/EXE/WILDARM2.EXE","/STG/STGEVT.BIN","/SYS/UTIL.OVR","/SYS/MENU.OVR"]:
    lba,size=ft[fname]
    ps=build(fname,lba,size,minlen=3)
    allpairs+=ps
    ch=sum(1 for x in ps if x["changed"])
    print(f"{fname}: {len(ps)} strings, {ch} changed EN->ES")

# keep only meaningful entries: changed OR looks like real text (has space/lowercase)
def keep(x):
    e=x["en"]
    return x["changed"] or (' ' in e and sum(c.islower() for c in e)>=2 and len(e)>=4)
kept=[x for x in allpairs if keep(x)]
for x in kept: x["jp"]=""   # placeholder for later
json.dump(kept, open("games/Wild Arms 2/WA2_string_map.json","w"), ensure_ascii=False, indent=0)
print(f"\nTotal kept entries: {len(kept)}; changed(translated): {sum(1 for x in kept if x['changed'])}")
