"""Battle pictures with Japanese lettering, redrawn in English at build time (our own lettering:
tools/pixfont.py capitals, scaled up).

MARCH.GRP (battle map): the block read by 0x8004a08c (file 0x23c7000, buffer 0x80167780; file offset =
0x23c7004 + buffer offset) holds 8bpp pieces uploaded by 0x8004a248-0x8004a2e4 / 0x8004a36c:
  0x2404544  176 x 32  任務達成！  (VRAM 512,384) -> SUCCESS!
  0x2405b44  176 x 32  任務失敗…  (VRAM 512,416) -> FAILED...
  0x2407144   88 x 32  ターン      (VRAM 320,464; the turn number is a separate digit sprite) -> TURN
  Drawn with CLUT (0,483) (0x800580f0 / 0x8001c554), but the game blends when drawing, so no VRAM row
  gives the screen colours. Quantised with the unit sprite palette MARCH.GRP 0x18f6404 (VRAM 0,487),
  limited to the indices each piece already uses: all three seen on screen and right (history 14).
BATTLE.GRP (melee battle result): every map chunk (0x31000 n, n = 0-5) starts with the same UI block
(read by 0x8005e98c: file offset 0, 0x4b60 bytes, mode-0 = 4bpp uploads 0x8005e994-0x8005eba4):
  +0x3040  96 x 40  勝利     (VRAM 576,144) -> VICTORY
  +0x37c0  96 x 40  敗北     (VRAM 608,144) -> DEFEAT
  +0x3f40 152 x 40  引き分け (VRAM 512,144) -> DRAW
  4bpp, drawn in layers of palette indices: outer rim, inner rim, top bevel, a fill ramp by row. The
  English reuses each piece's own indices by role (depth from the background), so no palette is needed.

usage: python3 tools/gfxbattle.py out.png   (preview, Japanese above English)
"""
import os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import gfx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MARCH_PAL = 0x18f6404
# offset, width, height, English, x scale, y scale, bold, italic shift (px over the cap height)
BANNERS = [(0x2404544, 176, 32, 'SUCCESS!', 3, 3, True, 0),
           (0x2405b44, 176, 32, 'FAILED...', 3, 3, True, 0),
           (0x2407144, 88, 32, 'TURN', 3, 3, False, 8)]
CHUNK, CHUNKS = 0x31000, 6
RESULTS = [(0x3040, 96, 40, 'VICTORY'), (0x37c0, 96, 40, 'DEFEAT'), (0x3f40, 152, 40, 'DRAW')]
RESULT_SCALE = (2, 3)                           # pixfont x 2 wide, x 3 tall, strokes thickened by 1 px


def big(text, sx, sy, bold=False, italic=0):
    """Ink pixels of text in pixfont scaled sx x sy (cap height 9 sy), optionally sheared; diagonal
    steps between scaled pixels are filled so curves are less blocky."""
    pts, _ = gfx.points(text, bold=bold)
    hh = 9 * sy
    out = set()
    for (x, y) in pts:
        for i in range(sx):
            for j in range(sy):
                yy = y * sy + j
                out.add((x * sx + i + ((hh - 1 - yy) * italic // hh if italic else 0), yy))
    add = set()
    for (x, y) in out:
        for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            if (x + dx, y + dy) in out and (x + dx, y) not in out and (x, y + dy) not in out:
                add.add((x + dx, y))
    return out | add


def place(m, w, h):
    tw = max(x for x, y in m) + 1
    th = max(y for x, y in m) + 1
    assert tw + 4 <= w and th + 4 <= h, (tw, th, w, h)
    x0, y0 = (w - tw) // 2, (h - th) // 2
    return {(x + x0, y + y0) for x, y in m}, y0, th


def mean(cs):
    return tuple(sum(c[i] for c in cs) // len(cs) for i in range(3))


# ---- MARCH.GRP 8bpp banners ----------------------------------------------------------------------

def banner(d, pal, off, w, h, text, sx, sy, bold, italic):
    pix = d[off:off + w * h]
    used = sorted(set(pix) - {0})
    at = lambda x, y: pix[y * w + x] if 0 <= x < w and 0 <= y < h else 0

    def classify(r):
        fill, edge = [], []
        for y in range(h):
            for x in range(w):
                v = at(x, y)
                if not v:
                    continue
                if all(at(x + dx, y + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)):
                    fill.append(pal[v])
                elif not all(at(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    edge.append(pal[v])
        return fill, edge
    fill, edge = classify(2)
    if len(fill) < 100:                         # thin strokes (ターン)
        fill, edge = classify(1)
    fill.sort(key=gfx.lum)
    dark = min(edge, key=gfx.lum)
    rim = mean(edge)
    m, y0, th = place(big(text, sx, sy, bold, italic), w, h)
    ring = gfx.edged(m)
    ring2 = gfx.edged(m | ring)
    cache = {}

    def q(c):
        if c not in cache:
            cache[c] = gfx.nearest(pal, c, used)
        return cache[c]
    img = [[0] * w for _ in range(h)]
    for (x, y) in ring2:
        img[y][x] = q(rim)
    for (x, y) in ring:
        img[y][x] = q(dark)
    for (x, y) in m:
        k = int((0.92 - 0.75 * (y - y0) / max(1, th - 1)) * (len(fill) - 1))   # bright top, darker bottom
        c = mean(fill[max(0, k - 3):k + 4])
        if (x - 1, y - 1) not in m and (x, y - 1) not in m:
            c = tuple(min(31, v + 6) for v in c)                               # top-left highlight
        img[y][x] = q(c)
    return bytes(b for r in img for b in r)


def patch_march(data):
    d = bytearray(data)
    pal = gfx.palette(data, MARCH_PAL)
    for off, w, h, text, sx, sy, bold, italic in BANNERS:
        d[off:off + w * h] = banner(data, pal, off, w, h, text, sx, sy, bold, italic)
    return bytes(d)


# ---- BATTLE.GRP 4bpp melee results ---------------------------------------------------------------

def get4(d, off, w, h):
    return [[(d[off + (y * w + x) // 2] >> (4 * (x & 1))) & 15 for x in range(w)] for y in range(h)]


def put4(img):
    return bytes(r[x] | r[x + 1] << 4 for r in img for x in range(0, len(r), 2))


def depth(img):
    """4-connected distance of every inked pixel from the background (1 = rim)."""
    h, w = len(img), len(img[0])
    D = [[0 if img[y][x] == 0 else 99 for x in range(w)] for y in range(h)]
    changed = True
    while changed:
        changed = False
        for y in range(h):
            for x in range(w):
                if D[y][x]:
                    m = min(D[yy][xx] if 0 <= yy < h and 0 <= xx < w else 0
                            for xx, yy in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))) + 1
                    if m < D[y][x]:
                        D[y][x], changed = m, True
    return D


def result(d, off, w, h, text):
    img = get4(d, off, w, h)
    D = depth(img)

    def most(pred):
        return Counter(img[y][x] for y in range(h) for x in range(w) if pred(x, y)).most_common(1)[0][0]
    rim1 = most(lambda x, y: D[y][x] == 1)
    rim2 = most(lambda x, y: D[y][x] == 2)
    top = most(lambda x, y: D[y][x] >= 3 and y and D[y - 1][x] == 2)
    ramp = []
    for y in range(h):
        c = Counter(img[y][x] for x in range(w) if D[y][x] >= 3 and img[y][x] != top)
        if c:
            ramp.append(c.most_common(1)[0][0])
    sx, sy = RESULT_SCALE
    m = big(text, sx, sy)
    m |= {(x + 1, y) for x, y in m}
    m, y0, th = place(m, w, h)
    ring = gfx.edged(m)
    new = [[0] * w for _ in range(h)]
    for x, y in gfx.edged(m | ring):
        new[y][x] = rim1
    for x, y in ring:
        new[y][x] = rim2
    for x, y in m:
        new[y][x] = top if (x, y - 1) not in m else ramp[int((y - y0) / max(1, th - 1) * (len(ramp) - 1))]
    return put4(new)


def patch_battle(data):
    d = bytearray(data)
    for off, w, h, text in RESULTS:
        new = result(data, off, w, h, text)
        for n in range(CHUNKS):
            o = CHUNK * n + off
            assert data[o:o + len(new)] == data[off:off + len(new)], hex(o)
            d[o:o + len(new)] = new
    return bytes(d)


def preview(path):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dev'))
    import png, grpview
    mo = open(os.path.join(ROOT, 'extract', 'MARCH.GRP'), 'rb').read()
    bo = open(os.path.join(ROOT, 'extract', 'BATTLE.GRP'), 'rb').read()
    mn, bn = patch_march(mo), patch_battle(bo)
    pal = mo[MARCH_PAL:MARCH_PAL + 512]
    rows = []
    for off, w, h, *_ in BANNERS:
        for g in (mo, mn):
            for r in grpview.render(pal + g[off:off + w * h], 512, w, h, 8, pal=0, scale=2):
                rows.append(bytes(r) + bytes(3 * (352 - 2 * w)))
    grey = bytes(sum(([i * 2, i * 2, i * 2] for i in range(16)), []))
    for off, w, h, _ in RESULTS:
        for g in (bo, bn):
            for r in get4(g, off, w, h):
                line = b''.join(bytes((v * 16, v * 16, v * 16)) * 2 for v in r)
                rows += [line + bytes(3 * (352 - 2 * w))] * 2
    png.write(path, 352, len(rows), rows)


if __name__ == '__main__':
    preview(sys.argv[1] if len(sys.argv) > 1 else 'gfxbattle.png')
