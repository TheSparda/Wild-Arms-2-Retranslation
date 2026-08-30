import sys, json
sys.path.insert(0,"games/Wild Arms 2/tools")
from wa2lib import readfile
import re

CHARID={0x0530:"Ashley",0x0531:"Brad",0x0532:"Lilka",0x0533:"Tim",0x0534:"Kanon",0x0535:"Marivel",
        0x0A30:"Irving",0x0A31:"Alta",0x0A32:"Mari",0x0A33:"Cole",0x0A34:"Bill",0x0A35:"Tony",
        0x0A36:"Scot",0x0A37:"Dog",0x0A42:"Terr",0x0A43:"Poka"}

def extract_runs(d, jp=False, minlen=3):
    runs=[]; i=0; n=len(d)
    while i<n:
        b=d[i]
        if 0x20<=b<0x7f or (jp and (0x81<=b<=0x9f or 0xe0<=b<=0xfc)):
            start=i; buf=bytearray()
            while i<n:
                b=d[i]
                if 0x20<=b<0x7f: buf.append(b); i+=1
                elif jp and (0x81<=b<=0x9f or 0xe0<=b<=0xfc) and i+1<n and 0x40<=d[i+1]<=0xfc and d[i+1]!=0x7f:
                    buf+=d[i:i+2]; i+=2
                else: break
            if len(buf)>=minlen:
                txt=buf.decode('shift_jis','replace') if jp else buf.decode('ascii','replace')
                cid=None
                if start>=2:
                    w=(d[start-2]<<8)|d[start-1]
                    if w in CHARID: cid=CHARID[w]
                    elif start>=3:
                        w2=(d[start-3]<<8)|d[start-2]
                        if w2 in CHARID: cid=CHARID[w2]
                runs.append({"off":start,"text":txt,"char":cid})
        else: i+=1
    return runs

EN="games/Wild Arms 2/Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin"
JP="games/Wild Arms 2/Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin"
ES="games/Wild Arms 2/WA2_CD1_spanish.bin"
print("reading files...")
en=readfile(EN,12586,10813440); es=readfile(ES,12586,10813440); jp=readfile(JP,12601,13271040)
print("extracting runs...")
er=extract_runs(en); sr=extract_runs(es); jr=extract_runs(jp,jp=True)
print(f"EN={len(er)} ES={len(sr)} JP={len(jr)} runs")
json.dump({"en":er,"es":sr,"jp":jr}, open("games/Wild Arms 2/tools/stgevt_runs.json","w"), ensure_ascii=False)
print("saved stgevt_runs.json")
# quick sample
ed=[r for r in er if ' ' in r['text'] or r['char']]
print("\nEN dialogue sample:")
for r in ed[:6]: print(f"  0x{r['off']:x} [{r['char']}] {r['text'][:45]!r}")
jd=[r for r in jr if len(r['text'])>=2]
print("JP sample:")
for r in jd[:6]: print(f"  0x{r['off']:x} [{r['char']}] {r['text'][:20]!r}")
