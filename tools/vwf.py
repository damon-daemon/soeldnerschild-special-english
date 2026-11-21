"""Variable-width English text: our proportional font (pixfont.py) inside FONT12.BIN, a glyph
routine with a per-character advance and word wrap in the game's string printer.

The game (SLPS_013.19):
  * FONT12.BIN is loaded once at 0x80139000: u16 Shift-JIS code table (3,200 entries, sorted),
    then 18-byte 12x12 1 bpp glyphs from 0x8013a900. 0x800148f8(code) binary-searches the table
    and returns the glyph index (0xc7f when the code is missing).
  * Text is drawn into a RAM surface at 0x80148a00 (320 px, 4 bpp, 160 bytes a row, low nibble =
    left pixel); 0x800148a0(y) uploads 12 rows of it to VRAM.
  * The string printer 0x80015230 keeps the pen in pixels: x gp+0xe08, y gp+0xe0c, left margin
    gp+0xe20, right limit gp+0xe24 (a new line after a character that ends past it), line height
    byte gp+0xe31, colour word gp+0xe2c (nibble repeated), typewriter flag byte gp+0xe39.
    Full-width characters go to 0x80014c0c (x & 3 == 0) or 0x80014960 (x & 3 == 2) and move the
    pen 12 px; bytes 0x20-0x60 to the half-width routines (8 px); 0x61-0x7a are commands;
    0xa6-0xdd half-width kana (as full-width glyphs).

Our encoding (one byte a character): ' '..'`' as ASCII, 'a'..'z' = 0xa6..0xbf, '{|}~' =
0xc0..0xc3 (font index k = byte - 0x20, or byte - 0x65 from 0xa6).

Patches:
  * FONT12.BIN: only the glyphs the game's text uses are kept (the table stays sorted, padded with
    0xffff); our glyphs go to the freed slots SLOT0 + k (12 rows, then the advance in byte 12).
    The last slot (the "missing" result) is blank.
  * 0x80014960 (the x & 3 == 2 full-width routine, 684 bytes) is replaced by our code:
      FWFIX   full-width glyphs: x rounded up to a multiple of 4, then the aligned routine
      VHOOK   from the printer's ASCII branch (0x80015664): our characters; anything else goes
              on to the original half-width kana branch 0x80015780
        space: measures the next word; at the line start nothing, if the word does not fit
               (end > limit + SLACK) a new line (via the printer's own overflow check), else
               the pen moves the space's advance; commands inside the word go to MEXT (dead
               ASCII branch 0x80015670): {c:x} / ESC skipped, {p:x} / {a:hhhh} words measured
        other: drawn pixel by pixel into the surface (any x), pen += advance
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, pixfont

EXE_BASE, EXE_OFF = 0x80010000, 0x800
FONT_CODES, FONT_GLYPHS, NGLYPH, GLYPH_B = 0x80139000, 0x8013a900, 3200, 18
SURF, STRIDE = 0x80148a00, 160
GP = 0x800e55f8
PEN_X, PEN_Y, LEFT, LIMIT, COLOUR, LINE_H, TYPEW = 0xe08, 0xe0c, 0xe20, 0xe24, 0xe2c, 0xe31, 0xe39
CAVE, CAVE_END = 0x80014960, 0x80014c0c
ALIGNED = 0x80014c0c                    # full-width glyph routine, x & 3 == 0
FW_CALLS = (0x8001532c, 0x80015750, 0x80015824)   # jal 0x80014960
HOOK_AT = 0x80015664                    # sltiu v0, v0, 0x41 / beqz v0, 0x80015780 (v0 = v1 - 0x20)
KANA = 0x80015780                       # original branch for the other bytes (a1 = v1 & 0xff)
NEXT = 0x800159c0                       # printer: overflow check, next byte
UPLOAD, WAIT = 0x800148a0, 0x80020cc0
MEXT, MEXT_END = 0x80015670, 0x80015780   # dead ASCII branch (FW_CALLS[1] inside it not patched)
CLR_VA = 0x80014ec0                     # opaque cells (in the dead half-width routines; exefix pool follows)
DIG_ADV = pixfont.DIGIT_W + pixfont.SPACING   # a space padding a number ("%4d") advances a digit's width
PAD_W = 8                               # a padding space clears the game's half-width cell
SLACK = 0                               # the printer also breaks after any character ending past the limit
LINE_W = 232                            # dialogue box: left margin 40, limit 272

_G = pixfont.glyphs()
CHARS = [chr(c) for c in range(0x20, 0x61)] + [chr(c) for c in range(0x61, 0x7f)]   # font index k
ENC = {ch: (0x20 + k if k < 0x41 else 0x65 + k) for k, ch in enumerate(CHARS)}
WIDTH = {ch: _G[ch][1] for ch in CHARS}


def encode(text):
    """English -> game bytes (one a character)."""
    out = b''
    for c in text:
        out += bytes([ENC[c]]) if c in ENC else c.encode('cp932')   # e.g. the caption mark §
    return out


def width(text):
    return sum(WIDTH.get(c, 12) for c in text)


def wrap(text, maxw=LINE_W):
    """Lines of text (no tags; '\n' = forced new line) as the patched printer breaks them."""
    out = []
    for para in text.split('\n'):
        line, x = '', 0
        for i, word in enumerate(para.split(' ')):
            w = width(word)
            if i and x:                          # a space between words (none at the line start)
                if x + WIDTH[' '] + w > maxw:
                    out.append(line); line, x = '', 0
                else:
                    line += ' '; x += WIDTH[' ']
            line += word; x += w
        out.append(line)
    return out


def used_codes(extract):
    """Shift-JIS codes the game's own text can show: everything below the kanji and every kanji
    in MESSAGE.DAT or in a Shift-JIS run of the other text files."""
    import msg
    used = set()
    d = open(os.path.join(extract, 'MESSAGE.DAT'), 'rb').read()
    for o, s in msg.blocks(d):
        for _, st in msg.strings(d, o, s):
            for t in msg.tokenize(st):
                if t[0] == 't':
                    used.update(int.from_bytes(c.encode('cp932'), 'big') for c in t[1] if len(c.encode('cp932')) == 2)
    for name in ('SLPS_013.19', 'JOBDATA.DAT', 'BEVENT.DAT', 'SCENARIO.DAT'):
        d = open(os.path.join(extract, name), 'rb').read(); i = 0
        while i < len(d) - 1:
            j, run = i, []
            while j < len(d) - 1 and (0x81 <= d[j] <= 0x9f or 0xe0 <= d[j] <= 0xfc) and 0x40 <= d[j + 1] <= 0xfc:
                run.append(d[j] << 8 | d[j + 1]); j += 2
            if len(run) >= 2:
                used.update(run); i = j
            else:
                i += 1
    return used


def font(clean, used):
    """FONT12.BIN with our glyphs from slot SLOT0 (returned too)."""
    codes = struct.unpack('<%dH' % NGLYPH, clean[:2 * NGLYPH])
    keep = [i for i, c in enumerate(codes) if c < 0x889f or c in used]
    slot0 = len(keep)
    assert slot0 + len(CHARS) < NGLYPH, 'no room for the English font'
    table = [codes[i] for i in keep] + [0xffff] * (NGLYPH - slot0)
    glyphs = [clean[2 * NGLYPH + GLYPH_B * i:2 * NGLYPH + GLYPH_B * (i + 1)] for i in keep]
    for ch in CHARS:
        rows, adv = _G[ch]
        glyphs.append(rows + bytes([adv]) + bytes(GLYPH_B - 13))
    glyphs += [bytes(GLYPH_B)] * (NGLYPH - len(glyphs))
    out = struct.pack('<%dH' % NGLYPH, *table) + b''.join(glyphs)
    assert len(out) == len(clean)
    return out, slot0


def code(slot0):
    """Our routines for the cave."""
    g0 = FONT_GLYPHS + GLYPH_B * slot0           # glyph k at g0 + 18 k; advance at +12
    L = [
        'FWFIX:',
        ('lw', 'v0', PEN_X, 'gp'),
        ('nop',),
        ('addiu', 'v0', 'v0', 3),
        ('srl', 'v0', 'v0', 2),
        ('sll', 'v0', 'v0', 2),
        ('j', ALIGNED),
        ('sw', 'v0', PEN_X, 'gp'),

        'VHOOK:',                                # a1 = byte, s1 -> it
        ('sltiu', 'v0', 'a1', 0xa6),
        ('bnez', 'v0', 'low'),
        ('sltiu', 'v0', 'a1', 0xde),
        ('beqz', 'v0', KANA),
        ('addiu', 't0', 'a1', -0x65),
        ('b', 'have'),
        ('nop',),
        'low:',
        ('addiu', 't0', 'a1', -0x20),
        ('sltiu', 'v0', 't0', 0x41),
        ('beqz', 'v0', KANA),
        ('nop',),
        'have:',                                 # t0 = k
        ('lui', 't5', asm.hi(g0)),
        ('addiu', 't5', 't5', asm.lo(g0)),       # t5 = glyph 0
        ('lw', 't1', PEN_X, 'gp'),
        ('bnez', 't0', 'draw'),
        ('lw', 't2', LEFT, 'gp'),
        ('jal', CLR_VA + 4 * CLRSP_AT),          # clear the space's cell (padding: run x 8 px)
        ('nop',),
        # space: nothing at the line start
        ('beq', 't1', 't2', 'out'),
        ('addiu', 't3', 's1', 1),
        ('move4',),                              # placeholder, replaced below
        'mloop:',
        ('lbu', 'a0', 0, 't3'),
        ('addiu', 't3', 't3', 1),
        ('sltiu', 'v0', 'a0', 0xa6),
        ('bnez', 'v0', 'mlow'),
        ('sltiu', 'v0', 'a0', 0xde),
        ('beqz', 'v0', 'mend'),
        ('addiu', 'a2', 'a0', -0x65),
        ('b', 'mhave'),
        ('nop',),
        'mlow:',
        ('addiu', 'a2', 'a0', -0x21),            # not the space: k - 1 < 0x40
        ('sltiu', 'v0', 'a2', 0x40),
        ('beqz', 'v0', 'mesc'),
        ('addiu', 'a2', 'a2', 1),
        'mhave:',
        ('sll', 'v0', 'a2', 4),
        ('sll', 'a3', 'a2', 1),
        ('addu', 'v0', 'v0', 'a3'),
        ('addu', 'v0', 'v0', 't5'),
        ('lbu', 'v0', 12, 'v0'),
        ('b', 'mloop'),
        ('addu', 't4', 't4', 'v0'),
        'mesc:',                                 # commands inside the word: MEXT
        ('j', MEXT),
        ('nop',),
        'mend:',
        ('lbu', 't7', 12, 't5'),                 # space advance
        ('lw', 't6', LIMIT, 'gp'),
        ('addu', 'v0', 't1', 't7'),
        ('addu', 'v0', 'v0', 't4'),
        ('addiu', 'a0', 't6', SLACK),
        ('sltu', 'v0', 'a0', 'v0'),
        ('beqz', 'v0', 'adv'),
        ('addu', 't1', 't1', 't7'),
        ('addiu', 't1', 't6', 1),                # does not fit: past the limit -> new line
        ('b', 'adv'),
        ('nop',),

        'draw:',                                 # t0 = k, t1 = x, t5 = glyph 0
        ('jal', CLR_VA + 4 * CLRCH_AT),          # clear the glyph's cell (the game's glyphs were opaque)
        ('nop',),
        ('sll', 'v0', 't0', 4),
        ('sll', 'a3', 't0', 1),
        ('addu', 'v0', 'v0', 'a3'),
        ('addu', 't5', 't5', 'v0'),              # t5 = our glyph
        ('lw', 't2', PEN_Y, 'gp'),
        ('lw', 't6', COLOUR, 'gp'),
        ('sll', 'v0', 't2', 7),
        ('sll', 'a3', 't2', 5),
        ('addu', 'v0', 'v0', 'a3'),              # y * 160
        ('lui', 't3', asm.hi(SURF)),
        ('addiu', 't3', 't3', asm.lo(SURF)),
        ('addu', 't3', 't3', 'v0'),              # t3 = row start
        ('andi', 't6', 't6', 0xff),              # colour in both nibbles
        ('addiu', 't8', 'zero', 12),             # rows left
        ('move5',),                              # placeholder: t9 = t5 (row pointer)
        'row:',
        ('lbu', 'a0', 0, 't9'),                  # bits, bit 7 = left
        ('move6',),                              # placeholder: a1 = t1 (pixel x)
        'bit:',
        ('beqz', 'a0', 'rowend'),
        ('andi', 'v0', 'a0', 0x80),
        ('beqz', 'v0', 'nextbit'),
        ('srl', 'v0', 'a1', 1),
        ('addu', 'v0', 't3', 'v0'),              # byte of the pixel
        ('lbu', 'a2', 0, 'v0'),
        ('andi', 'a3', 'a1', 1),
        ('addiu', 'a3', 'a3', 0),
        ('sll', 'a3', 'a3', 2),                  # 0 or 4
        ('addiu', 't7', 'zero', 0xf),
        ('sllv', 't7', 't7', 'a3'),              # mask
        ('nor', 'a3', 't7', 'zero'),
        ('and', 'a2', 'a2', 'a3'),
        ('and', 't7', 't7', 't6'),
        ('or', 'a2', 'a2', 't7'),
        ('sb', 'a2', 0, 'v0'),
        'nextbit:',
        ('sll', 'a0', 'a0', 1),
        ('andi', 'a0', 'a0', 0xff),
        ('b', 'bit'),
        ('addiu', 'a1', 'a1', 1),
        'rowend:',
        ('addiu', 't8', 't8', -1),
        ('addiu', 't9', 't9', 1),
        ('bnez', 't8', 'row'),
        ('addiu', 't3', 't3', STRIDE),
        ('lbu', 'v0', 12, 't5'),                 # advance
        ('nop',),
        ('addu', 't1', 't1', 'v0'),
        ('addu', 's5', 's5', 'v0'),
        ('sw', 't1', PEN_X, 'gp'),
        ('lbu', 'v0', TYPEW, 'gp'),
        ('move', 's4', 'zero'),
        ('beqz', 'v0', NEXT),
        ('nop',),
        ('jal', UPLOAD),
        ('lw', 'a0', PEN_Y, 'gp'),
        ('jal', WAIT),
        ('addiu', 'a0', 'zero', 3),
        ('j', NEXT),
        ('nop',),

        'adv:',                                  # space: t1 = new x
        ('sw', 't1', PEN_X, 'gp'),
        'out:',
        ('j', NEXT),
        ('move', 's4', 'zero'),
    ]
    fix = {('move4',): ('addu', 't4', 'zero', 'zero'), ('move5',): ('addu', 't9', 't5', 'zero'),
           ('move6',): ('addu', 'a1', 't1', 'zero'), }
    L = [fix.get(x, x) if isinstance(x, tuple) else x for x in L]
    L = [('addu', x[1], x[2], 'zero') if isinstance(x, tuple) and x[0] == 'move' else x for x in L]
    L = [x for x in L if not (isinstance(x, tuple) and x == ('addiu', 'a3', 'a3', 0))]
    return L


def mext_code(mloop, mend):
    """Commands met while measuring the next word (MEXT, in the dead ASCII branch): ESC x y
    (exe colour) and {c:x} are skipped; {p:x} (pointer word) and {a:hhhh} (person / role name)
    add the substituted word's width (the printer prints them through itself, so without this a
    name near the line end was split after its first letter: "the H / eat Burn spell").
    In: a0 = command byte, t3 -> after it, t4 = width so far, t5 = glyph 0. Uses v0, a2, a3, t6."""
    return [
        ('addiu', 'v0', 'zero', 0x1b),
        ('beq', 'a0', 'v0', 'skip2'),
        ('addiu', 'v0', 'zero', ord('c')),
        ('beq', 'a0', 'v0', 'skip1'),
        ('addiu', 'v0', 'zero', ord('p')),
        ('beq', 'a0', 'v0', 'pword'),
        ('addiu', 'v0', 'zero', ord('a')),
        ('bne', 'a0', 'v0', mend),
        ('nop',),
        ('lbu', 'v0', 0, 't3'),                  # {a:hhhh}: id (BE), as 0x80015534
        ('lbu', 'a2', 1, 't3'),
        ('sll', 'v0', 'v0', 8),
        ('or', 'v0', 'v0', 'a2'),
        ('addiu', 't3', 't3', 2),
        ('sltiu', 'a2', 'v0', 0xc4),
        ('beqz', 'a2', 'arole'),
        ('sll', 'a2', 'v0', 4),
        ('sll', 'a3', 'v0', 2),                  # person: 0x800c7548 + 21 id
        ('addu', 'a2', 'a2', 'a3'),
        ('addu', 'a2', 'a2', 'v0'),
        ('lui', 't6', asm.hi(0x800c7548)),
        ('addiu', 't6', 't6', asm.lo(0x800c7548)),
        ('b', 'meas'),
        ('addu', 't6', 't6', 'a2'),
        'arole:',
        ('sltiu', 'a2', 'v0', 0x320),
        ('beqz', 'a2', 'aother'),
        ('lui', 't6', asm.hi(0x800bf38c)),
        ('addiu', 'v0', 'v0', -0x2bc),           # role: *(0x800c040c + 4 (id - 0x2bc))
        ('lui', 't6', asm.hi(0x800c040c)),
        ('b', 'aload'),
        ('addiu', 't6', 't6', asm.lo(0x800c040c)),
        'aother:',
        ('addiu', 't6', 't6', asm.lo(0x800bf38c)),   # other: *(0x800bf38c + 4 id)
        'aload:',
        ('sll', 'v0', 'v0', 2),
        ('addu', 't6', 't6', 'v0'),
        ('lw', 't6', 0, 't6'),
        ('b', 'meas'),
        ('nop',),
        'pword:',                                # {p:x}: *(0x800c000c + 4 x), x signed
        ('lb', 'v0', 0, 't3'),
        ('addiu', 't3', 't3', 1),
        ('sll', 'v0', 'v0', 2),
        ('lui', 't6', asm.hi(0x800c000c)),
        ('addu', 't6', 't6', 'v0'),
        ('lw', 't6', asm.lo(0x800c000c), 't6'),
        ('nop',),
        'meas:',                                 # the whole word, spaces included
        ('lbu', 'a0', 0, 't6'),
        ('addiu', 't6', 't6', 1),
        ('sltiu', 'v0', 'a0', 0xa6),
        ('bnez', 'v0', 'plow'),
        ('sltiu', 'v0', 'a0', 0xde),
        ('beqz', 'v0', mloop),
        ('addiu', 'a2', 'a0', -0x65),
        ('b', 'phave'),
        ('nop',),
        'plow:',
        ('addiu', 'a2', 'a0', -0x20),
        ('sltiu', 'v0', 'a2', 0x41),
        ('beqz', 'v0', mloop),
        ('nop',),
        'phave:',
        ('sll', 'v0', 'a2', 4),
        ('sll', 'a3', 'a2', 1),
        ('addu', 'v0', 'v0', 'a3'),
        ('addu', 'v0', 'v0', 't5'),
        ('lbu', 'v0', 12, 'v0'),
        ('b', 'meas'),
        ('addu', 't4', 't4', 'v0'),
        'skip2:',
        ('addiu', 't3', 't3', 1),
        'skip1:',
        ('b', mloop),
        ('addiu', 't3', 't3', 1),
    ]


def clr_code(slot0):
    """Opaque cells, called from the cave. The game's glyph routines wrote whole 12 x 12 / 8 x 12
    cells (background 0), and lists are redrawn in place over old text (scrolling rankings, counts),
    padded with printf spaces ("%-16s"). Our glyphs only set their ink, so old text showed through.
      CLRCH  (t0 = k, t1 = x, t5 = glyph 0): clear the glyph's advance x 12 rows at the pen.
      CLRSP  (s1 -> the space, t1 = x, t5 = glyph 0): a space followed by a space or the end clears
             (run of spaces) x PAD_W px (the original padding footprint), any other space its advance.
             A space padding a number (at the line start or after a space, followed by spaces and a
             digit) instead clears and advances DIG_ADV and goes straight to the printer's NEXT
             (VHOOK skips spaces at the line start, so right-aligned prices came out left-aligned).
    Both keep t0, t1, t2, t5, s*; use v0, a0, a2, a3, t3, t4, t6-t9."""
    g0 = FONT_GLYPHS + GLYPH_B * slot0
    return [
        'CLRCH:',
        ('sll', 'v0', 't0', 4),
        ('sll', 'a3', 't0', 1),
        ('addu', 'v0', 'v0', 'a3'),
        ('addu', 'v0', 'v0', 't5'),
        ('lbu', 'a2', 12, 'v0'),                 # advance
        ('b', 'CLEAR'),
        ('addu', 'a0', 't1', 'zero'),

        'CLRSP:',                                # number padding? (line start or after a space,
        ('beq', 't1', 't2', 'np'),               # then spaces, then a digit: "%4d", "%7luG")
        ('lbu', 'v0', -1, 's1'),
        ('addiu', 'a3', 'zero', 0x20),
        ('bne', 'v0', 'a3', 'normal'),
        'np:',
        ('addiu', 'a3', 'zero', 0x20),
        ('addu', 'v0', 's1', 'zero'),
        'nps:',
        ('lbu', 'a0', 1, 'v0'),
        ('nop',),
        ('beq', 'a0', 'a3', 'nps'),
        ('addiu', 'v0', 'v0', 1),
        ('addiu', 'a0', 'a0', -0x30),
        ('sltiu', 'a0', 'a0', 10),
        ('beqz', 'a0', 'normal'),
        ('addiu', 'v0', 't1', DIG_ADV),          # padding: a digit's width, then the next byte
        ('sw', 'v0', PEN_X, 'gp'),               # (VHOOK's line-start / wrap logic skipped)
        ('addu', 's4', 'zero', 'zero'),
        ('lui', 'ra', asm.hi(NEXT)),
        ('addiu', 'ra', 'ra', asm.lo(NEXT)),
        ('addu', 'a0', 't1', 'zero'),
        ('b', 'CLEAR'),
        ('addiu', 'a2', 'zero', DIG_ADV),
        'normal:',
        ('lbu', 'v0', 1, 's1'),
        ('addiu', 'a3', 'zero', 0x20),
        ('beqz', 'v0', 'pad'),
        ('nop',),
        ('beq', 'v0', 'a3', 'pad'),
        ('nop',),
        ('lbu', 'a2', 12, 't5'),                 # space advance
        ('b', 'CLEAR'),
        ('addu', 'a0', 't1', 'zero'),
        'pad:',
        ('addu', 'v0', 's1', 'zero'),
        ('addu', 'a2', 'zero', 'zero'),
        'run:',
        ('lbu', 'a0', 0, 'v0'),
        ('addiu', 'v0', 'v0', 1),
        ('bne', 'a0', 'a3', 'runend'),
        ('nop',),
        ('b', 'run'),
        ('addiu', 'a2', 'a2', PAD_W),
        'runend:',
        ('addu', 'a0', 't1', 'zero'),

        'CLEAR:',                                # a0 = x, a2 = width: 12 rows at PEN_Y
        ('blez', 'a2', 'cdone'),
        ('lw', 'v0', PEN_Y, 'gp'),
        ('lui', 't3', asm.hi(SURF)),
        ('addiu', 't3', 't3', asm.lo(SURF)),
        ('sll', 'a3', 'v0', 7),
        ('addu', 't3', 't3', 'a3'),
        ('sll', 'a3', 'v0', 5),
        ('addu', 't3', 't3', 'a3'),              # row start
        ('addiu', 't8', 'zero', 12),
        'crow:',
        ('addu', 't9', 'a0', 'zero'),            # pixel x
        ('addu', 't4', 'a2', 'zero'),            # pixels left
        'cpix:',
        ('srl', 'v0', 't9', 1),
        ('addu', 'v0', 't3', 'v0'),
        ('lbu', 't6', 0, 'v0'),
        ('andi', 'a3', 't9', 1),
        ('beqz', 'a3', 'clo'),
        ('andi', 't7', 't6', 0xf0),              # even x = low nibble: keep the high one
        ('andi', 't7', 't6', 0x0f),              # odd x: keep the low one
        'clo:',
        ('sb', 't7', 0, 'v0'),
        ('addiu', 't4', 't4', -1),
        ('bnez', 't4', 'cpix'),
        ('addiu', 't9', 't9', 1),
        ('addiu', 't8', 't8', -1),
        ('bnez', 't8', 'crow'),
        ('addiu', 't3', 't3', STRIDE),
        'cdone:',
        ('jr', 'ra'),
        ('nop',),
    ]


def _clr_offsets():
    L = clr_code(0)
    lab = asm.labels(0, L)
    return lab['CLRCH'] // 4, lab['CLRSP'] // 4


CLRCH_AT, CLRSP_AT = _clr_offsets()
CLR_END = CLR_VA + len(asm.assemble(CLR_VA, clr_code(0)))


def patch(exe, slot0):
    """(SLPS_013.19 with the VWF, first free byte of the cave)."""
    exe = bytearray(exe)

    def put(va, b):
        o = va - EXE_BASE + EXE_OFF
        exe[o:o + len(b)] = b
    lines = code(slot0)
    labels = asm.labels(CAVE, lines)
    body = asm.assemble(CAVE, lines)
    assert CAVE + len(body) <= CAVE_END, 'cave overflow: %d bytes' % len(body)
    put(CAVE, body + bytes(CAVE_END - CAVE - len(body)))
    for va in FW_CALLS:
        if MEXT <= va < MEXT_END:
            continue
        put(va, asm.assemble(va, [('jal', labels['FWFIX'])]))
    put(HOOK_AT, asm.assemble(HOOK_AT, [('j', labels['VHOOK']), ('andi', 'a1', 'v1', 0xff)]))
    put(CLR_VA, asm.assemble(CLR_VA, clr_code(slot0)))
    mext = asm.assemble(MEXT, mext_code(labels['mloop'], labels['mend']))
    assert MEXT + len(mext) <= MEXT_END, 'MEXT overflow: %d bytes' % len(mext)
    put(MEXT, mext)
    return bytes(exe), (CAVE + len(body) + 3) & ~3
