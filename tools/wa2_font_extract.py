"""
WA2 font (SY0.BIN) glyph extraction + template-matching RE tool.

Decompresses the 5 LZSS sections, then treats the concatenated bytes as a stream
of fixed-stride 1bpp glyph bitmaps. Renders reference kanji from a system CJK font
at the same pixel size and finds best matches by Hamming distance.

Everything here is written to NEW files; it does not modify wa2_kanji_map.py.
"""
import sys, struct, os
sys.path.insert(0, os.path.dirname(__file__))
from wa2_lzss import decompress
from PIL import Image, ImageDraw, ImageFont

SY0 = os.path.join(os.path.dirname(__file__), "..", "font_work", "SY0_jp.bin")
OUT = os.path.join(os.path.dirname(__file__), "..", "font_work")
SECT = [0x100, 0x1800, 0x7cb4, 0xa8c8, 0xf1f0, 0x10edc, 0x14000]

# Known anchors: WA2 custom code -> real kanji (hand-solved, verified in map)
ANCHORS = {
    "88eb": "一", "8899": "大", "8816": "人", "8970": "世",
    "8971": "界", "890b": "生", "898b": "魔", "880b": "力",
    "8907": "目", "8877": "気",
}


def load_glyph_bytes():
    d = open(SY0, "rb").read()
    secs = [decompress(d[SECT[i]:SECT[i + 1]]) for i in range(5)]
    return secs, b"".join(secs)


def glyph_to_img(chunk, w, h, msb_first=True, col_major=False):
    """Render a 1bpp contiguous-bit blob to a WxH PIL image ('L')."""
    img = Image.new("L", (w, h), 0)
    px = img.load()
    nbits = w * h
    bitidx = 0
    for i in range(nbits):
        byte = chunk[i >> 3]
        bit = (byte >> (7 - (i & 7))) & 1 if msb_first else (byte >> (i & 7)) & 1
        if col_major:
            x = i // h; y = i % h
        else:
            x = i % w; y = i // w
        if 0 <= x < w and 0 <= y < h:
            px[x, y] = 255 if bit else 0
    return img


def render_ref(ch, w, h, fontpath, size=None):
    """Render a reference kanji into a WxH binarized image."""
    size = size or h
    f = ImageFont.truetype(fontpath, size)
    im = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(im)
    # center
    try:
        bbox = dr.textbbox((0, 0), ch, font=f)
        tw = bbox[2] - bbox[0]; th = bbox[3] - bbox[1]
        ox = (w - tw) // 2 - bbox[0]; oy = (h - th) // 2 - bbox[1]
    except Exception:
        ox = oy = 0
    dr.text((ox, oy), ch, fill=255, font=f)
    return im.point(lambda v: 255 if v > 96 else 0)


def hamming(a, b):
    pa = a.load(); pb = b.load()
    w, h = a.size
    diff = 0
    for y in range(h):
        for x in range(w):
            if (pa[x, y] > 0) != (pb[x, y] > 0):
                diff += 1
    return diff


def score_layout(alld, w, h, msb_first, col_major, start, stride, fontpath):
    """For each anchor, render its ref, slide over all glyph positions with given
    (start,stride) and find the best matching glyph. Return avg best-normalized score."""
    stride = stride or ((w * h + 7) // 8)
    ng = (len(alld) - start) // stride
    refs = {c: render_ref(k, w, h, fontpath) for c, k in ANCHORS.items()}
    results = {}
    tot = w * h
    for code, ref in refs.items():
        best = (1e9, -1)
        for g in range(ng):
            off = start + g * stride
            chunk = alld[off:off + stride]
            if len(chunk) < stride:
                break
            img = glyph_to_img(chunk, w, h, msb_first, col_major)
            hd = hamming(img, ref)
            if hd < best[0]:
                best = (hd, g)
        results[code] = (best[0] / tot, best[1])
    avg = sum(v[0] for v in results.values()) / len(results)
    return avg, results


if __name__ == "__main__":
    secs, alld = load_glyph_bytes()
    print("section sizes:", [len(s) for s in secs], "total", len(alld))
