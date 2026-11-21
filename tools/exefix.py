"""Small code fixes in the exe (run by build.py after progstr / tables).

1. Memory card save title in full-width English.

The save routine (0x8002e4xx) builds the card header title (64 bytes, Shift-JIS, shown by
the console's card manager) with the game's formatter 0x80015cfc (%y = one full-width
digit) from the format at 0x80010f14:

    ゼルドナーシルト%y　%s　%-4s　%y%y%y%y年%s%y月
    args: a2 save number, a3 hero name, then on the stack: place (自室 / 戦闘 / 宿屋, from
    0x8002d34c), year digits x4, month tens ("１" 0x800e5a9c or "　" 0x800e5aa0), month ones.

The hero name and the place are now in our 1-byte encoding (not Shift-JIS), so the call
is rewired to pass only: save number, year hundreds / tens / ones (the thousands digit is
always 0), month tens ("１" or "", the NUL after "１"), month ones:

    ＳＯＥＬＤＮＥＲＳＣＨＩＬＤ１　９５１／３

progstr keeps 80010f14 / 800e5a9c / 800e5aa0 Japanese ("-"); this runs after it.

2. Nation names in the dialogue's pointer words ({p:00}-{p:03}, set by 0x800143a4(slot, ptr))
come from 0x80017ba8 = the full name ("K. of Grandcour", cut to 16 letters). The 10 setter sites
pass record + 0x11 instead = the short name (Grandcour, Rana, Saxen ...), which reads as a plain
name in sentences ("The Rana and Saxen armies clash at ...").

3. World map date plate (travel screen, scene 0x1d): 0x80022650 draws the date with 8 x 16 digit
sprites at y 16 (glyph rows 21-29), x = year 0x18 / 0x20 / 0x28, month 0x38 / 0x40, after which the
plate picture had 年 / 月. The picture now has "Y" and "M" (tools/gfx.py DATE_*), and the digits move
to make "Y951 M 1" centred on the plate.

4. VS screen men counts (battle map, 0x8007e0ec): each frame "%2d" (0x800e6310) is printed at x 0x64 /
0x104 over the last value. The game's half-width digits filled their whole 8 px cell; our VWF glyphs
only set their own pixels, so a changing count piled up into a white box ("2█ men"). The two printf
calls now go to SHOW: clear the 12 px x 12 rows of the text surface, then print "%d" with a one-digit
count moved right by a digit width (right-aligned as before). SHOW lives in FREE: the game's half-width
ASCII glyph routines 0x80014ec0 / 0x80015070, called only from the printer's old ASCII branch, which
the VWF hook bypasses (dead code; 0x800151d8 after them is live).

5. Victory pay window (0x8004ee80): "Bonus Pay" counts up 60 frames, each "%5dG" printed at x 0xa4
over the last (same pile-up). Both printf calls go to SHOWW (second entry of SHOW): clear 40 px x 12
rows, no shift.

6. Melee order shouts (0x80066b0c): "%s!" / "%s %s!" (0x800e6194 / 0x800e61a4) take the row and the
order from 5-byte tables (0x800c37d7 + 5 * row, 0x800c37f0 + 5 * order: 4 letters, "All Chg.!"). They
now index the melee menu's 7-byte tables with the same order (0x800c3809 + 7 * row = All / Front /
Middle / Rear, 0x800c382c + 7 * order = Charge / Hold / Back / Swap): "All Charge!". x 5 = sll 2 +
addu, x 7 = sll 3 + subu (same size).

7. Generic menus (0x8003129c, the only menu drawer using strlen 0x80013bd4): each item was centred
by bytes, x = box + 8 + 3 * (longest - len), which half-centred English items of different pixel
widths (battle menu: End Turn / Overview / Map / Mission / Save ...). Now x = box + 8: left-aligned.

8. Guild hire list (By Type, 0x80041788): "%-4s %3dG  %5u" (type, fee, men) at x 0x90. %-4s pads by
bytes, so with proportional type names (Inf. / Pike / Cav. / Bow) the Fee and Men columns drifted.
The printf arguments are reordered to fee, men, type ("%3dG  %5u  %s", progstr.REORDERED), so the
numbers start at a fixed x; the header 0x80011a50 reads Name / Fee / Men / Type.

9. Travel screen town window (0x80022338): the right box lists 5 places with a mark each (○ / × /
？ = not visited) from a 3-byte label table 0x800c0ed0 (城 闘 民 館 広: one kanji, "Ca" / "Ar" ...).
The labels now come from FACIL (7-byte slots in FREE: Castle / Arena / House / Manor / Square, the
town map's words), the box (window 1, 0x8002c1b8; opened at 0x800223b4, closed at 0x800225d4:
both widths, or the extra cells stay on screen) is 9 cells wide instead of 6, and the format
0x80010610 "{C6}%s{C7} %s" becomes "%s {C6}%s{C7}" with the arguments swapped, so the 12 px marks
make a column and the labels follow. progstr keeps 0x800e5764 "？" Japanese ("-": full width, 12 px like ○ ×).

10. Guild job list detail box (0x80040ecc): the job title is printed in place with "%-12s" (0x800e5d54,
used only there). Each padding space clears 8 px (vwf CLRSP), too little after a wider title ("Brigand
Hunt" -> "Pirate Hunt" left a column of the "t"). "%-15s": 3 more spaces clear 24 px more (all 129
titles over the widest, 71 px; the clear ends by x 268, inside the box).
"""
import asm, vwf

FMT_VA, FMT_ROOM = 0x80010f14, 48
JOB_FMT = 0x800e5d54          # fix 10: Guild job title "%-12s"
FMT = 'ＳＯＥＬＤＮＥＲＳＣＨＩＬＤ%y　%y%y%y／%s%y'
ONE = 0x800e5a9c            # "１\0"; ONE + 2 = ""

# 0x8002e608 .. 0x8002e678: the stack stores and the sprintf call. Locals: 0x30..0x36 year
# digits (thousands first), 0x38 month tens (0/1), 0x3a month ones, 0xb0(sp) save index, s2 = out.
CALL = [
    ('lhu', 'a3', 0x32, 'sp'),          # year hundreds
    ('lhu', 'v0', 0x34, 'sp'),
    ('lw', 't2', 0xb0, 'sp'),
    ('sw', 'v0', 0x10, 'sp'),           # tens
    ('lhu', 'v0', 0x36, 'sp'),
    ('addu', 'a0', 's2', 'zero'),
    ('sw', 'v0', 0x14, 'sp'),           # ones
    ('lhu', 'v0', 0x3a, 'sp'),
    ('lui', 'a1', asm.hi(FMT_VA)),
    ('sw', 'v0', 0x1c, 'sp'),           # month ones
    ('lhu', 'v0', 0x38, 'sp'),
    ('addiu', 'a1', 'a1', asm.lo(FMT_VA)),
    ('lui', 'v1', asm.hi(ONE)),
    ('addiu', 'a2', 't2', 1),           # save number
    ('bnez', 'v0', 'tens'),
    ('addiu', 'v1', 'v1', asm.lo(ONE)),  # "１"
    ('addiu', 'v1', 'v1', 2),           # ""
    'tens:',
    ('jal', 0x80015cfc),
    ('sw', 'v1', 0x18, 'sp'),           # month tens
] + [('nop',)] * 10
CALL_VA, CALL_END = 0x8002e608, 0x8002e67c


# delay slots of `jal 0x800143a4` whose a1 = v0 from 0x80017ba8 (move a1, v0)
NATION_SITES = (0x80033ca8, 0x80034118, 0x80034160, 0x80034178, 0x80034190, 0x800345b4,
                0x8004573c, 0x80045750, 0x80045764, 0x80045778)
SHORT = 0x11

# `addiu v0, zero, X` (sprite x) in 0x80022650: (address, Japanese x, English x)
DATE_X = ((0x800226fc, 0x18, 29), (0x80022750, 0x20, 37), (0x8002278c, 0x28, 45),
          (0x800227c8, 0x38, 67), (0x80022804, 0x40, 75))


FREE, FREE_END = vwf.CLR_END, 0x800151d8  # dead code from 0x80014ec0 (vwf's CLR first): free for new routines
VS_FMT = 0x800e6310                        # "%2d", used only here
VS_CALLS = (0x8007e120, 0x8007e138)        # jal 0x80016b20 (printf + print), a0 = VS_FMT, a1 = count
PRINTF = 0x80016b20
BONUS_CALLS = (0x8004ef00, 0x8004ef40)    # victory pay window: "%5dG" (0x800e6000) counted up in place
# SHOW (VS counts): clear 6 bytes (12 px) x 12 rows at the pen, one digit moved right.
# SHOWW (bonus pay): clear 20 bytes (40 px) x 12 rows, no shift. Then printf as before.
SHOW = [
    ('addiu', 't6', 'zero', 6),
    ('b', 'body'),
    ('addiu', 't7', 'zero', 1),
    'showw:',
    ('addiu', 't6', 'zero', 20),
    ('addiu', 't7', 'zero', 0),
    'body:',
    ('addiu', 'sp', 'sp', -24),
    ('sw', 'ra', 20, 'sp'),
    ('lw', 't0', vwf.PEN_X, 'gp'),
    ('lw', 't1', vwf.PEN_Y, 'gp'),
    ('lui', 't2', asm.hi(vwf.SURF)),
    ('addiu', 't2', 't2', asm.lo(vwf.SURF)),
    ('sll', 't3', 't1', 7),
    ('sll', 't4', 't1', 5),
    ('addu', 't2', 't2', 't3'),
    ('addu', 't2', 't2', 't4'),             # row start (y * 160)
    ('srl', 't3', 't0', 1),
    ('addu', 't2', 't2', 't3'),             # byte of x (x even)
    ('addiu', 't5', 'zero', 12),
    'clr:',
    ('addu', 't8', 't2', 'zero'),
    ('addu', 't9', 't6', 'zero'),
    'row:',
    ('sb', 'zero', 0, 't8'),
    ('addiu', 't9', 't9', -1),
    ('bnez', 't9', 'row'),
    ('addiu', 't8', 't8', 1),
    ('addiu', 't5', 't5', -1),
    ('bnez', 't5', 'clr'),
    ('addiu', 't2', 't2', vwf.STRIDE),
    ('beqz', 't7', 'go'),
    ('slti', 'v0', 'a1', 10),
    ('beqz', 'v0', 'go'),
    ('addiu', 't0', 't0', vwf.WIDTH['0']),
    ('sw', 't0', vwf.PEN_X, 'gp'),         # one digit: right-aligned
    'go:',
    ('jal', PRINTF),
    ('nop',),
    ('lw', 'ra', 20, 'sp'),
    ('nop',),
    ('jr', 'ra'),
    ('addiu', 'sp', 'sp', 24),
]
SHOWW_AT = 3 * 4                           # byte offset of 'showw:' in SHOW


SHOUT = (  # (va, old, new) instruction lists, fix 6 (and 7: MENU_X, appended below)
    (0x80066b90, [('sll', 'v0', 's0', 2), ('addu', 'v0', 'v0', 's0'), ('lui', 'a2', 0x800c),
                  ('addiu', 'a2', 'a2', 0x37f0)],
                 [('sll', 'v0', 's0', 3), ('subu', 'v0', 'v0', 's0'), ('lui', 'a2', 0x800c),
                  ('addiu', 'a2', 'a2', 0x382c)]),
    (0x80066bf4, [('sll', 'v0', 'v1', 2), ('addu', 'v0', 'v0', 'v1'), ('lui', 'a2', 0x800c),
                  ('addiu', 'a2', 'a2', 0x37d7)],
                 [('sll', 'v0', 'v1', 3), ('subu', 'v0', 'v0', 'v1'), ('lui', 'a2', 0x800c),
                  ('addiu', 'a2', 'a2', 0x3809)]),
    (0x80066c08, [('sll', 'v0', 's0', 2), ('addu', 'v0', 'v0', 's0'), ('lui', 'a3', 0x800c),
                  ('addiu', 'a3', 'a3', 0x37f0)],
                 [('sll', 'v0', 's0', 3), ('subu', 'v0', 'v0', 's0'), ('lui', 'a3', 0x800c),
                  ('addiu', 'a3', 'a3', 0x382c)]),
)
MENU_X = (  # fix 7: menu items left-aligned
    (0x800313c8, [('subu', 'v0', 's3', 'v0')], [('addu', 'v0', 'zero', 'zero')]),
    # fix 8: hire list printf args (a1 type s2, a2 fee 0x10(s1), a3 men 0xa(s0)) -> fee, men, type
    (0x8004179c, [('addu', 'a1', 's2', 'zero'), ('sll', 's0', 's0', 1), ('addu', 's0', 's0', 's5'),
                  ('lbu', 'a2', 0x10, 's1'), ('lhu', 'a3', 0xa, 's0')],
                 [('lbu', 'a1', 0x10, 's1'), ('sll', 's0', 's0', 1), ('addu', 's0', 's0', 's5'),
                  ('lhu', 'a2', 0xa, 's0'), ('addu', 'a3', 's2', 'zero')]),
)


FACIL = ('Castle', 'Arena', 'House', 'Manor', 'Square')
FACIL_FMT = 0x80010610
TOWNBOX = (  # fix 9 (FACIL address filled in by patch)
    (0x800223c0, [('addiu', 'a3', 'zero', 6)], [('addiu', 'a3', 'zero', 9)]),   # open
    (0x800225e0, [('addiu', 'a3', 'zero', 6)], [('addiu', 'a3', 'zero', 9)]),   # close
    (0x80022568, [('addiu', 'a0', 'a0', 0x610), ('addu', 'a1', 's3', 'zero'), ('jal', PRINTF),
                  ('addu', 'a2', 's0', 'zero')],
                 [('addiu', 'a0', 'a0', 0x610), ('addu', 'a2', 's3', 'zero'), ('jal', PRINTF),
                  ('addu', 'a1', 's0', 'zero')]),
    (0x80022578, [('addiu', 's3', 's3', 3)], [('addiu', 's3', 's3', 7)]),
)


def patch(exe):
    exe = bytearray(exe)

    def put(va, b):
        o = va - vwf.EXE_BASE + vwf.EXE_OFF
        exe[o:o + len(b)] = b

    fmt = FMT.encode('shift_jis') + b'\0'
    assert len(fmt) <= FMT_ROOM, len(fmt)
    put(FMT_VA, fmt.ljust(FMT_ROOM, b'\0'))
    code = asm.assemble(CALL_VA, CALL)
    assert len(code) == CALL_END - CALL_VA, len(code)
    put(CALL_VA, code)

    move = asm.assemble(0, [('addu', 'a1', 'v0', 'zero')])
    for va in NATION_SITES:
        o = va - vwf.EXE_BASE + vwf.EXE_OFF
        assert exe[o:o + 4] == move, hex(va)
        put(va, asm.assemble(va, [('addiu', 'a1', 'v0', SHORT)]))

    for va, old, new in DATE_X:
        o = va - vwf.EXE_BASE + vwf.EXE_OFF
        assert exe[o:o + 4] == asm.assemble(va, [('addiu', 'v0', 'zero', old)]), hex(va)
        put(va, asm.assemble(va, [('addiu', 'v0', 'zero', new)]))

    put(FREE, bytes(FREE_END - FREE))
    pool = FREE
    code = asm.assemble(pool, SHOW)
    put(pool, code); show = pool; pool += len(code)
    o = VS_FMT - vwf.EXE_BASE + vwf.EXE_OFF
    assert exe[o:o + 4] == b'%2d\0'
    put(VS_FMT, b'%d\0\0')
    for va in VS_CALLS:
        assert exe[va - vwf.EXE_BASE + vwf.EXE_OFF:][:4] == asm.assemble(va, [('jal', PRINTF)]), hex(va)
        put(va, asm.assemble(va, [('jal', show)]))
    for va in BONUS_CALLS:
        assert exe[va - vwf.EXE_BASE + vwf.EXE_OFF:][:4] == asm.assemble(va, [('jal', PRINTF)]), hex(va)
        put(va, asm.assemble(va, [('jal', show + SHOWW_AT)]))
    for va, old, new in SHOUT + MENU_X:
        o = va - vwf.EXE_BASE + vwf.EXE_OFF
        a = asm.assemble(va, old)
        assert exe[o:o + len(a)] == a, hex(va)
        put(va, asm.assemble(va, new))
    o = FACIL_FMT - vwf.EXE_BASE + vwf.EXE_OFF
    assert exe[o:o + 12] == b'\x1bC6%s\x1bC7 %s\0'
    put(FACIL_FMT, b'%s \x1bC6%s\x1bC7\0')
    facil = pool
    for w in FACIL:
        b = vwf.encode(w)
        assert len(b) <= 6, w
        put(pool, b.ljust(7, b'\0')); pool += 7
    pool = (pool + 3) & ~3
    fix9 = TOWNBOX + ((0x800224e8, [('lui', 'v0', 0x800c), ('addiu', 's3', 'v0', 0xed0)],
                       [('lui', 'v0', asm.hi(facil)), ('addiu', 's3', 'v0', asm.lo(facil))]),)
    for va, old, new in fix9:
        o = va - vwf.EXE_BASE + vwf.EXE_OFF
        a = asm.assemble(va, old)
        assert exe[o:o + len(a)] == a, hex(va)
        put(va, asm.assemble(va, new))
    o = JOB_FMT - vwf.EXE_BASE + vwf.EXE_OFF
    assert exe[o:o + 6] == b'%-12s\0'
    put(JOB_FMT, b'%-15s\0')
    assert pool <= FREE_END
    patch.free = (pool, FREE_END)
    return bytes(exe)
