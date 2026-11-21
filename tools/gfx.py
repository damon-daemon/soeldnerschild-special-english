"""Graphics redrawn in English at build time (our own lettering: tools/pixfont.py).

GRP.BIN has no header: the program reads pieces at fixed offsets with 0x8001afd0(lba, offset, buffer,
size) (callers 0x80016e70-0x8001753c; map in notes/history.md Session 11). Pictures are 8bpp: a palette
of 256 15-bit colours (512 bytes), then the pixels. Pieces changed here (same size, in place):

  0x2a5000  town map building labels: 72 x 240 = 12 labels of 72 x 20 (ショップ ギルド 教会 大聖堂 訓練所
            宿屋 酒場 城 闘技場 広場 民家 屋敷) = tl/tables/places.txt 00-0a, 0c. Lettering rows 4-15.
  0xb0600   town plates (inside the world map piece 0x9d800): 72 x 320 = 20 plates of 72 x 16, town
            order = tl/tables/towns.txt. Letters rows 4-12, white with a dark edge.
  0x9d800   world map of the travel screen (320 x 240): date plate x 15-88 y 15-33, "年" and "月" after
            the digit sprites erased, "Y" and "M" drawn instead (the digits move: exefix.DATE_X).
  0x129000 + 0x13000 t   town backdrops (320 x 240), the town name painted bottom right (rows ~204-222,
            light blue italic with a dark shadow): erased (inpainted) and drawn again in English.

The labels and plates all share one base picture: the base is rebuilt by a per-pixel vote over the
pieces (only panel colours count inside the panel), then each piece gets the base + English.

usage: python3 tools/gfx.py [out.png]   (preview of all changed pictures; GRP.BIN from extract/)
"""
import os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import pixfont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_G = pixfont.glyphs()

LABELS = (0x2a5000, 72, 20, 12)              # palette offset, width, height, count
LABEL_PANEL = (5, 4, 67, 16)                 # x0, y0, x1, y1 (inside the frame)
LABEL_KEYS = ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '0a', '0c']
LABEL_INK, LABEL_EDGE = (25, 25, 23), (2, 2, 2)

PLATES = (0xb0600, 72, 16, 20)
PLATE_PANEL = (4, 3, 68, 13)
PLATE_INK, PLATE_EDGE = (31, 31, 31), (0, 0, 0)

TOWN_BG, TOWN_STEP, W, H = 0x129000, 0x13000, 320, 240
NAME_BOX = (176, 199, 318, 226)              # area searched for the Japanese name
NAME_RIGHT, NAME_TOP = 306, 207              # English: right edge, top of the capitals


def palette(d, off, n=256):
    return [((c & 31), (c >> 5 & 31), (c >> 10 & 31)) for c in
            (d[off + 2 * i] | d[off + 2 * i + 1] << 8 for i in range(n))]


def nearest(pal, rgb, allowed=None):
    best = None
    for i in (allowed if allowed is not None else range(len(pal))):
        c = pal[i]
        e = 3 * (c[0] - rgb[0]) ** 2 + 6 * (c[1] - rgb[1]) ** 2 + (c[2] - rgb[2]) ** 2
        if best is None or e < best[0]:
            best = (e, i)
    return best[1]


def lum(c):
    return c[0] + c[1] + c[2]


def points(s, italic=False, bold=False):
    """Ink pixels (x, y) of s in pixfont (y 0 = top of the capitals), and the width."""
    pts, x = set(), 0
    for ch in s:
        rows, adv = _G[ch]
        for y in range(12):
            sh = (11 - y) // 4 if italic else 0
            for i in range(8):
                if rows[y] & (0x80 >> i):
                    pts.add((x + i + sh, y))
                    if bold:
                        pts.add((x + i + sh + 1, y))
        x += adv + (1 if bold else 0)
    w = max(p[0] for p in pts) + 1 if pts else 0
    return pts, w


def edged(pts):
    """The 1 px ring around pts."""
    ring = set()
    for (x, y) in pts:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (x + dx, y + dy) not in pts:
                    ring.add((x + dx, y + dy))
    return ring


# ---- labels and plates --------------------------------------------------------------------------

def base_piece(d, off, w, h, n, panel, is_panel):
    """Text-free picture shared by n pieces of w x h at off: per-pixel vote (inside the panel only
    colours accepted by is_panel(index) count)."""
    x0, y0, x1, y1 = panel
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            vals = [d[off + k * w * h + y * w + x] for k in range(n)]
            inside = x0 <= x < x1 and y0 <= y < y1
            c = Counter(v for v in vals if is_panel(v)) if inside else Counter(vals)
            out[y * w + x] = c.most_common(1)[0][0] if c else out[y * w + x - 1]
    return out


def plaques(d, spec, panel, texts, ink, edge, y0, panel_test):
    pal_off, w, h, n = spec
    pal = palette(d, pal_off)
    off = pal_off + 512
    base = base_piece(d, off, w, h, n, panel, lambda v: panel_test(pal[v]))
    ink_i, edge_i = nearest(pal, ink), nearest(pal, edge)
    out = bytearray()
    for s in texts:
        px = bytearray(base)
        pts, tw = points(s)
        x0 = panel[0] + (panel[2] - panel[0] - tw) // 2
        if tw + 2 > panel[2] - panel[0]:
            raise ValueError('%r: %d px, room %d' % (s, tw, panel[2] - panel[0] - 2))
        for col, ps in ((edge_i, edged(pts)), (ink_i, pts)):
            for (x, y) in ps:
                if 0 <= x0 + x < w and 0 <= y0 + y < h:
                    px[(y0 + y) * w + x0 + x] = col
        out += px
    return off, bytes(out)


def labels(d):
    t = load_tl('places')
    texts = [t[k] for k in LABEL_KEYS]
    return plaques(d, LABELS, LABEL_PANEL, texts, LABEL_INK, LABEL_EDGE, 4,
                   lambda c: lum(c) <= 40)


def plates(d):
    t = load_tl('towns')
    texts = [t['%02x' % i] for i in range(PLATES[3])]
    return plaques(d, PLATES, PLATE_PANEL, texts, PLATE_INK, PLATE_EDGE, 4,
                   lambda c: 8 <= lum(c) <= 45)


def load_tl(name):
    out = {}
    for line in open(os.path.join(ROOT, 'tl', 'tables', name + '.txt'), encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            k, _, v = line.rstrip('\n').partition('|')
            out[k] = v
    return out


# ---- world map date plate -----------------------------------------------------------------------

DATE_PIC = 0x9d800
DATE_ERASE = (44, 19, 84, 32)                # x0, y0, x1, y1: the two kanji
DATE_BAND = (19, 19, 86, 31)                 # plate interior (row medians)
DATE_LETTERS = (('Y', 22), ('M', 58))        # glyph, x of the left edge; rows 21-29 like the digits
DATE_GLYPHS = {
    'Y': ['X...X', 'X...X', '.X.X.', '.X.X.', '..X..', '..X..', '..X..', '..X..', '..X..'],
    'M': ['X.....X', 'XX...XX', 'X.X.X.X', 'X.X.X.X', 'X..X..X', 'X.....X', 'X.....X', 'X.....X', 'X.....X'],
}
DATE_INK, DATE_SHADOW = (23, 23, 21), (2, 3, 2)


def dateplate(d):
    """(offset, bytes) of the world map's pixels with "Y ... M" on the date plate."""
    pal = palette(d, DATE_PIC)
    off = DATE_PIC + 512
    idx = [list(d[off + y * W: off + (y + 1) * W]) for y in range(H)]
    px = [[pal[i] for i in row] for row in idx]
    bx0, by0, bx1, by1 = DATE_BAND
    x0, y0, x1, y1 = DATE_ERASE
    mask = set()
    for y in range(y0, y1):
        row = sorted(_l(px[y][x]) for x in range(bx0, bx1))
        med = row[len(row) // 2]
        for x in range(x0, x1):
            if abs(_l(px[y][x]) - med) > 25:
                mask |= {(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                         if bx0 <= x + dx < bx1 and by0 <= y + dy < by1}
    changed = set(mask)
    rem = set(mask)
    while rem:
        upd = {}
        for (x, y) in rem:
            nb = [px[y + dy][x + dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if (x + dx, y + dy) not in rem and bx0 <= x + dx < bx1 and by0 <= y + dy < by1]
            if nb:
                upd[(x, y)] = tuple(sum(c[i] for c in nb) // len(nb) for i in range(3))
        for (x, y), v in upd.items():
            px[y][x] = v
            rem.discard((x, y))
    for ch, lx in DATE_LETTERS:
        # italic like the digit sprites (3 px over 9 rows), dark edge on the left of each stroke
        pts = {(lx + i + (8 - j) // 3, 21 + j) for j, r in enumerate(DATE_GLYPHS[ch])
               for i, c in enumerate(r) if c == 'X'}
        for (x, y) in pts:
            if (x - 1, y) not in pts:
                px[y][x - 1] = DATE_SHADOW
                changed.add((x - 1, y))
        for (x, y) in pts:
            px[y][x] = DATE_INK
            changed.add((x, y))
    cache = {}
    for (x, y) in changed:
        c = px[y][x]
        if c not in cache:
            cache[c] = nearest(pal, c)
        idx[y][x] = cache[c]
    return off, bytes(b for row in idx for b in row)


# ---- town backdrops -----------------------------------------------------------------------------

def _l(c):
    return c[0] * 3 + c[1] * 6 + c[2]


def _bluish(c):
    return c[2] >= c[0] + 2 and c[2] >= c[1] and lum(c) >= 24


def inpaint(px, box):
    """Erase the painted name inside box: mask = pixels far from the local median or bluish, grown by
    2 px; filled from the outside in with the mean of the known neighbours. The left edge of the box
    is moved to the leftmost bluish column (the name's own colour) less 4."""
    x0, y0, x1, y1 = box
    blue = [x for x in range(x0, x1) if sum(_bluish(px[y][x]) for y in range(y0, y1)) >= 2]
    if blue:
        x0 = max(x0, min(blue) - 4)
    core = {(x, y) for y in range(y0, y1) for x in range(x0, x1) if _bluish(px[y][x])}
    near = {(x + dx, y + dy) for (x, y) in core for dx in range(-4, 5) for dy in range(-4, 5)}
    mask = set(core)
    for (x, y) in near - core:
        if not (x0 <= x < x1 and y0 <= y < y1):
            continue
        win = sorted(_l(px[yy][xx]) for yy in range(max(0, y - 5), min(H, y + 6))
                     for xx in range(max(0, x - 5), min(W, x + 6)))
        med, l = win[len(win) // 2], _l(px[y][x])
        if l - med > 50 or med - l > 70:
            mask.add((x, y))
    grown = set()
    for (x, y) in mask:
        for dx in (-1, 0, 1, 2):
            for dy in (-1, 0, 1, 2):
                if x0 <= x + dx < x1 and y0 <= y + dy < y1:
                    grown.add((x + dx, y + dy))
    rem = set(grown)
    while rem:
        upd = {}
        for (x, y) in rem:
            nb = [px[y + dy][x + dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))
                  if 0 <= x + dx < W and 0 <= y + dy < H and (x + dx, y + dy) not in rem]
            if len(nb) >= 2 or (nb and len(rem) < 50):
                upd[(x, y)] = tuple(sum(c[i] for c in nb) // len(nb) for i in range(3))
        if not upd:
            break
        for (x, y), v in upd.items():
            px[y][x] = v
            rem.discard((x, y))
    return grown


NAME_INK = [(30, 30, 31), (29, 30, 31), (27, 29, 31), (25, 27, 30), (23, 26, 29), (21, 24, 28), (19, 23, 27),
            (17, 21, 26), (16, 20, 25), (15, 19, 24), (14, 18, 23), (13, 17, 22)]
NAME_SHADOW = (2, 2, 4)


def backdrop(d, t, name):
    """(offset, bytes) of town t's pixels with the English name."""
    pal_off = TOWN_BG + TOWN_STEP * t
    pal = palette(d, pal_off)
    off = pal_off + 512
    idx = [list(d[off + y * W: off + (y + 1) * W]) for y in range(H)]
    px = [[pal[i] for i in row] for row in idx]
    changed = inpaint(px, NAME_BOX)
    pts, tw = points(name, italic=True, bold=True)
    x0 = NAME_RIGHT - tw
    for (x, y) in pts:
        for dx, dy in ((1, 1), (2, 2)):
            px[NAME_TOP + y + dy][x0 + x + dx] = NAME_SHADOW
            changed.add((x0 + x + dx, NAME_TOP + y + dy))
    for (x, y) in pts:
        px[NAME_TOP + y][x0 + x] = NAME_INK[y]
        changed.add((x0 + x, NAME_TOP + y))
    cache = {}
    for (x, y) in changed:
        c = px[y][x]
        if c not in cache:
            cache[c] = nearest(pal, c)
        idx[y][x] = cache[c]
    return off, bytes(b for row in idx for b in row)


MONTH_PIC = 0x88000                          # 240-px-wide picture (palette + pixels); rows 320-351 =
MONTH_TITLE = (MONTH_PIC + 512 + 240 * 320, 240, 32, 'MONTHLY EVENTS')   # 今月の出来事 (month-end map,
                                             # VRAM 896,224; tinted yellow by the GPU), glyphs x 33-205


def month_title(d):
    import gfxbattle
    off, w, h, text = MONTH_TITLE
    return off, gfxbattle.banner(d, palette(d, MONTH_PIC), off, w, h, text, 2, 2, False, 0)


def patch(grp):
    """GRP.BIN with the English pictures (unchanged without tl/tables)."""
    if not os.path.exists(os.path.join(ROOT, 'tl', 'tables', 'towns.txt')):
        return grp
    d = bytearray(grp)
    for off, data in (labels(grp), plates(grp), dateplate(grp), month_title(grp)):
        d[off:off + len(data)] = data
    towns = load_tl('towns')
    for t in range(PLATES[3]):
        off, data = backdrop(grp, t, towns['%02x' % t])
        d[off:off + len(data)] = data
    assert len(d) == len(grp)
    return bytes(d)


def preview(path):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dev'))
    import png, grpview
    g = patch(open(os.path.join(ROOT, 'extract', 'GRP.BIN'), 'rb').read())
    rows = []
    def add(rr, w):
        for r in rr:
            rows.append(bytes(r) + bytes(3 * (320 - w)))
    a = grpview.render(g, LABELS[0] + 512, 72, 240, 8, LABELS[0], 1)
    b = grpview.render(g, PLATES[0] + 512, 72, 320, 8, PLATES[0], 1)
    for y in range(320):
        r = bytearray(a[y] if y < 240 else bytes(3 * 72)) + bytes(3 * 8) + bytes(b[y])
        rows.append(bytes(r) + bytes(3 * (320 - 152)))
    for t in range(PLATES[3]):
        o = TOWN_BG + TOWN_STEP * t
        full = grpview.render(g, o + 512, W, H, 8, o, 1)
        for y in range(192, 232):
            rows.append(bytes(full[y]))
    png.write(path, 320, len(rows), rows)


if __name__ == '__main__':
    preview(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'gfx.png'))
