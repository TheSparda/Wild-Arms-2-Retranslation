"""
WA2 LZSS decompressor (standard Okumura LZ77).

Reverse-engineered from WILDARM2.EXE: the decompress loop is at RAM 0x8009a074.
Format: 4KB ring buffer (mask 0xFFF), init position 0xFEE, flag bit 1=literal / 0=match.
Match = 2 bytes: offset = b1 | ((b2 & 0xf0) << 4)  (12-bit),  length = (b2 & 0x0f) + 3.

Used for SY0.BIN (the font). SY0 layout: 0x00 = 6-entry RAM pointer header (base 0x801e0100);
sections at file offsets 0x100, 0x1800, 0x7cb4, 0xa8c8, 0xf1f0, 0x10edc — each LZSS-compressed
EXCEPT the last (0x10edc) which is an uncompressed u16 index/offset table.
"""

def decompress(data, out_limit=1 << 20):
    N = 0x1000
    ring = bytearray(N)
    r = 0xFEE
    out = bytearray()
    src = 0
    flags = 0
    while src < len(data) and len(out) < out_limit:
        flags >>= 1
        if not (flags & 0x100):
            if src >= len(data):
                break
            flags = data[src] | 0xFF00
            src += 1
        if flags & 1:  # literal
            b = data[src]; src += 1
            out.append(b); ring[r] = b; r = (r + 1) & (N - 1)
        else:          # back-reference
            if src + 1 >= len(data):
                break
            b1 = data[src]; b2 = data[src + 1]; src += 2
            offset = b1 | ((b2 & 0xF0) << 4)
            length = (b2 & 0x0F) + 3
            for k in range(length):
                b = ring[(offset + k) & (N - 1)]
                out.append(b); ring[r] = b; r = (r + 1) & (N - 1)
    return bytes(out)


# SY0.BIN section file-offsets (after the 0x100 pointer header)
SY0_SECTIONS = [0x100, 0x1800, 0x7cb4, 0xa8c8, 0xf1f0, 0x10edc, 0x14000]

def decompress_sy0(sy0_bytes):
    """Return list of decompressed sections 0..4 (section 5 @0x10edc is an uncompressed table)."""
    out = []
    for i in range(len(SY0_SECTIONS) - 1):
        seg = sy0_bytes[SY0_SECTIONS[i]:SY0_SECTIONS[i + 1]]
        out.append(decompress(seg))
    return out


if __name__ == "__main__":
    sy = open("font_work/SY0_jp.bin", "rb").read()
    for i, d in enumerate(decompress_sy0(sy)):
        print(f"section {i} @0x{SY0_SECTIONS[i]:x}: {len(d)} bytes decompressed")
