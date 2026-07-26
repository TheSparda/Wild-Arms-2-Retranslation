#!/usr/bin/env python3
"""Apply the prime directive from WA2_RE_STYLE_GUIDE.md: use the JP LIT verbatim as the RE
when the LIT reads clearly and fits <=3x35. Only keep the existing (polished) RE when the LIT
can't be used (over-budget = a 'major issue').

For each box in a FINAL file:
  - needs a REAL LIT (not empty / 'pending' / '(literal ...' / '__LIT_TODO__').
  - name-code safety: only where the CURRENT RE already contains a {n} code, replace the spelled
    canonical name in the LIT with that same {n}. This preserves Ard's literal "Ard...Ard" speech
    (that box's RE has no {6} code) and never invents codes.
  - reflow the (code-ported) LIT to <=3 lines x <=35 chars. If it fits, RE := that. Else keep RE.
  - EN-anchored boxes (no usable LIT) are left untouched.

Usage:
  python3 tools_wa2/prefer_lit_re.py --dry            # report only, change nothing
  python3 tools_wa2/prefer_lit_re.py                  # apply in place to all insert/*_FINAL.txt
  python3 tools_wa2/prefer_lit_re.py insert/x_FINAL.txt [more...]   # specific files
"""
import re, sys, glob, os

CODE_NAME = {0:'Ashley',1:'Brad',2:'Lilka',3:'Marina',4:'Kanon',5:'Liz',6:'Ard'}
WIDTH=35; MAXL=3

def real_lit(lit):
    if not lit: return False
    s=lit.strip()
    if not s or 'pending' in s or s=='__LIT_TODO__' or s.startswith('(literal'): return False
    # A LIT that is (or contains) a translator NOTE rather than the line itself: skip it.
    # e.g. "Ge-ge-ge... (Ard can only say his own name)" — the note describes, doesn't translate.
    if re.search(r'\((?:[^)]*\b(?:can only|note|lit\.|i\.e\.|untranslat|sfx|onomatopoe)\b[^)]*)\)', s, re.I):
        return False
    return True

def wrap(text):
    lines=[""]
    for w in text.split():
        cand=w if not lines[-1] else lines[-1]+" "+w
        if len(cand)<=WIDTH: lines[-1]=cand
        else: lines.append(w)
    return lines

def port_codes(lit, re_text):
    """Replace a spelled canonical name in LIT with {n} ONLY if {n} is already in the current RE."""
    out=lit
    for n,name in CODE_NAME.items():
        code='{'+str(n)+'}'
        if code in re_text:
            out=re.sub(r'\b'+re.escape(name)+r'\b', code, out)
    return out

def process(path, dry):
    src=open(path).read().split('\n')
    # VOICE-LOCK: a file may opt out of the prime directive (its RE is deliberately styled to a
    # character's voice, not the flat literal). Respect the marker and skip the file entirely.
    head='\n'.join(src[:20])
    if 'VOICE-LOCK' in head or 'prime-directive EXCEPTION' in head:
        return {'changed':0,'kept_overfit':0,'kept_no_lit':0,'ported':0,'total':0,'voicelock':True}, []
    out=[]; i=0
    stats={'changed':0,'kept_overfit':0,'kept_no_lit':0,'ported':0,'total':0}
    samples=[]
    while i<len(src):
        ln=src[i]
        m=re.match(r'^\[US#(\d+)\]',ln)
        if not m:
            out.append(ln); i+=1; continue
        us=m.group(1); out.append(ln); i+=1
        block=[]
        while i<len(src) and not re.match(r'^\[US#',src[i]):
            block.append(src[i]); i+=1
        # extract LIT + current RE from block
        lit=None; re_lines=[]; re_start=None
        j=0
        while j<len(block):
            b=block[j]
            if re.match(r'^\s{2}LIT\s*:',b): lit=re.sub(r'^\s{2}LIT\s*:\s?','',b).rstrip('\n')
            elif re.match(r'^\s{2}RE\s*:',b):
                re_start=j; re_lines=[re.sub(r'^\s{2}RE\s*:\s?','',b).rstrip('\n')]
                k=j+1
                while k<len(block) and re.match(r'^\s{7}\S',block[k]):
                    re_lines.append(block[k].strip()); k+=1
            j+=1
        stats['total']+=1
        cur_re=' '.join(' '.join(re_lines).split())
        if re_start is None or not real_lit(lit):
            stats['kept_no_lit']+=1; out.extend(block); continue
        ported=port_codes(lit.strip(), cur_re)
        if ported!=lit.strip(): stats['ported']+=1
        # No box may end on a trailing comma (style guide). A LIT that does is a lead-in that
        # continues in the next box, so end it with '...' instead of copying the dangling comma.
        ported=re.sub(r',\s*$', '...', ported)
        wl=wrap(' '.join(ported.split()))
        if len(wl)>MAXL or any(len(x)>WIDTH for x in wl):
            stats['kept_overfit']+=1; out.extend(block); continue
        if ' '.join(wl).strip()==cur_re.strip():
            stats['kept_no_lit']+=0  # identical already; count as no-op (not changed)
            out.extend(block); continue
        # rebuild block with new RE
        stats['changed']+=1
        if len(samples)<8: samples.append((us,cur_re,' / '.join(wl)))
        newblock=[]
        k=0
        while k<len(block):
            if k==re_start:
                newblock.append('  RE : '+wl[0])
                for x in wl[1:]: newblock.append('       '+x)
                # skip old RE continuation lines
                k+=1
                while k<len(block) and re.match(r'^\s{7}\S',block[k]): k+=1
                continue
            newblock.append(block[k]); k+=1
        out.extend(newblock)
    if not dry:
        open(path,'w').write('\n'.join(out))
    return stats, samples

def main():
    args=[a for a in sys.argv[1:] if not a.startswith('--')]
    dry='--dry' in sys.argv
    files=args if args else sorted(glob.glob('insert/*_FINAL.txt'))
    tot={'changed':0,'kept_overfit':0,'kept_no_lit':0,'ported':0,'total':0}
    locked=[]
    for f in files:
        st,samp=process(f,dry)
        if st.get('voicelock'):
            locked.append(os.path.basename(f)); continue
        for k in tot: tot[k]+=st[k]
        if st['changed'] or st['kept_overfit']:
            print(f"{os.path.basename(f):40} changed {st['changed']:4}  kept-overfit {st['kept_overfit']:3}  ported-codes {st['ported']:3}")
    if locked:
        print(f"VOICE-LOCK (skipped, RE kept as-is): {', '.join(locked)}")
    print(f"\n{'DRY RUN — ' if dry else ''}TOTALS: {tot['total']} boxes | RE<-LIT changed {tot['changed']} | "
          f"kept (LIT over-budget) {tot['kept_overfit']} | kept (no usable LIT / already==) {tot['kept_no_lit']} | code-ports {tot['ported']}")

if __name__=='__main__': main()
