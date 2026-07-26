#!/usr/bin/env python3
"""
Fill LIT literals into a first-pass file from a US#->literal mapping module, OR
dump a file's remaining clean-JP boxes (LIT still __LIT_TODO__) as JP/EN pairs to translate.

  dump:  python3 tools_wa2/fill_lits.py dump insert/firstpass/blk12_DZ_CC.txt
  patch: python3 tools_wa2/fill_lits.py patch insert/firstpass/blk12_DZ_CC.txt /tmp/lits_blk12.py
         (the .py file defines L = {us:int -> literal:str})
"""
import re, sys, os, importlib.util

def boxes(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    cur=None; jp=''; en=''; todo=False; out=[]
    for ln in lines:
        m=re.match(r'^\[US#(\d+)\]',ln)
        if m:
            if cur is not None and todo: out.append((cur,jp,en))
            cur=int(m.group(1)); jp=''; en=''; todo=False
        mj=re.match(r'^  JP : (.*)$',ln);  me=re.match(r'^  EN : (.*)$',ln)
        if mj: jp=mj.group(1)
        if me: en=me.group(1)
        if ln.strip()=='LIT: __LIT_TODO__': todo=True
    if cur is not None and todo: out.append((cur,jp,en))
    return out

def do_dump(path):
    for us,jp,en in boxes(path):
        print(f"[US#{us}]")
        print(f"  JP: {jp}")
        print(f"  EN: {en}")
    print(f"# {len(boxes(path))} clean boxes to fill in {os.path.basename(path)}")

def do_patch(path, mod):
    spec=importlib.util.spec_from_file_location('lm',mod); m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); L=m.L
    lines=open(path,encoding='utf-8').read().split('\n'); cur=None; n=0
    for i,ln in enumerate(lines):
        mm=re.match(r'^\[US#(\d+)\]',ln)
        if mm: cur=int(mm.group(1))
        if ln.strip()=='LIT: __LIT_TODO__' and cur in L:
            lines[i]='  LIT: '+L[cur]; n+=1
    open(path,'w',encoding='utf-8').write('\n'.join(lines))
    left=sum(1 for x in lines if x.strip()=='LIT: __LIT_TODO__')
    print(f"{os.path.basename(path)}: filled {n}; {left} __LIT_TODO__ remaining")

if __name__=='__main__':
    if sys.argv[1]=='dump': do_dump(sys.argv[2])
    else: do_patch(sys.argv[2], sys.argv[3])
