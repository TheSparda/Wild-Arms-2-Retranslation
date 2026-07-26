import sys, struct, os
sys.path.insert(0, 'tools_wa2')
from wa2_lzss import decompress
try:
    from PIL import Image
except ImportError:
    Image = None

RAW, USER, HDR = 2352, 2048, 24
BIN = 'Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin'
OUT = 'font_work/retest'
os.makedirs(OUT, exist_ok=True)

def readfile(lba, size):
    with open(BIN, 'rb') as f:
        out = bytearray(); nsec = (size + USER - 1)//USER
        for s in range(nsec):
            f.seek((lba+s)*RAW+HDR); out += f.read(USER)
    return bytes(out[:size])

def sections(data):
    """pointer header: u32 RAM addrs; base = first & ~0xfff-ish. Return file offsets."""
    ptrs = []
    for i in range(16):
        p = struct.unpack('<I', data[i*4:i*4+4])[0]
        if p == 0: break
        ptrs.append(p)
    base = ptrs[0] & 0xffff0000  # e.g. 0x801d0000
    # section file offsets = ptr - base... but header itself occupies start.
    offs = [p - ptrs[0] + (ptrs[0] - base) for p in ptrs]
    # simpler: offset within file = ptr - (ptrs[0] - first_section_file_off)
    # Use ptr difference from a base = ptrs[0] rounded down to where header sits.
    base2 = ptrs[0] - (ptrs[0] & 0xfff if False else 0)
    return ptrs

def render_1bpp(buf, w, msb=True, colmajor=False, cell_w=None, cell_h=None, scale=2, path=''):
    if Image is None: return
    if cell_w and cell_h:
        # tiled glyph rendering: cell_w x cell_h cells, packed
        bytes_per_row = (cell_w + 7)//8
        cell_bytes = bytes_per_row * cell_h
        ncells = len(buf)//cell_bytes
        cols = 32
        rows = (ncells + cols - 1)//cols
        img = Image.new('L', (cols*cell_w, rows*cell_h), 0)
        px = img.load()
        for c in range(ncells):
            cx = (c % cols)*cell_w; cy = (c//cols)*cell_h
            for y in range(cell_h):
                for xb in range(bytes_per_row):
                    b = buf[c*cell_bytes + y*bytes_per_row + xb]
                    for bit in range(8):
                        x = xb*8 + bit
                        if x >= cell_w: break
                        on = (b >> (7-bit)) & 1 if msb else (b >> bit) & 1
                        if on: px[cx+x, cy+y] = 255
        img = img.resize((img.width*scale, img.height*scale), Image.NEAREST)
        img.save(path)
    else:
        h = (len(buf)*8)//w
        img = Image.new('L', (w, h), 0); px = img.load()
        for i, b in enumerate(buf):
            for bit in range(8):
                idx = i*8+bit; x = idx % w; y = idx//w
                if y >= h: break
                on = (b >> (7-bit)) & 1 if msb else (b >> bit) & 1
                if on: px[x, y] = 255
        img.save(path)

# ---- SY0 + CH0 sections ----
for name, lba, size in [('SY0', 1369, 81920), ('CH0', 717, 1216512)]:
    data = readfile(lba, size)
    ptrs = sections(data)
    base = ptrs[0] & 0xffff0000
    foffs = [p - base for p in ptrs]  # file offsets of each section
    print(f'\n=== {name} sections (file offsets): {[hex(o) for o in foffs]} ===')
    for si in range(len(foffs)):
        start = foffs[si]
        end = foffs[si+1] if si+1 < len(foffs) else size
        raw = data[start:end]
        try:
            dec = decompress(raw)
        except Exception as e:
            dec = raw
        z = dec.count(0)/max(1,len(dec))*100
        print(f'  sec{si}: raw={len(raw)} dec={len(dec)} zero%={z:.1f}')
        # render candidates that look bitmap-ish (sparse) at multiple cell sizes
        if len(dec) > 2000:
            for cw, ch in [(12,12),(16,16),(12,16),(16,12),(8,16),(24,24)]:
                p = f'{OUT}/{name}_sec{si}_{cw}x{ch}.png'
                render_1bpp(dec, 0, msb=True, cell_w=cw, cell_h=ch, path=p)
print('\ndone -> font_work/retest/')
