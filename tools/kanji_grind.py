import sys, re, collections, importlib
sys.path.insert(0, 'tools')
import wa2_kanji_map, wa2_jp_decode
importlib.reload(wa2_kanji_map); importlib.reload(wa2_jp_decode)
from wa2_jp_decode import readfile, HIRA, KATA, KANJI

jd = readfile('Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin', 12601, 13271040)
def msgs(d):
    o=[];i=0
    while True:
        i=d.find(b'\x10\x0c',i+1)
        if i<0 or i+2>=len(d):break
        o.append(i)
    return o
JM=msgs(jd)
def dec(seg, extra=None):
    K=dict(KANJI)
    if extra: K.update(extra)
    out=[];i=0
    while i<len(seg):
        c=seg[i]
        if c==0:break
        if c==0xf0 and i+1<len(seg): out.append('~');i+=2;continue
        if (0x81<=c<=0x9f or 0xe0<=c<=0xef) and i+1<len(seg):
            code=seg[i:i+2]
            if code in K:out.append(K[code]);i+=2;continue
            if code[0] in (0x88,0x89,0x8a,0x8b) and code!=b'\x81\x40':out.append('<%s>'%code.hex());i+=2;continue
            try:out.append(code.decode('shift_jis'))
            except:out.append('_')
            i+=2;continue
        if c in HIRA:out.append(HIRA[c]);i+=1;continue
        if c in KATA:out.append(KATA[c]);i+=1;continue
        if 0x20<=c<0x7f:out.append(chr(c));i+=1;continue
        if c==0x0d:out.append('/');i+=1;continue
        out.append('.');i+=1
    return ''.join(out)
LINES=[dec(jd[p+2:p+2+400]).replace(chr(10),' ') for p in JM]

def freq():
    full='\n'.join(LINES)
    return collections.Counter(re.findall(r'<([0-9a-f]{4})>',full))

def contexts(code, n=5, width=11):
    cs=[l for l in LINES if '<'+code+'>' in l]
    cs.sort(key=lambda l:l.count('<'))
    out=[]
    for l in cs[:n]:
        p=l.find('<'+code+'>')
        out.append(l[max(0,p-width):p+width+7])
    return len(cs), out

if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'top'
    if mode=='top':
        f=freq(); start=int(sys.argv[2]) if len(sys.argv)>2 else 0; cnt=int(sys.argv[3]) if len(sys.argv)>3 else 15
        print(f'map={len(KANJI)}  distinct-unsolved={len(f)}  total-unsolved-occ={sum(f.values())}')
        for code,n in f.most_common()[start:start+cnt]:
            _,ex=contexts(code,4)
            print(f'{code} ({n}x): ' + ' | '.join(ex))
    elif mode=='verify':
        # verify candidate solves: args = code=char code=char ...
        extra={}
        for a in sys.argv[2:]:
            code,ch=a.split('='); extra[bytes.fromhex(code)]=ch
        LINES2=[dec(jd[p+2:p+2+400],extra).replace(chr(10),' ') for p in JM]
        for a in sys.argv[2:]:
            code,ch=a.split('=')
            hh=[l for l in LINES2 if ch in l][:4]
            print(f'--- {code}={ch} ---')
            for h in hh:
                p=h.find(ch); print('   ',h[max(0,p-16):p+18])
