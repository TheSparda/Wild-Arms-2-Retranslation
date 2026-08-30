"""
WA2 Japanese text decoder (work in progress).

ENCODING (cracked this session):
- KANJI + punctuation = STANDARD Shift-JIS (2-byte, lead 0x81-0x9f/0xe0-0xef). Decode directly.
- HIRAGANA = custom SINGLE-byte codes, gojuon order, base 0x28.
    code c (0x28..0x7a) -> SJIS hiragana block glyph[c-0x28], where block = 0x829f..0x82f1
    (i.e. ぁあぃい...をん, the 83-glyph small+voiced-inclusive set).  VERIFIED against dialogue.
- KATAKANA = custom SINGLE-byte codes in ~0x9c..0xff, NON-linear (gaps/reorder). PARTIAL only.
    Confirmed anchors (Rosetta from メモリーカードにセーブ etc.): see KATA_ANCHORS.
    Long-vowel ー = 0xb0. Full katakana table still TODO (needs glyph-order or more anchors).
- Control bytes < 0x20: 0x0d = line break; 0x00 terminates; others are event opcodes.

Cross-check tool: US STGEVT.BIN has IDENTICAL event bytecode, so JP msg #N == US msg #N (Rosetta).
"""
RAW, USER, HDR = 2352, 2048, 24

def readfile(path, lba, size):
    nsec = (size + USER - 1) // USER
    with open(path, "rb") as f:
        f.seek(lba * RAW); raw = f.read(nsec * RAW)
    return b"".join(raw[s*RAW+HDR:s*RAW+HDR+USER] for s in range(nsec))[:size]

# hiragana: SJIS 0x829f..0x82f1 in order, mapped from single-byte base 0x28
_HIRA = [bytes([0x82, lo]).decode("shift_jis") for lo in range(0x9f, 0xf2)]
HIRA = {0x28 + k: g for k, g in enumerate(_HIRA)}

# katakana — SOLVED (Rosetta-derived). 46 basic gojūon from ア=0xb1 (archaic ヰヱヲ dropped),
# long-vowel ー=0xb0, small/voiced kana ァィゥェォャュョッ at 0xa7..0xaf, ゛゜dakuten handled by SJIS.
_KATA_BASIC = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン"
KATA = {0xb1 + i: c for i, c in enumerate(_KATA_BASIC)}
KATA[0xb0] = "ー"
KATA.update({0xa7: "ァ", 0xa8: "ィ", 0xa9: "ゥ", 0xaa: "ェ", 0xab: "ォ",
             0xac: "ャ", 0xad: "ュ", 0xae: "ョ", 0xaf: "ッ"})

# custom kanji (game's own order in 0x88xx-0x8axx), solved incrementally
try:
    from wa2_kanji_map import KANJI as _KJ_HEX
except ImportError:
    _KJ_HEX = {}
KANJI = {bytes.fromhex(k): v for k, v in _KJ_HEX.items()}

# 0xf0xx = 2-byte glyph/DTE block (typographic + common-expression codes)
F0 = {
    0x43: "〜",   # wave/emphasis ender: いやだわ〜, キミ〜
    # emphasis exclamation glyphs — found via EN alignment: always after ッ, EN shows !/?!
    0x56: "！",   # f056 (99/101 after ッ)
    0x57: "！",   # f057 (198/198 after ッ) — styled exclamation
    0x58: "！",   # f058 (37/37 after ッ)
    # --- ellipsis run: f040 [f041 ...] f042, one cell each -------------------
    # The game draws …… as a bracketed multi-cell run (left / repeatable middle / right)
    # so the dots space evenly. Evidence (all 120 blocks, data/script/boxes.json):
    #   f040->f042 763x, f040->f041 159x, f041->f042 178x; 913/925 f040 runs close on
    #   f042 (98.7%); run lengths 2 cells (763), 3 cells (147), 4-6 cells (3).
    #   f040 is preceded by 「 452x and by clause-final は/て/が; after f042 normal
    #   kana resumes (で/そ/あ) or the box ends.
    # Substituting one … per cell yields grammatical Japanese in every sampled box, e.g.
    #   「……でも、今回の体験版では / 「………ほうほう、空を元に戻す為に
    # One cell = one … keeps the rendered WIDTH right, which the insertion budget depends on.
    0x40: "…",   # f040 (925) ellipsis run, left cell
    0x41: "…",   # f041 (223) ellipsis run, middle cell (repeatable)
    0x42: "…",   # f042 (946) ellipsis run, right cell
    # long-vowel dash in hiragana context (katakana ー is the single byte 0xb0).
    # Evidence: う<f045>ん, うぇ<f045>x5ん, ふぎゃ<f045>x15ッ！, ぐが<f045>x4んッ！
    0x45: "ー",   # f045 (216)
}

def decode(b):
    out = []; i = 0
    while i < len(b):
        c = b[i]
        if c == 0x00:
            break
        if c == 0xf0 and i + 1 < len(b):
            out.append(F0.get(b[i+1], "<f0%02x>" % b[i+1])); i += 2; continue
        if (0x81 <= c <= 0x9f or 0xe0 <= c <= 0xef) and i + 1 < len(b):
            code = b[i:i+2]
            if code in KANJI:
                out.append(KANJI[code]); i += 2; continue
            # 0x88-0x8b lead = game's custom kanji block; show as placeholder unless solved.
            # This block is NOT Shift-JIS and legitimately uses trail bytes below 0x40
            # (the global tier starts at 0x8801; the block-local tier at 0x8a38), so it must
            # be matched BEFORE the trail-byte gate below.
            if code[0] in (0x88, 0x89, 0x8a, 0x8b):
                out.append("<%s>" % code.hex()); i += 2; continue
            # Every other lead in 0x81-0x9f/0xe0-0xef is real Shift-JIS, so the trail byte
            # must be legal (0x40-0x7e or 0x80-0xfc). Without this gate the decoder swallowed
            # 2,541 illegal pairs -- 91 06, 98 10, e1 3c, 96 10 ... -- which are a single-byte
            # code followed by an event opcode (0x06 = inline-box frame, 0x10 = control lead),
            # not text. Consuming them emitted plausible-looking <xxxx>/kanji noise that let
            # binary runs pass the extractor's cjk>=2 gate and inflated the unsolved count.
            if not (0x40 <= b[i+1] <= 0x7e or 0x80 <= b[i+1] <= 0xfc):
                out.append("[%02x]" % c); i += 1; continue
            try:
                out.append(code.decode("shift_jis"))
            except Exception:
                out.append("<%02x%02x>" % (b[i], b[i+1]))
            i += 2; continue
        if c in HIRA:
            out.append(HIRA[c]); i += 1; continue
        if c in KATA:
            out.append(KATA[c]); i += 1; continue
        if c == 0x0d:
            out.append("\n"); i += 1; continue
        if 0x20 <= c < 0x7f:
            out.append(chr(c)); i += 1; continue
        out.append("[%02x]" % c); i += 1
    return "".join(out)

def messages(data, limit=None):
    """Yield (offset, decoded) for each 100C message-start."""
    i = 0; n = 0
    while True:
        i = data.find(b"\x10\x0c", i + 1)
        if i < 0: break
        yield i, decode(data[i+2:i+200])
        n += 1
        if limit and n >= limit: break

JP_BIN = "Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin"
JP_LBA, JP_SIZE, JBLK = 12601, 13271040, 110592

def load_jp():
    return readfile(JP_BIN, JP_LBA, JP_SIZE)

def block_bytes(data, block):
    return data[block * JBLK:(block + 1) * JBLK]


# --- block-aware decoding (two-tier: global <0x8a38, block-local >=0x8a38) ---
import json as _json, os as _os
_BT_PATH = _os.path.join(_os.path.dirname(__file__), '..', 'font_work', 'block_tables.json')
def _load_bt():
    try: return _json.load(open(_BT_PATH))
    except Exception: return {}
def decode_block(data, block):
    """Decode bytes with per-block local table for codes >=0x8a38 (overrides global map).
    Unknown local codes -> <b:xxxx>; unknown global -> <xxxx>."""
    bt = _load_bt().get(str(block), {})
    # Reuse the standard decoder but intercept >=0x8a38 codes at the byte level.
    # Strategy: decode normally, but we must override local codes -> do a parallel raw scan and
    # splice. Simplest correct approach: call decode() on segments split around local codes.
    out=[]; j=0; n=len(data)
    KHI={0x88,0x89,0x8a,0x8b}
    while j<n:
        c=data[j]
        if c in KHI and j+1<n:
            code=(c<<8)|data[j+1]
            if code>=0x8a38:
                h=f'{code:04x}'
                out.append(bt.get(h, '<b:'+h+'>'))
                j+=2; continue
        # accumulate a run of non-local bytes and decode as a unit (preserves kana/DTE/controls)
        k=j
        while k<n:
            cc=data[k]
            if cc in KHI and k+1<n and ((cc<<8)|data[k+1])>=0x8a38:
                break
            # advance by token width so we don't split a 2-byte unit
            if cc in KHI and k+1<n: k+=2
            elif cc in (0xf0,0x05,0x0a,0x0b,0x10,0x11,0x13,0x16,0x17,0x18) and k+1<n: k+=2
            else: k+=1
        out.append(decode(data[j:k]))
        j=k
    return ''.join(out)


if __name__ == "__main__":
    import sys
    argv = sys.argv[1:]
    if argv and argv[0] == "decode_block":
        blk = int(argv[1]); lim = int(argv[2]) if len(argv) > 2 else 0
        seg = block_bytes(load_jp(), blk)
        n = 0; i = -1
        while True:
            i = seg.find(b"\x10\x0c", i + 1)
            if i < 0: break
            print(f"@0x{i:x}: {decode_block(seg[i+2:i+220], blk)}")
            n += 1
            if lim and n >= lim: break
    else:
        data = load_jp()
        for off, txt in messages(data, limit=20):
            print(f"@0x{off:x}: {txt[:70]}")
