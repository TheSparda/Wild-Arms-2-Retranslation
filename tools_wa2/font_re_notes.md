# WA2 Font Reverse-Engineering Notes (bulk kanji decoding)

Status: **BLOCKED** on locating a directly-renderable 1bpp kanji glyph bank.
The starting premise (SY0.BIN sections 0–4 are the kanji font) is **disproven** —
sections 1–4 are compressed 16-bit portrait/graphic images, not glyph bitmaps.

## What was verified (hard evidence)

### 1. LZSS decompressor is CORRECT
- Routine confirmed in WILDARM2.EXE at RAM 0x8009a010–0x8009a180 (capstone MIPS32-LE).
  Ring init 0xFEE, flag byte `| 0xff00`, literal bit=1, match: `off = b1 | ((b2&0xf0)<<4)`,
  `len = (b2&0x0f)+3`. Exactly matches `tools_wa2/wa2_lzss.py`.
- The setup at 0x8009a010 reads a **width and height** (`lh 4($s0)`, `lh 6($s0)`) and
  multiplies them — i.e. it decompresses **rectangular images**, not a glyph table.

### 2. SY0.BIN section content (decompressed, entropy analysis)
| sec | file off | dec size | entropy | zero% | verdict |
|-----|----------|----------|---------|-------|---------|
| 0 | 0x100 | 16780 | 2.39 | 73.7 | sparse/bitmap-ish, but NO clean glyph grid at any stride |
| 1 | 0x1800 | 33497 | 5.78 | 19.3 | image data |
| 2 | 0x7cb4 | 32954 | 6.08 | 25.8 | image data |
| 3 | 0xa8c8 | 32661 | 6.40 | 18.0 | image data |
| 4 | 0xf1f0 | 33515 | 5.40 | 37.7 | **PORTRAITS** — rendered as 256px-wide 4bpp, faces clearly visible |

- Rendering sec4 as a continuous 256px-wide 4bpp texture shows recognizable
  **character portraits/faces** (see `font_work/rez_sec4_w256_lo.png`). Definitive:
  SY0 is a graphics/portrait bank, not the kanji font.
- Autocorrelation of sec2/3/4 peaks sharply at **lag 128** (sec4 r=0.412) =
  128 bytes = one 256px row at 4bpp. Consistent with VRAM texture rows, not glyphs.
- SY0 last section @0x10edc (12580 B, uncompressed u16) — first ~2048 entries have the
  banked +18 stride structure, remainder is high-entropy. Likely a TIM/texture coord or
  sprite-frame table for the portraits, NOT a kanji glyph offset table.

### 3. CH0.BIN (1.2 MB, /SYS/CH0.BIN, LBA 717) — extracted & analyzed
- Same pointer-header + LZSS structure (base 0x801d8000, 9 sections).
- Sections 0–7 are **extremely sparse (96–98.5% zeros, entropy 0.16–1.2)** = the
  hallmark of 1bpp bitmap fonts, BUT they are tiny (725–5608 B each) and did not
  resolve into a clean glyph grid at strides 16/18/24/32 (msb/lsb, row/col-major).
- Section 8: 191969 B, entropy 3.58, 48.7% zeros. Size ≈ 7998×24 or 5999×32.
  7998 ≈ full JIS X 0208 kanji count — a strong candidate for the master kanji font,
  but rendering at 16x12 / 12x16 / 16x16 (all bit orders + col-major) produced noise.
- Section 9: 1.05 MB, entropy 5.86 — bulk graphics.

### 4. Disassembly leads (WILDARM2.EXE, .text @0x80011124, file off 0x800)
- `ori 0x8800` hits at 0x8002fbf4/ff50/030128 are **false positives**: paired with
  `lui 7` they build the constant 0x78800 (a buffer/VRAM size), not a kanji code.
- `andi 0x3ff` (mask to 0..1023 = the kanji index range) at 0x80035398 belongs to a
  packed **10-bit table lookup** (`slti 0x200` / `-0x400` sign-extend) — a tilemap/map
  decoder, not glyph rendering.
- The font/text draw routine that consumes 0x88xx codes was **not positively located**.
  It likely computes the glyph address from a code via a routine that references the
  runtime-loaded font base (a pointer stored in RAM after the font file is DMA'd in),
  so there is no static `lui/addiu` immediate to grep for.

## The blocker
No section of SY0 or CH0, at any tested stride (16/18/24/32 bytes), bit order
(msb/lsb), or orientation (row/col-major), renders as a recognizable grid of kanji.
Only the trivially-sparse anchor 一 template-matches (norm-Hamming ~0.01), which is
meaningless — a single horizontal bar matches many blank-ish glyphs. All other anchors
(大, 人, 生, 目…) land on scattered/duplicate indices with 25–99/144 Hamming, the
signature of a wrong layout. The font is therefore **not a flat fixed-stride 1bpp bank**;
it is either (a) inside a differently-encoded region (CH0 sec8 is the best remaining
lead but needs its exact packing), (b) stored as VRAM 4bpp with an interleaved/swizzled
layout, or (c) built at runtime, requiring the actual draw routine to be traced in an
emulator (e.g. no$psx/pcsx-redux with a breakpoint on the text VRAM upload) rather than
from static bytes alone.

## Recommended next step (highest value)
Trace in an emulator: set an execution breakpoint on the GPU DMA / `LoadImage` that
uploads glyph pixels to the text window's VRAM, feed a known kanji (e.g. 一 = code
0x88eb) through the message system, and capture (a) the source RAM address of the glyph
and (b) its stride/format from the live registers. That directly reveals which file,
which section, what stride, and what index math maps 0x88xx → glyph — none of which
could be pinned down from the static data because the layout is not a plain 1bpp bank.

## Files produced (all NEW, no existing tool modified)
- tools_wa2/wa2_font_extract.py — glyph renderer + template-matcher (Pillow)
- tools_wa2/wa2_layout_search.py — numpy stride/bit-order search vs anchors
- tools_wa2/wa2_anchor_solve.py — code→glyph-index consistency test (the disproof)
- tools_wa2/wa2_render_overview.py, wa2_render_4bpp.py — section overview renderers
- tools_wa2/wa2_extract_sector.py — MODE2/2352 file extractor (verified vs SY0)
- font_work/CH0_jp.bin — newly extracted candidate font file
- font_work/rez_sec4_w256_lo.png — proof SY0 sec4 = portraits
- font_work/s8_*.png, ch0_sec8_*.png — CH0 sec8 render attempts (best remaining lead)

No validated glyph→kanji mapping was obtained, so wa2_kanji_map_FONT.json was NOT
written (writing a bogus map would be worse than none).
