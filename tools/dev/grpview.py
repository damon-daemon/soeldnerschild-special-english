"""Render a byte range of a file as a picture (reverse engineering of the graphics).

usage: python3 tools/dev/grpview.py FILE OFFSET WIDTH HEIGHT BPP out.png [--pal OFF] [--scale N]
  BPP 4 / 8 (indexed: palette of 16 / 256 15-bit colours at --pal, else grey) or 16 (direct colour).
  OFFSET / --pal accept hex. With --pal p (no value given = OFFSET, pixels after the palette).
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import png


def rgb(c):
    return ((c & 31) << 3, (c >> 5 & 31) << 3, (c >> 10 & 31) << 3)


def render(d, off, w, h, bpp, pal=None, scale=1):
    n = {4: 16, 8: 256}.get(bpp, 0)
    if pal is not None and n:
        cols = [rgb(d[pal + 2 * i] | d[pal + 2 * i + 1] << 8) for i in range(n)]
    else:
        cols = [(i * 255 // max(n - 1, 1),) * 3 for i in range(n)]
    rows = []
    stride = w * bpp // 8
    for y in range(h):
        line = d[off + y * stride: off + (y + 1) * stride]
        r = bytearray()
        if bpp == 4:
            px = [cols[b >> s & 15] for b in line for s in (0, 4)]
        elif bpp == 8:
            px = [cols[b] for b in line]
        else:
            px = [rgb(line[i] | line[i + 1] << 8) for i in range(0, len(line) - 1, 2)]
        px += [(255, 0, 255)] * (w - len(px))
        for p in px:
            r += bytes(p) * scale
        rows += [r] * scale
    return rows


if __name__ == '__main__':
    a = sys.argv[1:]
    scale, pal = 1, None
    if '--scale' in a:
        i = a.index('--scale'); scale = int(a[i + 1]); del a[i:i + 2]
    f, off, w, h, bpp, out = a[0], int(a[1], 0), int(a[2]), int(a[3]), int(a[4]), a[5]
    if '--pal' in a:
        i = a.index('--pal')
        if i + 1 < len(a) and not a[i + 1].startswith('-'):
            pal = int(a[i + 1], 0); del a[i:i + 2]
        else:
            pal = off; off += 32 if bpp == 4 else 512; del a[i]
    d = open(f, 'rb').read()
    rows = render(d, off, w, h, bpp, pal, scale)
    png.write(out, len(rows[0]) // 3, len(rows), rows)
