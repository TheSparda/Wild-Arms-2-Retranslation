#!/usr/bin/env python3
"""
First-pass generator for a Disc-1 guide area.
Given a block, finds the scene's US# messages, and emits a first-pass FINAL file:
  JP (block-decoded, reference) / EN (original localization) / RE (localization reflowed to the
  WA2 display window <=3 lines x <=35 chars, em dashes stripped, color-code artifacts removed).
This is a FIRST PASS: RE is the localization made insert-shaped, NOT a deep literary retranslation.
Story-spine scenes get flagged for a later deep pass; this gives every area valid insert text now.

Usage: python3 tools_wa2/firstpass_area.py <block> <AREACODE> "<Area Name>" <us_lo> <us_hi> <outfile>
"""
import sys, re, textwrap, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W

UD = W.readfile('Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin', 12586, 10813440)
def umsgs(d):
    o=[]; i=-1
    while True:
        i=d.find(b'\x10\x0c', i+1)
        if i<0: break
        o.append(i)
    return o
UM = umsgs(UD); UBLK = 90112

def uen(i):
    """Original EN. The name-code sequence 0x0a + ASCII-digit → {n} (party-member name slot),
    so it survives as {0}/{1}/... instead of a bare digit that later gets stripped."""
    e = UM[i+1] if i+1 < len(UM) else len(UD)
    raw = UD[UM[i]:e].split(b'\x00')[0]
    out = []
    j = 0
    while j < len(raw):
        b = raw[j]
        if b == 0x0a and j+1 < len(raw) and 0x30 <= raw[j+1] <= 0x39:
            out.append('{' + chr(raw[j+1]) + '}'); j += 2; continue
        if 0x20 <= b < 0x7f: out.append(chr(b))
        elif b == 0x0d: out.append(' ')
        j += 1
    return ' '.join(''.join(out).split())

def ublk(i): return UM[i]//UBLK

def jp_for(us, block):
    """JP text for a US# via same-index mapping within the block."""
    seg = W.block_bytes(W.load_jp(), block)
    jm=[]; i=-1
    while True:
        i=seg.find(b'\x10\x0c', i+1)
        if i<0: break
        jm.append(i)
    # first US# in this block:
    b_start = min(k for k in range(len(UM)) if ublk(k)==block)
    k = us - b_start
    if k<0 or k>=len(jm): return ''
    s=jm[k]; e=jm[k+1] if k+1<len(jm) else s+300
    return ' '.join(W.decode_block(seg[s+2:min(e,s+300)], block).replace('\n',' / ').split())

def reflow(en):
    t = en.lstrip('@').lstrip('*').strip()
    t = re.sub(r'\s*—\s*', ', ', t)          # em dash -> comma
    t = t.replace('--', ', ')
    t = re.sub(r'\s+', ' ', t).strip()
    # drop stray 0/1 color-code artifacts, but NEVER touch {n} name codes
    t = re.sub(r'(?<![{\d])[01](?![}\d])', '', t)
    t = re.sub(r'\s+', ' ', t).strip().replace(' ,', ',')
    lines = textwrap.wrap(t, 35)
    return lines[:3]

def is_content(t):
    s = t.strip()
    if not s: return False
    if 'Demo Version' in t or 'read it?' in t: return False
    return True

def main():
    block = int(sys.argv[1]); code = sys.argv[2]; name = sys.argv[3]
    lo = int(sys.argv[4]); hi = int(sys.argv[5]); outfile = sys.argv[6]
    rows = []
    for us in range(lo, hi+1):
        if ublk(us) != block:  # stay in-block
            continue
        en = uen(us)
        if not is_content(en): continue
        rows.append((us, en, jp_for(us, block), reflow(en)))
    L = []
    L.append(f"# WA2 — {name} ({code}) — block {block}, US#{lo}-{hi} — FIRST-PASS insert-ready")
    L.append("# =========================================================================================")
    L.append(f"# FIRST PASS (auto-generated): RE = the US localization reflowed to the display window")
    L.append(f"#   (<=3 lines x <=35 chars), em dashes stripped, color-code artifacts removed. JP shown for")
    L.append(f"#   reference (block-decoded; residual codes possible). This is NOT a deep literary")
    L.append(f"#   retranslation — it gives {name} valid insert text; flag for a deep RE pass later.")
    L.append(f"# US# reconciled by construction (IDs are the real block-{block} message slots).")
    L.append("# Columns: JP (reference) / EN (original) / RE (fit, em-dash-free).")
    L.append("# =========================================================================================")
    L.append("")
    for us, en, jp, lines in rows:
        L.append(f"[US#{us}]")
        L.append(f"  JP : {jp[:150]}")
        L.append(f"  EN : {en.lstrip('@').lstrip('*').strip()}")
        L.append(f"  RE : {lines[0] if lines else ''}")
        for ln in lines[1:]:
            L.append(f"       {ln}")
        L.append("")
    L.append("# =========================================================================================")
    L.append(f"# STATUS: {len(rows)} boxes first-passed (US#{lo}-{hi}, block {block}). Em-dash-free, <=3x35.")
    L.append("# =========================================================================================")
    open(outfile, 'w').write('\n'.join(L) + '\n')
    print(f"{code} blk{block}: {len(rows)} boxes -> {outfile}")

if __name__ == '__main__':
    main()
