"""Render each decompressed section as a grid of NxN glyphs, several strides/bit-orders,
to visually ground-truth the font layout. Saves PNGs to font_work/."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from wa2_lzss import decompress
from PIL import Image

SY0 = os.path.join(os.path.dirname(__file__), "..", "font_work", "SY0_jp.bin")
OUT = os.path.join(os.path.dirname(__file__), "..", "font_work")
SECT = [0x100, 0x1800, 0x7cb4, 0xa8c8, 0xf1f0, 0x10edc, 0x14000]


def grid(data, w, h, msb, cols=32, maxg=1024, scale=3, gap=1):
    if msb:
        bits = np.unpackbits(np.frombuffer(data, np.uint8))
    else:
        bits = np.unpackbits(np.frombuffer(data, np.uint8), bitorder="little")
    stride = (w * h + 7) // 8 * 8
    ng = min(len(bits) // stride, maxg)
    rows = (ng + cols - 1) // cols
    cw, ch = w + gap, h + gap
    canvas = Image.new("L", (cols * cw, rows * ch), 40)
    px = canvas.load()
    for g in range(ng):
        gb = bits[g * stride:g * stride + w * h].reshape(h, w)
        gx = (g % cols) * cw; gy = (g // cols) * ch
        for y in range(h):
            for x in range(w):
                if gb[y, x]:
                    px[gx + x, gy + y] = 255
    return canvas.resize((canvas.width * scale, canvas.height * scale), Image.NEAREST)


if __name__ == "__main__":
    d = open(SY0, "rb").read()
    secs = [decompress(d[SECT[i]:SECT[i + 1]]) for i in range(5)]
    alld = b"".join(secs)
    # Render whole concatenated stream at 12x12 both orders, and 16x16
    for tag, w, h, msb in [("all_12_msb", 12, 12, True), ("all_12_lsb", 12, 12, False),
                           ("all_16_msb", 16, 16, True), ("all_16_lsb", 16, 16, False)]:
        img = grid(alld, w, h, msb, cols=48, maxg=48 * 24, scale=2)
        p = os.path.join(OUT, f"re_{tag}.png")
        img.save(p)
        print("saved", p, img.size)
    # per-section 12x12 msb
    for i, s in enumerate(secs):
        img = grid(s, 12, 12, True, cols=40, maxg=40 * 20, scale=2)
        img.save(os.path.join(OUT, f"re_sec{i}_12msb.png"))
    print("done")
