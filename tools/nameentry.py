"""English name entry for the hero (SLPS_013.19, new game).

The game's screen (loop 0x80021570): a 16 x 6 grid of 3-byte cells (2-byte character + NUL) at
GRID, cell = row * 16 + column; columns drawn at x 0x18 + 16 each with 4 px gaps after columns 4
and 9 and column 15 at 0x11c, rows at y 0x62 + 16 each (0x80020f10); the 'Done' button
(終了, column 15 row 6) below. State object: +8 column, +0xc row, +0x10 pos (characters).
0x8002119c(col, row, mode): mode 1 appends the cell to the name buffer BUF (strcat; refused at
16 bytes), mode 0 deletes (a zero at strlen - 2), then redraws the name at (0x20, 0x3a) in a
cleared 96 x 12 box. 0x80021448(pos) places the underline at x = pos * 12 + 0x1d (none when
pos = 8). OK on a cell appends and pos += 1; at 8 the cursor jumps to Done. Done -> confirm
'%s?' (0x800218e4), then the checks (0x800219d4): secret names (4 x 17-byte entries at SECRET:
アイン = the default name; entering it twice, then a cheat name, sets stats / magic / gold),
'no space as the first character' (0x80013930(buf, "　", 2)), and 'name used by a person'.
0x80021dd0 (the next screen) centres the name in 96 px by its character count.

English: letters are our one-byte encoding; MAX letters (the 16-byte person name field and the
96 px box hold them); pos = strlen; an empty cell appends nothing (pos = strlen after the
append); the underline and the centring use the name's pixel width (NAMEW in the pool).
"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, vwf

MAX = 10
BUF = 0x800f01a8
GRID = 0x800c0bd8
SECRET, SECRET_B = 0x800c0cf8, 17
SECRETS = ('Ein', 'Special', 'Magic', 'Gold')      # default name, then the three cheats

# rows of 16 cells; '' = empty; column 15 row 5 = the space (as in the Japanese grid)
_ROWS = [
    ('ABCDE', 'abcde', '01234', ''),
    ('FGHIJ', 'fghij', '56789', ''),
    ('KLMNO', 'klmno', ".,'-&", ''),
    ('PQRST', 'pqrst', '!?():', ''),
    ('UVWXY', 'uvwxy', '', ''),
    ('Z', 'z', '', ' '),
]


def cells():
    out = []
    for groups in _ROWS:
        row = []
        for g, n in zip(groups, (5, 5, 5, 1)):
            row += list(g) + [''] * (n - len(g))
        out.append(row)
    return out


# exe strings: (address, room in bytes incl. the NUL, bytes)
E = vwf.encode
STRINGS = [
    (0x8001045c, 20, E("Your hero's name?")),
    (0x80010470, 24, E('Call him ') + b'%s' + E('?')),
    (0x80010488, 36, E('A name cannot begin with a space.') + b'g'),
    (0x800104ac, 64, E('Someone in the game has that name.') + b'n' + E('Please choose another.') + b'g'),
    (0x800e5700, 8, E('Done')),
    (0x800e5708, 8, E('Back')),
    (0x800e5710, 8, E('Select')),
    (0x800e5728, 4, E(' ')),                       # the 'first character' test string
]


def namew(slot0):
    """NAMEW: v0 = pixel width of the name in BUF (our encoding)."""
    g0 = vwf.FONT_GLYPHS + vwf.GLYPH_B * slot0
    return [
        'NAMEW:',
        ('lui', 't0', asm.hi(BUF)),
        ('addiu', 't0', 't0', asm.lo(BUF)),
        ('lui', 't5', asm.hi(g0)),
        ('addiu', 't5', 't5', asm.lo(g0)),
        ('addu', 'v0', 'zero', 'zero'),
        'nwloop:',
        ('lbu', 'a1', 0, 't0'),
        ('addiu', 't0', 't0', 1),
        ('beqz', 'a1', 'nwend'),
        ('sltiu', 'v1', 'a1', 0xa6),
        ('bnez', 'v1', 'nwlow'),
        ('addiu', 'a1', 'a1', -0x20),
        ('addiu', 'a1', 'a1', -0x45),
        'nwlow:',
        ('sll', 'v1', 'a1', 4),
        ('sll', 't1', 'a1', 1),
        ('addu', 'v1', 'v1', 't1'),
        ('addu', 'v1', 'v1', 't5'),
        ('lbu', 'v1', 12, 'v1'),
        ('b', 'nwloop'),
        ('addu', 'v0', 'v0', 'v1'),
        'nwend:',
        ('jr', 'ra'),
        ('nop',),
    ]


def patch(exe, slot0, pool, pool_end):
    """(exe with the English name entry, next free pool byte)."""
    exe = bytearray(exe)

    def at(va):
        return va - vwf.EXE_BASE + vwf.EXE_OFF

    def put(va, b):
        exe[at(va):at(va) + len(b)] = b

    def code(va, lines):
        put(va, asm.assemble(va, lines))

    # NAMEW in the pool
    L = namew(slot0)
    body = asm.assemble(pool, L)
    assert pool + len(body) <= pool_end, 'pool full (name entry)'
    put(pool, body)
    nw = pool
    pool = (pool + len(body) + 3) & ~3

    # grid
    for r, row in enumerate(cells()):
        for c, ch in enumerate(row):
            put(GRID + 3 * (r * 16 + c), E(ch).ljust(3, b'\0'))
    # secret names
    for i, s in enumerate(SECRETS):
        b = E(s)
        assert len(b) < SECRET_B
        put(SECRET + SECRET_B * i, b.ljust(SECRET_B, b'\0'))
    for va, room, b in STRINGS:
        assert len(b) < room, (hex(va), b)
        put(va, b.ljust(room, b'\0'))

    code(0x800211e0, [('sb', 'zero', -1, 'v0')])                  # delete: the last byte
    code(0x800211f0, [('addiu', 'v0', 'zero', MAX)])              # append refused at MAX bytes
    code(0x800215f4, [('addiu', 'fp', 'zero', MAX)])              # loop: full at MAX
    code(0x80021600, [('addu', 'v0', 'v0', 'zero')])              # pos = strlen (not / 2)
    code(0x800216f0, [('lui', 'a0', asm.hi(BUF)),                 # after an append: pos = strlen
                      ('jal', 0x80013a7c),
                      ('addiu', 'a0', 'a0', asm.lo(BUF))])
    code(0x8002144c, [('addiu', 'v0', 'zero', MAX)])              # no underline when full
    code(0x80021460, [('jal', nw), ('nop',),                      # underline x = 0x1d + width
                      ('addiu', 'a2', 'v0', 0x1d), ('nop',)])
    code(0x80021b44, [('addiu', 'a2', 'zero', 1)])                # first-character test: 1 byte
    code(0x80021dd8, [('jal', nw), ('nop',),                      # next screen: centre by width
                      ('addu', 'v1', 'v0', 'zero'), ('nop',), ('nop',), ('nop',)])
    return bytes(exe), pool


if __name__ == '__main__':
    for row in cells():
        print(' '.join(c if c.strip() else ('_' if c else '.') for c in row))
