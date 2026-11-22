"""Strings of the program SLPS_013.19 that the code or a pointer table refers to (menus, labels,
system and memory card messages, shop lines ...). Fixed-slot record tables (items, classes,
companies ...) are tables.py's business; persons / roles are names.py's, the name entry screen is
nameentry.py's (all excluded here).

tl/progstr/*.txt: "ADDR<TAB>English" lines (ADDR = the string's RAM address, 8 hex digits); '#' starts
a comment line; English "-" = keep the Japanese. Control bytes as in tl/msg: {z} {g} {n} (and {x:hh}
for anything else); printf conversions (%s %3d %7lu %y ...) are copied as they are and must match the
Japanese (same ones, same order; a pad width may change). A string without English takes the English
of another string with the same Japanese (translation memory).

References (found in the clean exe):
  data   32-bit words equal to the address (pointer tables)
  lui    a lui/addiu (or load/store) pair: only the low half is changed, so a moved string must stay
         under the same %hi
  gp     an addiu/load relative to gp (0x800e55f8): a moved string must stay within gp +- 32 KB
English that fits the slot (its bytes plus the zero padding up to the next string) is written in place.
Longer English moves to the pool (the free tail of the slots of strings written in place) and every
reference is repointed; it must stay reachable (see above), else shorten it. A string with no
reference found must fit its slot.

  progstr.py export          -> script/progstr.json
  progstr.py show [FILE] [--todo]   Japanese (and English) of a tl file's keys, or of every string
  progstr.py init            write tl/progstr/ skeleton files (keys + Japanese as comments; no overwrite)
  progstr.py apply FILE BATCH  put changed ADDR<TAB>English lines into a tl file (checked)
  progstr.py check | stats
  progstr.py width TEXT      pixel width of an English text
"""
import collections, json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import msg, vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'progstr')
SCRIPT = os.path.join(ROOT, 'script', 'progstr.json')
EXE = os.path.join(ROOT, 'extract', 'SLPS_013.19')
BASE, FOFF = vwf.EXE_BASE, vwf.EXE_OFF
GP = vwf.GP
# where the program's own strings are (the rest is code, the record tables or bss)
AREAS = [(0x80010000, 0x80012720), (0x800e5600, 0x800e6400)]
FILES = [('01_system', 0x80010000, 0x80012720), ('02_labels', 0x800e5600, 0x800e6400)]
EXCLUDE_TABLES = [(0x800c040c, 0x800c040c + 4 * 0x17)]     # roles (names.py)
EXCLUDE = {0x8001045c, 0x80010470, 0x80010488, 0x800104ac, 0x800e5700, 0x800e5708, 0x800e5710,
           0x800e5728}                                     # nameentry.py
FMT = re.compile(rb'%[-+ #0]*\d*(?:\.\d+)?l?[diouxXcsyY%]')
# references the scan misses (the lui is in another block; the register keeps %hi): target -> addiu
MANUAL_REFS = {0x800e5d38: [0x800409d4],                 # 滅亡: fallen nation in the nation list
               0x800e6188: [0x80066598, 0x80067198],     # 人 after %2d (men column)
               0x800e61a4: [0x80066bf0]}                 # "%s%s！": row + battle order shout
LOADSTORE = {0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x28, 0x29, 0x2a, 0x2b, 0x2e, 0x32, 0x3a}
KEYLINE = re.compile(r'([0-9a-f]{8})\t(.*)$')


TAGRE = r'\{[A-Z][0-9a-zA-Z]\}|\{[a-z](?::[0-9a-f]*)?\}'
FMTRE = r'%[-+ #0]*\d*(?:\.\d+)?l?[diouxXcsyY%]'


def to_tagged(b):
    """exe string bytes -> tagged text: Shift-JIS and ASCII 0x20-0x40 as text, printf conversions as
    they are, ESC C n -> {Cn}, the printer's commands -> {z} {g} {n} ..., other bytes {x:hh}"""
    out, i = [], 0
    while i < len(b):
        c = b[i]
        m = FMT.match(b, i)
        if m:
            out.append(m.group().decode()); i = m.end(); continue
        if (0x81 <= c <= 0x9f or 0xe0 <= c <= 0xfc) and i + 1 < len(b):
            try:
                out.append(b[i:i + 2].decode('cp932')); i += 2; continue
            except UnicodeDecodeError:
                pass
        if c == 0x1b and i + 2 < len(b) and 0x41 <= b[i + 1] <= 0x5a:
            out.append('{%c%c}' % (b[i + 1], b[i + 2])); i += 3; continue
        if 0x20 <= c <= 0x40:
            out.append(chr(c)); i += 1; continue
        if c in msg.ARGS:
            k = msg.ARGS[c]
            a = b[i + 1:i + 1 + k]
            out.append('{%c}' % c if not k else '{%c:%s}' % (c, a.hex())); i += 1 + k; continue
        if 0xa1 <= c <= 0xdf:
            out.append(bytes([c]).decode('cp932')); i += 1; continue
        out.append('{x:%02x}' % c); i += 1
    return ''.join(out)


def from_tagged(s, enc=vwf.encode):
    out = b''
    for part in re.split('(%s|%s)' % (TAGRE, FMTRE), s):
        if not part:
            continue
        if re.fullmatch(FMTRE, part):
            out += part.encode()
        elif re.fullmatch(r'\{[A-Z][0-9a-zA-Z]\}', part):
            out += b'\x1b' + part[1:3].encode()
        elif re.fullmatch(r'\{[a-z](?::[0-9a-f]*)?\}', part):
            m = re.fullmatch(r'\{([a-z])(?::([0-9a-f]*))?\}', part)
            out += bytes.fromhex(m.group(2)) if m.group(1) == 'x' else m.group(1).encode() + bytes.fromhex(m.group(2) or '')
        else:
            out += enc(part)
    return out


def off(va):
    return va - BASE + FOFF


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def scan_refs(d):
    """{target address: [(kind, file offset of the word)]} for data words, lui pairs and gp."""
    n = (len(d) - FOFF) // 4
    W = struct.unpack_from('<%dI' % n, d, FOFF)
    refs = collections.defaultdict(list)
    lo_area, hi_area = AREAS[0][0], AREAS[-1][1]
    for i, w in enumerate(W):
        if lo_area <= w < hi_area:
            refs[w].append(('data', FOFF + 4 * i))
        op = w >> 26
        if op == 0x0f:                                   # lui rt, hi
            rt, hi = (w >> 16) & 31, (w & 0xffff) << 16
            for j in range(i + 1, min(n, i + 40)):
                x = W[j]; xo = x >> 26; rs, xt = (x >> 21) & 31, (x >> 16) & 31
                if (xo == 0x09 or xo in LOADSTORE) and rs == rt:
                    t = (hi + s16(x & 0xffff)) & 0xffffffff
                    refs[t].append(('lui', FOFF + 4 * j))
                    if xo == 0x09 and xt == rt or xo in LOADSTORE and xo < 0x28 and xt == rt:
                        break
                    continue
                if writes(x) == rt:
                    break
                if x == 0x03e00008:
                    break
        elif (op == 0x09 or op in LOADSTORE) and (w >> 21) & 31 == 28:
            refs[(GP + s16(w & 0xffff)) & 0xffffffff].append(('gp', FOFF + 4 * i))
    for t, xs in MANUAL_REFS.items():
        for x in xs:
            assert W[(x - BASE) // 4] & 0xffff == t & 0xffff, hex(x)
            refs[t].append(('lui', FOFF + (x - BASE)))
    return refs


def writes(x):
    """register an instruction writes (None if none / unknown)"""
    op = x >> 26
    if op == 0:
        f = x & 63
        if f in (0x08, 0x18, 0x19, 0x1a, 0x1b, 0x11, 0x13, 0x0c, 0x0d):
            return None
        return (x >> 11) & 31
    if op in (0x02, 0x04, 0x05, 0x06, 0x07, 0x01) or op >= 0x28:
        return None
    if op == 0x03:
        return 31
    return (x >> 16) & 31


def is_text(b):
    try:
        t = b.decode('cp932')
    except UnicodeDecodeError:
        return False
    return any(ord(c) >= 0x3000 or 0xff01 <= ord(c) for c in t)


def export():
    d = open(EXE, 'rb').read()
    refs = scan_refs(d)
    excl = set(EXCLUDE)
    for a, b in EXCLUDE_TABLES:
        excl.update(struct.unpack_from('<%dI' % ((b - a) // 4), d, off(a)))
    rows = []
    for lo, hi in AREAS:
        o = off(lo)
        while o < off(hi):
            if d[o] == 0 or (o and d[o - 1] != 0 and (o - FOFF + BASE) not in refs):
                o += 1; continue
            e = d.index(b'\0', o)
            va = o - FOFF + BASE
            inner = [x for x in range(o + 1, e) if x % 4 == 0 and
                     any(k == 'data' for k, _ in refs.get(x - FOFF + BASE, ()))]
            if inner:                            # a referenced byte inside: data before a string
                o = inner[0]; continue
            b = d[o:e]
            t = to_tagged(b)
            if is_text(b) and '{x:' not in t and refs.get(va) and va not in excl:
                slot = e + 1                     # up to the next nonzero or referenced byte
                while slot < off(hi) and d[slot] == 0 and (slot - FOFF + BASE) not in refs:
                    slot += 1
                rows.append({'key': '%08x' % va, 'jp': t,
                             'len': len(b), 'slot': slot - o, 'refs': refs[va]})
                o = e + 1
            else:
                o += 1                           # data bytes may run into a real string
    os.makedirs(os.path.dirname(SCRIPT), exist_ok=True)
    json.dump(rows, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('%d strings -> %s' % (len(rows), SCRIPT))


def rows():
    if not os.path.exists(SCRIPT):
        export()
    return json.load(open(SCRIPT, encoding='utf-8'))


def tagged_jp(r):
    return r['jp']


def read_tl():
    """{key: English} over all tl files (and {key: file})"""
    en, where = {}, {}
    if not os.path.isdir(TL):
        return en, where
    for name in sorted(os.listdir(TL)):
        if not name.endswith('.txt'):
            continue
        for ln, line in enumerate(open(os.path.join(TL, name), encoding='utf-8'), 1):
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue
            m = KEYLINE.match(line)
            assert m, '%s:%d: bad line %r' % (name, ln, line)
            if m.group(2) != '':
                en[m.group(1)] = m.group(2)
            where[m.group(1)] = name
    return en, where


def encode(e):
    """tagged English -> bytes"""
    return from_tagged(e)


def convs(b):
    """conversions without flags / width; %Y (full-width number) counts as %d: the English prints
    the same int in ASCII digits"""
    return [re.sub(rb'^%[-+ #0]*\d*', b'%', c).replace(b'%Y', b'%d') for c in FMT.findall(b)]


def ctrl(t):
    return re.findall(TAGRE, t)


def jp_width(t):
    w = 0
    for c in re.sub(r'\{[a-z](?::[0-9a-f]*)?\}', '', t):
        w += 8 if ord(c) < 0x80 else 12
    return w


# printf strings whose arguments exefix.py reorders: address -> the conversions the English must have
REORDERED = {0x80011a3c: [b'%d', b'%u', b'%s']}    # Guild hire list: type last (exefix 8)


def errors(r, e):
    out = []
    jb = from_tagged(r['jp'], lambda t: t.encode('cp932'))
    eb = encode(e)
    if convs(eb) != REORDERED.get(int(r['key'], 16), convs(jb)):
        out.append('printf conversions %s != Japanese %s' % (convs(eb), convs(jb)))
    if ctrl(r['jp']) != ctrl(e):
        out.append('control tags %s != Japanese %s' % (ctrl(e), ctrl(r['jp'])))
    bad = [c for c in re.sub('%s|%s' % (TAGRE, FMTRE), '', e) if c not in vwf.ENC and c not in '§\u3000']   # § = the game's caption mark, \u3000 = 12 px space
    if bad:
        out.append('characters not in the font: %r' % ''.join(bad))
    return out


def english():
    """{key: English bytes} after translation memory"""
    R = rows()
    en, _ = read_tl()
    mem = {}
    for r in R:
        e = en.get(r['key'])
        if e and e != '-':
            mem.setdefault(r['jp'], e)
    out = {}
    for r in R:
        e = en.get(r['key']) or mem.get(r['jp'])
        if e and e != '-':
            out[r['key']] = e
    return out


def patch(exe):
    """exe with the English program strings; returns (exe, problems)"""
    exe = bytearray(exe)
    R = {r['key']: r for r in rows()}
    E = english()
    moved, pool, probs = [], [], []
    for k, e in E.items():
        r = R[k]
        b = encode(e) + b'\0'
        o = off(int(k, 16))
        if len(b) <= r['slot']:
            exe[o:o + r['slot']] = b.ljust(r['slot'], b'\0')
            if r['refs'] and r['slot'] - len(b) >= 4:
                a = (o + len(b) + 3) & ~3
                if o + r['slot'] - a >= 4:
                    pool.append([a, o + r['slot']])
        else:
            moved.append((k, b))
    for k, b in sorted(moved, key=lambda x: -len(x[1])):
        r = R[k]
        va = int(k, 16)
        kinds = {kd for kd, _ in r['refs']}
        if not r['refs']:
            probs.append('%s: %d bytes > slot %d and no reference: shorten' % (k, len(b), r['slot'])); continue
        place = None
        for p in pool:
            if p[1] - p[0] < len(b):
                continue
            nva = p[0] - FOFF + BASE
            if 'lui' in kinds and (nva + 0x8000) >> 16 != (va + 0x8000) >> 16:
                continue
            if 'gp' in kinds and not -0x8000 <= nva - GP < 0x8000:
                continue
            place = p; break
        if place is None:
            probs.append('%s: %d bytes > slot %d and no pool room in reach (%s): shorten'
                         % (k, len(b), r['slot'], '/'.join(sorted(kinds)))); continue
        no = place[0]; nva = no - FOFF + BASE
        exe[no:no + len(b)] = b
        place[0] = (no + len(b) + 3) & ~3
        o = off(va)
        exe[o:o + r['slot']] = bytes(r['slot'])
        for kd, wo in r['refs']:
            w = struct.unpack_from('<I', exe, wo)[0]
            if kd == 'data':
                assert w == va
                struct.pack_into('<I', exe, wo, nva)
            elif kd == 'lui':
                struct.pack_into('<I', exe, wo, (w & 0xffff0000) | ((s16(w & 0xffff) + nva - va) & 0xffff))
            else:
                struct.pack_into('<I', exe, wo, (w & 0xffff0000) | ((nva - GP) & 0xffff))
    patch.free = sum(p[1] - p[0] for p in pool)
    patch.pool = pool
    return bytes(exe), probs


def file_of(k):
    va = int(k, 16)
    for name, lo, hi in FILES:
        if lo <= va < hi:
            return name + '.txt'


def init():
    os.makedirs(TL, exist_ok=True)
    by = collections.defaultdict(list)
    for r in rows():
        by[file_of(r['key'])].append(r)
    for name, R in by.items():
        p = os.path.join(TL, name)
        if os.path.exists(p):
            print('exists: %s' % p); continue
        with open(p, 'w', encoding='utf-8') as f:
            f.write('# ADDR<TAB>English (see tools/progstr.py); Japanese: progstr.py show %s\n' % name)
            for r in R:
                f.write('%s\t\n' % r['key'])
        print('%s: %d keys' % (p, len(R)))


def show(name=None, todo=False):
    en, where = read_tl()
    for r in rows():
        if name and where.get(r['key']) != os.path.basename(name):
            continue
        if todo and r['key'] in en:
            continue
        kinds = ''.join(sorted({kd[0] for kd, _ in r['refs']}))
        print('%s [%d/%d %s] %s' % (r['key'], r['len'], r['slot'], kinds, r['jp']))
        if r['key'] in en:
            print('%s\t%s' % (r['key'], en[r['key']]))


def apply(name, batch):
    R = {r['key']: r for r in rows()}
    path = os.path.join(TL, os.path.basename(name))
    lines = open(path, encoding='utf-8').read().split('\n')
    idx = {m.group(1): i for i, l in enumerate(lines) for m in [KEYLINE.match(l)] if m}
    errs = 0
    for line in open(batch, encoding='utf-8'):
        line = line.rstrip('\n')
        m = KEYLINE.match(line)
        if not m:
            continue
        k, e = m.groups()
        if k not in idx:
            print('%s: not in %s' % (k, name)); errs += 1; continue
        x = errors(R[k], e) if e != '-' else []
        if x:
            print('%s: %s' % (k, '; '.join(x))); errs += 1; continue
        lines[idx[k]] = '%s\t%s' % (k, e)
    open(path, 'w', encoding='utf-8').write('\n'.join(lines))
    print('%d errors' % errs)


def check():
    R = {r['key']: r for r in rows()}
    en, _ = read_tl()
    n = 0
    for k, e in en.items():
        if e == '-':
            continue
        for x in errors(R[k], e):
            print('%s: %s' % (k, x)); n += 1
        if vwf.width(re.sub(r'\{[a-z](?::[0-9a-f]*)?\}', '', e)) > jp_width(R[k]['jp']) + 12 and '{n}' not in e:
            print('%s: note: %d px > Japanese %d px' % (k, vwf.width(e), jp_width(R[k]['jp'])))
    d = open(EXE, 'rb').read()
    import names, nameentry
    _, probs = patch(d)
    for p in probs:
        print(p); n += 1
    print('%d errors; pool left %d bytes' % (n, patch.free))


def width(t):
    print('%d px' % vwf.width(re.sub('%s|%s' % (TAGRE, FMTRE), lambda m: '00000' if m.group().startswith('%') else '', t)))


def stats():
    R = rows()
    E = english()
    print('%d strings, %d with English (%d by translation memory)' % (len(R), len(E), len(E) - len(read_tl()[0])))


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
    elif cmd == 'width':
        width(' '.join(a[1:]))
    else:
        stats()
