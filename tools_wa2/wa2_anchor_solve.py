"""Find best glyph index for every anchor at candidate layouts, then check whether
code->index is a consistent affine mapping. That mapping is the real proof of the format.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from wa2_lzss import decompress
from PIL import Image, ImageDraw, ImageFont

SY0 = os.path.join(os.path.dirname(__file__), "..", "font_work", "SY0_jp.bin")
SECT = [0x100, 0x1800, 0x7cb4, 0xa8c8, 0xf1f0, 0x10edc, 0x14000]
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"

# All hand-solved anchors with their codes
ANCHORS = {
    "88eb": "一", "8899": "大", "8816": "人", "8970": "世", "8971": "界",
    "890b": "生", "898b": "魔", "880b": "力", "8907": "目", "8877": "気",
    "8884": "思", "8819": "見", "8814": "行", "889d": "前", "8846": "今",
    "88bc": "戦", "880c": "何", "8823": "能", "8855": "地", "890f": "間",
}


def load():
    d = open(SY0, "rb").read()
    secs = [decompress(d[SECT[i]:SECT[i + 1]]) for i in range(5)]
    return b"".join(secs)


def ref_bitmap(ch, w, h, size):
    f = ImageFont.truetype(FONT, size)
    im = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(im)
    bbox = dr.textbbox((0, 0), ch, font=f)
    ox = (w - (bbox[2] - bbox[0])) // 2 - bbox[0]
    oy = (h - (bbox[3] - bbox[1])) // 2 - bbox[1]
    dr.text((ox, oy), ch, fill=255, font=f)
    return (np.array(im) > 96).astype(np.uint8).reshape(-1)


def matrix(alld, stride, w, h, msb, col_major):
    if msb:
        bits = np.unpackbits(np.frombuffer(alld, np.uint8))
    else:
        bits = np.unpackbits(np.frombuffer(alld, np.uint8), bitorder="little")
    sbits = stride * 8
    ng = len(bits) // sbits
    m = bits[:ng * sbits].reshape(ng, sbits)[:, :w * h]
    if col_major:
        m = m.reshape(ng, w, h).transpose(0, 2, 1).reshape(ng, w * h)
    return m


def solve(alld, w, h, stride, msb, col_major, size):
    m = matrix(alld, stride, w, h, msb, col_major)
    rows = []
    for code, ch in ANCHORS.items():
        ref = ref_bitmap(ch, w, h, size)
        hd = (m != ref[None, :]).sum(axis=1)
        gi = int(hd.argmin())
        rows.append((code, ch, gi, int(hd[gi]), int(ref.sum())))
    return rows, m.shape[0]


if __name__ == "__main__":
    alld = load()
    for (w, h, stride, msb, cm, size) in [
        (16, 16, 32, True, False, 16),
        (16, 16, 32, True, False, 17),
        (12, 12, 18, False, False, 12),
        (12, 12, 18, True, False, 12),
    ]:
        rows, ng = solve(alld, w, h, stride, msb, cm, size)
        print(f"\n=== {w}x{h} stride{stride} msb={msb} cm={cm} size={size} ng={ng} ===")
        rows_sorted = sorted(rows, key=lambda r: int(r[0], 16))
        for code, ch, gi, hd, refn in rows_sorted:
            codenum = int(code, 16)
            idx = (codenum >> 8 & 0xff) * 256 + (codenum & 0xff)  # not meaningful yet
            print(f"  {code} {ch} -> glyph#{gi:5d}  hamming={hd:3d}/{w*h} refpx={refn}")
        # check code order vs glyph# order correlation
        by_code = sorted(rows, key=lambda r: int(r[0], 16))
        gis = [r[2] for r in by_code]
        mono = sum(1 for i in range(len(gis) - 1) if gis[i + 1] > gis[i])
        print(f"  monotonic-increasing pairs: {mono}/{len(gis)-1}")
