import struct, sys, json, os
RAW,USER,HDR=2352,2048,24
def read_region(path,lba,nbytes):
    nsec=(nbytes+USER-1)//USER
    with open(path,"rb") as f:
        f.seek(lba*RAW); raw=f.read(nsec*RAW)
    return b"".join(raw[s*RAW+HDR:s*RAW+HDR+USER] for s in range(nsec))

CHARID={0x0530:"Ashley",0x0531:"Brad",0x0532:"Lilka",0x0533:"Tim",0x0534:"Kanon",0x0535:"Marivel",
        0x0A30:"Irving",0x0A31:"Alta",0x0A32:"Mari",0x0A33:"Cole",0x0A34:"Bill",0x0A35:"Tony",
        0x0A36:"Scot",0x0A37:"Dog",0x0A42:"Terr",0x0A43:"Poka"}

def extract(d):
    """Return (offset, char, text) for ASCII runs >=3, with 0x0d shown as \\n inside runs."""
    out=[]; i=0; n=len(d)
    while i<n:
        b=d[i]
        if 0x20<=b<0x7f:
            st=i; buf=bytearray()
            while i<n:
                c=d[i]
                if 0x20<=c<0x7f: buf.append(c); i+=1
                elif c==0x0d: buf.append(0x0a); i+=1   # line break -> newline, keep run going
                else: break
            if sum(1 for x in buf if x!=0x0a)>=3:
                cid=None
                for k in (2,3):
                    if st>=k:
                        w=(d[st-k]<<8)|d[st-k+1]
                        if w in CHARID: cid=CHARID[w]; break
                out.append((st, cid, buf.decode('ascii','replace')))
        else: i+=1
    return out

def dump_disc(binp, ft, discname, outdir):
    os.makedirs(outdir, exist_ok=True)
    total=0
    for fname in ["/STG/STGEVT.BIN","/EXE/WILDARM2.EXE","/SYS/UTIL.OVR","/SYS/MENU.OVR"]:
        if fname not in ft: continue
        lba,size=ft[fname]
        d=read_region(binp,lba,size)
        runs=extract(d)
        # filter to meaningful text: has lowercase+space OR a char tag
        keep=[(o,c,t) for o,c,t in runs if c or (' ' in t and sum(x.islower() for x in t)>=2)]
        safe=fname.strip("/").replace("/","_")
        with open(f"{outdir}/{safe}.txt","w") as f:
            f.write(f"# {discname} {fname} — {len(keep)} strings\n\n")
            for o,c,t in keep:
                tag=f"[{c}] " if c else ""
                f.write(f"@0x{o:06x} {tag}{t}\n")
        total+=len(keep)
        print(f"  {fname}: {len(keep)} strings -> {safe}.txt")
    return total

ft1=json.load(open("games/Wild Arms 2/filetable_cd1.json"))
ft2=json.load(open("games/Wild Arms 2/filetable_cd2.json"))
D1="games/Wild Arms 2/Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin"
D2="games/Wild Arms 2/Game Files/Wild Arms 2 (USA) (Disc 2)/Wild Arms 2 (USA) (Disc 2).bin"
print("=== DISC 1 ===")
t1=dump_disc(D1,ft1,"Disc1","games/Wild Arms 2/english_script/disc1")
print("=== DISC 2 ===")
t2=dump_disc(D2,ft2,"Disc2","games/Wild Arms 2/english_script/disc2")
print(f"\nTOTAL English strings dumped: {t1+t2} (disc1={t1}, disc2={t2})")
