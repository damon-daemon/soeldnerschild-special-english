"""VRAM of a DuckStation save state (to find where a picture on screen comes from).

The state = header (u32s at 0xa8: media path len / offset, subimage, then screenshot and data fields),
a zstd screenshot frame, then the zstd data frame (the second '28 b5 2f fd'). In the data, the VRAM
(1024 x 512 x 16 bit) ends right before the 'GPU' marker that follows 'GPU-VRAM'.

usage: python3 tools/emu/vram.py STATE.sav OUT          -> OUT.vram (raw 1 MB) + OUT.png (15-bit view)
       then: python3 tools/dev/grpview.py OUT.vram 0x... (offset = 2 * (y * 1024 + x)) 2048 ... to view
       a part as 4 / 8 bpp (width in pixels = 1024 * 16 / bpp for whole rows). Needs the zstd command.
"""
import os, subprocess, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dev'))
import png

MAGIC = bytes.fromhex('28b52ffd')


def vram(path):
    d = open(path, 'rb').read()
    first = d.find(MAGIC)
    second = d.find(MAGIC, first + 4)
    raw = subprocess.run(['zstd', '-d', '-c'], input=d[second:], stdout=subprocess.PIPE, check=True).stdout
    o = raw.find(b'GPU-VRAM')
    o = raw.find(b'GPU', o + 4) - 0x100000
    return raw[o:o + 0x100000]


if __name__ == '__main__':
    v = vram(sys.argv[1])
    open(sys.argv[2] + '.vram', 'wb').write(v)
    rows = []
    for y in range(512):
        r = bytearray()
        for x in range(1024):
            c = v[2 * (y * 1024 + x)] | v[2 * (y * 1024 + x) + 1] << 8
            r += bytes(((c & 31) << 3, (c >> 5 & 31) << 3, (c >> 10 & 31) << 3))
        rows.append(r)
    png.write(sys.argv[2] + '.png', 1024, 512, rows)
