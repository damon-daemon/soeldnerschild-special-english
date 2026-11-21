"""Fixed-slot record tables of the program SLPS_013.19 (names of ranks, items, classes, towns,
companies, jobs, spells ...): English written in place, in the same slot as the Japanese.

The game reads each table through a small accessor (record = base + index * stride, e.g. 0x800175b0
ranks, 0x8001a7b0 items, 0x80018b88 companies) and the callers read the name at a fixed offset of the
record, so a name cannot grow past its field. Our encoding is one byte a character (vwf.encode), so a
field of N bytes holds N - 1 letters (full-width Japanese held (N - 1) / 2). Half-width kana fields
(classes, towns, units, specials, spells) are printed by the same VWF branch as our letters.

The tables at 0x800c66ec-0x800caceb are a copy of SCENARIO.DAT (the game loads it there at a new
game): nations, towns, companies are written to both (like names.py's persons).

tl/tables/NAME.txt: "KEY|English" lines; KEY = record index (hex) or, in misc.txt, the slot address.
'#' starts a comment; English "-" = keep the Japanese. Same Japanese in one table = same English
(translation memory) unless the key has its own line. Control tags as in progstr ({g} {n} ...).

  tables.py export                  -> script/tables.json (key, Japanese, slot size)
  tables.py show [NAME] [--todo]    Japanese, slot and English
  tables.py init                    tl/tables/ skeletons (no overwrite)
  tables.py apply NAME BATCH        put KEY|English lines into a tl file (checked)
  tables.py check | stats
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, progstr, vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'tables')
SCRIPT = os.path.join(ROOT, 'script', 'tables.json')
EXE = os.path.join(ROOT, 'extract', 'SLPS_013.19')
SCN_VA, SCN_END = 0x800c66ec, 0x800cacec          # SCENARIO.DAT image in the exe

# name, base, stride, count, field offset, field bytes (with the zero), what
TABLES = [
    ('ranks', 0x800c028c, 9, 25, 0, 9, 'ranks / titles (accessor 0x800175b0)'),
    ('troops', 0x800c0370, 5, 7, 0, 5, 'troop types (0x800175c8)'),
    ('places', 0x800c0394, 9, 13, 0, 9, 'town map places (0x800175e0)'),
    ('item_kinds', 0x800c0468, 7, 18, 0, 7, 'item kinds (0x80017614)'),
    ('bonuses', 0x800c04e8, 7, 6, 0, 7, 'item stat bonuses (0x80017654)'),
    ('weapon_kinds', 0x800c0514, 7, 7, 0, 7, 'weapon skills (0x800176b8)'),
    ('grades', 0x800c0548, 3, 5, 0, 3, 'skill grades E-A (0x800176e4)'),
    ('orders', 0x800c5778, 11, 6, 0, 11, "Ein's knightly orders (lui 0x80096a10)"),
    ('classes', 0x800c5d14, 11, 21, 0, 11, 'commander classes, half-width (0x8001aa70)'),
    ('specials', 0x800c60c8, 16, 21, 2, 12, 'special moves, half-width (0x8001a65c)'),
    ('effects', 0x800c6620, 12, 17, 0, 12, 'spell effects (0x8001a6dc)'),
    ('nations', 0x800c68b8, 36, 7, 0, 17, 'nation full names (0x80017ba8; SCENARIO)'),
    ('nations_short', 0x800c68b8, 36, 7, 0x11, 13, 'nation short names (SCENARIO)'),
    ('towns', 0x800c6b78, 32, 20, 0, 9, 'towns, half-width (0x80018904; SCENARIO)'),
    ('companies', 0x800c7118, 17, 63, 0, 17, 'companies, orders, factions (0x80018b8c; SCENARIO)'),
    ('items', 0x800cacec, 48, 102, 2, 17, 'item names (0x8001a7b0)'),
    ('item_desc', 0x800cacec, 48, 102, 0x16, 26, 'item descriptions'),
    ('units', 0x800cc00c, 17, 21, 0, 10, 'unit types, half-width (0x800194a4)'),
    ('jobs', 0x800cc174, 26, 129, 4, 13, 'job titles (0x8001aa8c)'),
    ('spells', 0x800cce90, 18, 65, 4, 12, 'spell names, half-width (0x8001a684)'),
]
# name-only tables rewritten as a byte offset table + packed strings in the same bytes, the accessor
# changed to base + base[i]: name -> (accessor address, accessor instructions, area bytes, longest name)
PACKED = {'classes': (0x8001aa6c, 8, 21 * 11, 20)}   # 21 slots only: 0x800c5dfc is the mission goal buffer

# loose labels referenced by lui pairs: (address, count, stride)
MISC = [
    (0x800c003c, 1, 17),     # empty row dashes
    (0x800c0d4c, 6, 5),      # Infantry Pike Cavalry Bow / Fast Normal
    (0x800c0ed0, 5, 3),      # town map legend: castle arena house mansion square
    (0x800c13c8, 3, 11),     # AUDIO BGM SE
    (0x800c13ec, 2, 13),     # STEREO MONO
    (0x800c148c, 3, 5), (0x800c156c, 3, 5),      # rows
    (0x800c1cc8, 2, 11),     # Options: Message / Melee
    (0x800c1ce0, 2, 7), (0x800c1cf0, 2, 7),      # Normal Fast / Skip Watch
    (0x800c2394, 6, 3),      # grades E-S
    (0x800c2adc, 3, 7),      # Attack Wait Magic
    (0x800c3230, 6, 9),      # Enemy rear ... Our rear
    (0x800c37cc, 3, 5), (0x800c37dc, 4, 5), (0x800c37f0, 4, 5),
    (0x800c3810, 9, 7), (0x800c3850, 2, 7),
    (0x800c5244, 1, 20),     # Not enough TP
]


def off(va):
    return va - vwf.EXE_BASE + vwf.EXE_OFF


def slots():
    """[(table, key, address, field bytes)]"""
    out = []
    for name, base, stride, n, fo, fb, _ in TABLES:
        for k in range(n):
            out.append((name, '%02x' % k, base + stride * k + fo, fb))
    for a, n, stride in MISC:
        for k in range(n):
            out.append(('misc', '%08x' % (a + stride * k), a + stride * k, stride))
    return out


def export():
    d = open(EXE, 'rb').read()
    rows = []
    for t, k, a, fb in slots():
        o = off(a)
        raw = d[o:o + fb]
        n = raw.index(0) if 0 in raw else fb
        assert not any(raw[n:]), '%s %s: bytes after the string in the field' % (t, k)
        rows.append({'table': t, 'key': k, 'addr': a, 'slot': fb, 'len': n,
                     'jp': progstr.to_tagged(raw[:n])})
    os.makedirs(os.path.dirname(SCRIPT), exist_ok=True)
    json.dump(rows, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('%d slots -> %s' % (len(rows), SCRIPT))


def rows():
    if not os.path.exists(SCRIPT):
        export()
    return json.load(open(SCRIPT, encoding='utf-8'))


def names():
    return [t[0] for t in TABLES] + ['misc']


def read_tl():
    """{(table, key): English}"""
    en = {}
    for t in names():
        p = os.path.join(TL, t + '.txt')
        if not os.path.exists(p):
            continue
        for ln, line in enumerate(open(p, encoding='utf-8'), 1):
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue
            k, sep, e = line.partition('|')
            assert sep, '%s.txt:%d: bad line %r' % (t, ln, line)
            if e:
                en[(t, k)] = e
    return en


def english():
    """{(table, key): English} after translation memory (per table)"""
    R = rows()
    en = read_tl()
    mem = {}
    for r in R:
        e = en.get((r['table'], r['key']))
        if e and e != '-':
            mem.setdefault((r['table'], r['jp']), e)
    out = {}
    for r in R:
        e = en.get((r['table'], r['key'])) or mem.get((r['table'], r['jp']))
        if e and e != '-':
            out[(r['table'], r['key'])] = e
    return out


def jp_width(t):
    return progstr.jp_width(t)


def limit(r):
    """most bytes (letters) an entry may have"""
    return PACKED[r['table']][3] if r['table'] in PACKED else r['slot'] - 1


def errors(r, e):
    out = []
    b = progstr.encode(e)
    if len(b) > limit(r):
        out.append('%d bytes > %d letters at most' % (len(b), limit(r)))
    if progstr.ctrl(r['jp']) != progstr.ctrl(e):
        out.append('control tags %s != Japanese %s' % (progstr.ctrl(e), progstr.ctrl(r['jp'])))
    bad = [c for c in re.sub(progstr.TAGRE, '', e) if c not in vwf.ENC]
    if bad:
        out.append('characters not in the font: %r' % ''.join(bad))
    return out


def patch(exe, scenario):
    """(exe, scenario) with the English table entries; problems -> patch.problems"""
    exe, scenario = bytearray(exe), bytearray(scenario)
    R = {(r['table'], r['key']): r for r in rows()}
    probs = []
    E = english()
    for t, (acc, ninstr, area, _) in PACKED.items():
        base = next(x[1] for x in TABLES if x[0] == t)
        R_t = [r for r in rows() if r['table'] == t]
        if not any((t, r['key']) in E for r in R_t):
            continue
        strs = []
        for r in R_t:
            e = E.get((t, r['key']))
            jb = exe[off(r['addr']):off(r['addr']) + r['len']]
            strs.append((progstr.encode(e) if e and not errors(r, e) else bytes(jb)) + b'\0')
        blob, offs = b'', []
        for b in strs:
            offs.append(len(R_t) + len(blob)); blob += b
        if len(R_t) + len(blob) > area or max(offs) > 255:
            probs.append('%s: packed table %d bytes > %d (or an offset > 255): shorten' % (t, len(R_t) + len(blob), area))
        else:
            exe[off(base):off(base) + area] = (bytes(offs) + blob).ljust(area, b'\0')
            code = asm.assemble(acc, [('lui', 'v0', asm.hi(base)), ('addiu', 'v0', 'v0', asm.lo(base)),
                                      ('addu', 'v1', 'v0', 'a0'), ('lbu', 'v1', 0, 'v1'),
                                      ('jr', 'ra'), ('addu', 'v0', 'v0', 'v1')] + [('nop',)] * (ninstr - 6))
            exe[off(acc):off(acc) + len(code)] = code
    for tk, e in E.items():
        r = R[tk]
        x = errors(r, e)
        if x:
            probs.append('%s %s: %s' % (tk[0], tk[1], '; '.join(x))); continue
        if tk[0] in PACKED:
            continue
        b = progstr.encode(e).ljust(r['slot'], b'\0')
        a = r['addr']
        exe[off(a):off(a) + r['slot']] = b
        if SCN_VA <= a < SCN_END:
            scenario[a - SCN_VA:a - SCN_VA + r['slot']] = b
    patch.problems = probs
    return bytes(exe), bytes(scenario)


def init():
    os.makedirs(TL, exist_ok=True)
    R = rows()
    what = {t[0]: t[6] for t in TABLES}
    what['misc'] = 'loose labels (KEY = address)'
    for t in names():
        p = os.path.join(TL, t + '.txt')
        if os.path.exists(p):
            print('exists: %s' % p); continue
        keys = [r for r in R if r['table'] == t]
        with open(p, 'w', encoding='utf-8') as f:
            f.write('# %s: KEY|English, at most %d letters (see tools/tables.py; Japanese: tables.py show %s)\n'
                    % (what[t], limit(keys[0]), t))
            for r in keys:
                f.write('%s|\n' % r['key'])
        print('%s: %d keys' % (p, len(keys)))


def show(name=None, todo=False):
    en = read_tl()
    E = english()
    for r in rows():
        tk = (r['table'], r['key'])
        if name and r['table'] != name:
            continue
        if todo and tk in E:
            continue
        print('%s %s [%d/%d] %s' % (r['table'], r['key'], r['len'], limit(r), r['jp']))
        if tk in E:
            print('%s|%s%s' % (r['key'], E[tk], '' if tk in en else '   (memory)'))


def apply(name, batch):
    R = {(r['table'], r['key']): r for r in rows()}
    path = os.path.join(TL, name + '.txt')
    lines = open(path, encoding='utf-8').read().split('\n')
    idx = {l.partition('|')[0]: i for i, l in enumerate(lines) if '|' in l and not l.startswith('#')}
    errs = 0
    for line in open(batch, encoding='utf-8'):
        line = line.rstrip('\n')
        if '|' not in line or line.startswith('#'):
            continue
        k, _, e = line.partition('|')
        if k not in idx:
            print('%s: not in %s' % (k, name)); errs += 1; continue
        x = errors(R[(name, k)], e) if e not in ('', '-') else []
        if x:
            print('%s: %s' % (k, '; '.join(x))); errs += 1; continue
        lines[idx[k]] = '%s|%s' % (k, e)
    open(path, 'w', encoding='utf-8').write('\n'.join(lines))
    print('%d errors' % errs)


def check():
    R = {(r['table'], r['key']): r for r in rows()}
    n = 0
    for tk, e in english().items():
        r = R[tk]
        for x in errors(r, e):
            print('%s %s: %s' % (tk[0], tk[1], x)); n += 1
        w = vwf.width(re.sub(progstr.TAGRE, '', e))
        if w > jp_width(r['jp']) + 12:
            print('%s %s: note: %d px > Japanese %d px (%s)' % (tk[0], tk[1], w, jp_width(r['jp']), e))
    print('%d errors' % n)


def stats():
    R = rows()
    E = english()
    for t in names():
        tot = sum(1 for r in R if r['table'] == t)
        done = sum(1 for k in E if k[0] == t)
        print('%-14s %3d/%3d' % (t, done, tot))
    print('total %d/%d' % (len(E), len(R)))


if __name__ == '__main__':
    a = sys.argv[1:]
    cmd = a[0] if a else 'stats'
    if cmd == 'export':
        export()
    elif cmd == 'show':
        show(next((x for x in a[1:] if not x.startswith('--')), None), '--todo' in a)
    elif cmd == 'init':
        init()
    elif cmd == 'apply':
        apply(a[1], a[2])
    elif cmd == 'check':
        check()
    else:
        stats()
