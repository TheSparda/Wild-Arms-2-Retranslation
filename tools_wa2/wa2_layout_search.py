"""Fast numpy layout search for WA2 font glyph geometry.

Finds the (start, stride, w, h, bit-order, orientation) that makes known anchor
kanji render recognizably by minimizing Hamming distance to reference glyphs.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from wa2_lzss import decompress
from PIL import Image, ImageDraw, ImageFont

SY0 = os.path.join(os.path.dirname(__file__), "..", "font_work", "SY0_jp.bin")
SECT = [0x100, 0x1800, 0x7cb4, 0xa8c8, 0xf1f0, 0x10edc, 0x14000]
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"

ANCHORS = {"88eb": "一", "8899": "大", "8816": "人", "890b": "生", "8907": "目"}


def load():
    d = open(SY0, "rb").read()
    secs = [decompress(d[SECT[i]:SECT[i + 1]]) for i in range(5)]
    return secs, b"".join(secs)


def bits_of(data):
    """Return uint8 array (len*8) of bits MSB-first."""
    arr = np.frombuffer(data, dtype=np.uint8)
    return np.unpackbits(arr)  # MSB-first


def ref_bitmap(ch, w, h, size):
    f = ImageFont.truetype(FONT, size)
    im = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(im)
    bbox = dr.textbbox((0, 0), ch, font=f)
    tw = bbox[2] - bbox[0]; th = bbox[3] - bbox[1]
    ox = (w - tw) // 2 - bbox[0]; oy = (h - th) // 2 - bbox[1]
    dr.text((ox, oy), ch, fill=255, font=f)
    a = np.array(im) > 96
    return a.astype(np.uint8)


def search(alld, w, h, msb=True, col_major=False, strides=None, size=None):
    size = size or h
    bits = bits_of(alld) if msb else np.unpackbits(np.frombuffer(alld, np.uint8), bitorder="little")
    glyph_bits = w * h
    stride_bytes = (glyph_bits + 7) // 8
    if strides is None:
        strides = [stride_bytes]
    refs = {c: ref_bitmap(k, w, h, size).reshape(-1) for c, k in ANCHORS.items()}
    # For col-major we need to reorder ref accordingly for comparison; instead reorder glyph.
    best_overall = None
    for stride in strides:
        sbits = stride * 8
        nb = len(bits)
        ng = (nb - 0) // sbits
        if ng < 10:
            continue
        # build matrix ng x glyph_bits (take first glyph_bits of each stride window)
        usable = ng * sbits
        m = bits[:usable].reshape(ng, sbits)[:, :glyph_bits]
        if col_major:
            # reinterpret each row as w columns of h -> transpose to row-major
            m = m.reshape(ng, w, h).transpose(0, 2, 1).reshape(ng, glyph_bits)
        for code, ref in refs.items():
            # hamming = popcount(xor)
            hd = (m != ref[None, :]).sum(axis=1)
            gi = int(hd.argmin()); val = int(hd[gi])
            key = (stride, code)
            if best_overall is None or True:
                pass
        # score for anchor 一 specifically at this stride
        ref = refs["88eb"]
        hd = (m != ref[None, :]).sum(axis=1)
        gi = int(hd.argmin()); val = int(hd[gi])
        cand = (val, stride, w, h, msb, col_major, gi)
        if best_overall is None or val < best_overall[0]:
            best_overall = cand
    return best_overall


if __name__ == "__main__":
    secs, alld = load()
    print("total glyph bytes", len(alld))
    results = []
    for (w, h) in [(12, 12), (16, 16), (11, 11), (10, 10), (12, 11), (14, 14), (13, 13)]:
        for msb in (True, False):
            for cm in (False, True):
                for size in (h, h + 1, h + 2):
                    b = search(alld, w, h, msb, cm, size=size)
                    if b:
                        results.append((b[0] / (w * h),) + b + (size,))
    results.sort()
    print("\ntop layouts for 一 (norm_hamming, raw, stride, w, h, msb, colmajor, glyphidx, size):")
    for r in results[:15]:
        print(f"  {r[0]:.3f} raw={r[1]} stride={r[2]} {r[3]}x{r[4]} msb={r[5]} cm={r[6]} gidx={r[7]} size={r[8]}")
