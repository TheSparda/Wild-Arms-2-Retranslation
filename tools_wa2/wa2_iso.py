#!/usr/bin/env python3
"""
STGEVT extract / reinsert for the WA2 MODE2/2352 PS1 disc image — the round-trip core of the inserter.

MODE2/FORM1 sector = 2352 bytes: 16 sync/header + 2048 user data + 4 EDC + 276 ECC.
User data lives at offset 24 (12 sync + 4 header + 8 subheader), length 2048.

STEP 2 of the workflow. First goal: prove extract -> reinsert-unchanged is BYTE-IDENTICAL to the
source .bin. If a file's byte length is unchanged we ONLY rewrite the 2048 data bytes per sector and
leave EDC/ECC untouched — for identical data that yields a bit-for-bit identical image (verified by
the round-trip test). EDC/ECC recompute is only needed if data within a sector changes; that path is
added once we insert real edits (and we re-verify against an emulator).

  extract:  python3 tools_wa2/wa2_iso.py extract <bin> <lba> <size> <out.bin>
  reinsert: python3 tools_wa2/wa2_iso.py reinsert <bin> <lba> <size> <data.bin> <out_bin>
  verify:   python3 tools_wa2/wa2_iso.py verify <bin_a> <bin_b>
"""
import sys, shutil, hashlib

SECTOR = 2352
DATA_OFF = 24
DATA_LEN = 2048

def extract(bin_path, lba, size, out_path):
    with open(bin_path, 'rb') as f, open(out_path, 'wb') as o:
        written = 0; sec = lba
        while written < size:
            f.seek(sec*SECTOR + DATA_OFF)
            chunk = f.read(DATA_LEN)
            if not chunk: break
            take = min(DATA_LEN, size - written)
            o.write(chunk[:take]); written += take; sec += 1
    return written

def reinsert(bin_path, lba, size, data_path, out_bin, recompute_ecc=False):
    """Write `data_path` bytes back into a COPY of bin_path at the file's sectors.
    By default only the 2048 user-data region per sector is overwritten (EDC/ECC left intact).
    recompute_ecc=True will recompute per-sector EDC/ECC (needed when data changes)."""
    data = open(data_path, 'rb').read()
    if len(data) != size:
        raise SystemExit(f"data length {len(data)} != declared size {size} — refuse (would shift sectors)")
    shutil.copyfile(bin_path, out_bin)
    with open(out_bin, 'r+b') as o:
        written = 0; sec = lba
        while written < size:
            take = min(DATA_LEN, size - written)
            block = data[written:written+take].ljust(DATA_LEN, b'\x00')
            o.seek(sec*SECTOR + DATA_OFF)
            o.write(block[:take] if take < DATA_LEN else block)
            if recompute_ecc:
                _fix_sector_ecc(o, sec)
            written += take; sec += 1
    return written

# ---- EDC/ECC (MODE2/FORM1) — only used on the recompute path ----
_EDC_TABLE = None
def _edc_table():
    global _EDC_TABLE
    if _EDC_TABLE is None:
        t = []
        for i in range(256):
            edc = i
            for _ in range(8):
                edc = (edc >> 1) ^ (0xD8018001 if edc & 1 else 0)
            t.append(edc & 0xFFFFFFFF)
        _EDC_TABLE = t
    return _EDC_TABLE

def _edc(data):
    t = _edc_table(); edc = 0
    for b in data:
        edc = (edc >> 8) ^ t[(edc ^ b) & 0xFF]
    return edc & 0xFFFFFFFF

def _fix_sector_ecc(fh, sec):
    """Recompute EDC (offset 2072, 4 bytes over bytes 16..2071) for a MODE2/FORM1 sector.
    NOTE: full ECC P/Q recompute is intentionally NOT implemented yet — most PS1 emulators
    ignore ECC. This is a placeholder for the edit path; the round-trip test does NOT use it."""
    base = sec*SECTOR
    fh.seek(base+16); region = fh.read(2072-16+4-4)  # subheader+data (bytes 16..2071)
    # region should be 2056 bytes (8 subheader + 2048 data)
    edc = _edc(region)
    fh.seek(base+2072)
    fh.write(edc.to_bytes(4, 'little'))

def sha(path):
    h = hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda: f.read(1<<20), b''): h.update(chunk)
    return h.hexdigest()

def verify(a, b):
    ha, hb = sha(a), sha(b)
    same = ha == hb
    print(f"A {ha[:16]}…  {a}")
    print(f"B {hb[:16]}…  {b}")
    print("IDENTICAL" if same else "DIFFER")
    return same

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'extract':
        b,l,s,o = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
        print(f"extracted {extract(b,l,s,o)} bytes -> {o}")
    elif cmd == 'reinsert':
        b,l,s,d,o = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6]
        ecc = '--ecc' in sys.argv
        print(f"reinserted {reinsert(b,l,s,d,o,ecc)} bytes -> {o}")
    elif cmd == 'verify':
        verify(sys.argv[2], sys.argv[3])

# ---- full-disc patch: apply an edited STGEVT data blob back into a real disc copy ----
def patch_disc(disc_in, disc_out, data_path, lba=12586, size=10813440):
    """Copy disc_in -> disc_out, write edited STGEVT data (same byte length) at its sectors,
    recomputing EDC on every sector touched. Refuses on any length change (would need repointing)."""
    return reinsert(disc_in, lba, size, data_path, disc_out, recompute_ecc=True)
