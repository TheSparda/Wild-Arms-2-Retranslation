"""Extract a file from a MODE2/2352 PS1 .bin by LBA + size.
Each sector = 2352 bytes; user data (MODE2/FORM1) = 2048 bytes at offset 24.
Reusable per the PS1 disc-editing memory notes.
"""
import sys, os

SECTOR = 2352
DATA_OFF = 24
DATA_LEN = 2048


def extract(bin_path, lba, size, out_path):
    with open(bin_path, "rb") as f, open(out_path, "wb") as o:
        written = 0
        sec = lba
        while written < size:
            f.seek(sec * SECTOR + DATA_OFF)
            chunk = f.read(DATA_LEN)
            if not chunk:
                break
            take = min(DATA_LEN, size - written)
            o.write(chunk[:take])
            written += take
            sec += 1
    return written


if __name__ == "__main__":
    binp, lba, size, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    n = extract(binp, lba, size, out)
    print(f"wrote {n} bytes to {out}")
