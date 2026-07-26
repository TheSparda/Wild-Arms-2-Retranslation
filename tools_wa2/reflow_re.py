#!/usr/bin/env python3
"""Reflow the RE blocks of an insert file so every line is <=35 chars and <=3 lines.
Joins the existing RE lines (preserving explicit sentence breaks lightly) and greedily
re-wraps by words. If it can't fit in 3x35, it reports the US# so it can be shortened by hand.
Usage: python3 tools_wa2/reflow_re.py insert/<file>   (in place)
"""
import re,sys
WIDTH=35; MAXL=3
def wrap(words):
    lines=[""]
    for w in words:
        if not lines[-1]: cand=w
        else: cand=lines[-1]+" "+w
        if len(cand)<=WIDTH: lines[-1]=cand
        else: lines.append(w)
    return lines
def main():
    path=sys.argv[1]
    src=open(path).read().split('\n'); out=[]; i=0; over=[]
    while i<len(src):
        ln=src[i]; m=re.match(r'^\[US#(\d+)\]',ln)
        out.append(ln)
        if not m: i+=1; continue
        us=m.group(1); i+=1
        # copy through until RE:
        while i<len(src) and not re.match(r'^\s{2}RE\s*:',src[i]) and not re.match(r'^\[US#',src[i]):
            out.append(src[i]); i+=1
        if i>=len(src) or not re.match(r'^\s{2}RE\s*:',src[i]): continue
        re_lines=[re.sub(r'^\s{2}RE\s*:\s?','',src[i]).rstrip()]; i+=1
        while i<len(src) and re.match(r'^\s{7}\S',src[i]):
            re_lines.append(src[i].strip()); i+=1
        joined=' '.join(' '.join(re_lines).split())
        wl=wrap(joined.split())
        if len(wl)>MAXL or any(len(x)>WIDTH for x in wl): over.append((us,wl))
        out.append('  RE : '+wl[0])
        for x in wl[1:]: out.append('       '+x)
    open(path,'w').write('\n'.join(out))
    if over:
        print(f"{path}: {len(over)} still over 3x{WIDTH} (need manual shortening):")
        for us,wl in over: print(f"  US#{us}: {wl}")
    else:
        print(f"{path}: all RE now fit <=3x{WIDTH}")
if __name__=='__main__': main()
