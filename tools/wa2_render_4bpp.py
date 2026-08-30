"""Render decompressed SY0 data as 4bpp glyphs (PS1 texture format) — several sizes.
1167 glyphs at 16x16x4bpp fits ~994 kanji + kana far better than 8300 at 12x12x1bpp."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from wa2_lzss import decompress
from PIL import Image

SY0 = os.path.join(os.path.dirname(__file__), "..", "font_work", "SY0_jp.bin")
OUT = os.path.join(os.path.dirname(__file__), "..", "font_work")
SECT = [0x100, 0x1800, 0x7cb4, 0xa8c8, 0xf1f0, 0x10edc, 0x14000]


def nibbles(data, lo_first=True):
    a = np.frombuffer(data, np.uint8)
    lo = a & 0x0F
    hi = a >> 4
    if lo_first:
        out = np.empty(a.size * 2, np.uint8); out[0::2] = lo; out[1::2] = hi
    else:
        out = np.empty(a.size * 2, np.uint8); out[0::2] = hi; out[1::2] = lo
    return out


def grid4(data, w, h, lo_first=True, cols=32, maxg=1024, scale=3, gap=1):
    nib = nibbles(data, lo_first)  # 4bpp pixels 0..15
    ppg = w * h
    ng = min(nib.size // ppg, maxg)
    rows = (ng + cols - 1) // cols
    cw, ch = w + gap, h + gap
    canvas = Image.new("L", (cols * cw, rows * ch), 20)
    px = canvas.load()
    for g in range(ng):
        gb = nib[g * ppg:(g + 1) * ppg].reshape(h, w)
        gx = (g % cols) * cw; gy = (g // cols) * ch
        for y in range(h):
            for x in range(w):
                px[gx + x, gy + y] = int(gb[y, x]) * 17
    return canvas.resize((canvas.width * scale, canvas.height * scale), Image.NEAREST)


if __name__ == "__main__":
    d = open(SY0, "rb").read()
    secs = [decompress(d[SECT[i]:SECT[i + 1]]) for i in range(5)]
    alld = b"".join(secs)
    print("total", len(alld), "16x16x4bpp glyphs:", len(alld) // 128)
    for tag, w, h, lf in [("4bpp16_lo", 16, 16, True), ("4bpp16_hi", 16, 16, False),
                          ("4bpp12_lo", 12, 12, True), ("4bpp14_lo", 14, 14, True)]:
        img = grid4(alld, w, h, lf, cols=40, maxg=40 * 16, scale=3)
        p = os.path.join(OUT, f"re_{tag}.png")
        img.save(p); print("saved", p, img.size)
    # section 0 (likely small ASCII/kana font) at various
    img = grid4(secs[0], 16, 16, True, cols=32, maxg=512, scale=3)
    img.save(os.path.join(OUT, "re_sec0_4bpp16.png"))
