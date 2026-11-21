"""Text in the fixed-slot data files JOBDATA.DAT (job descriptions) and BEVENT.DAT (mission goals,
battle choices): English written in place, each string in its own slot.

JOBDATA.DAT: 129 records of 302 bytes (0-93 used), the whole file is loaded to 0x801f0000 and
0x8001aae4(i) returns 0x801f0000 + 302 i; printed by 0x80016afc in the Guild's job window (left 40,
limit 272 = 232 px wide like the dialogue box, ~10 lines). 'n' = new line. 301 letters at most.

BEVENT.DAT: 256 blocks (header u32 BE offset, u32 BE size); block = u16 n, 2n u16 offsets (event
scripts), then the goal table at 2 + 4n: 4 victory + 4 defeat conditions of 33 bytes (32 letters).
In the scripts, a choice is 06 cc + cc options of 33 bytes. Bytes after a slot's zero are leftovers.

tl/datatext/jobdata.txt  "NN|English"    ({n} = new line)
tl/datatext/bevent.txt   "OFFSET|English" (file offset, hex); same Japanese = same English
(translation memory: only the first offset of each Japanese string is listed).

  datatext.py export | show [jobdata|bevent] [--todo] | init | apply NAME BATCH | check | stats
"""
import collections, json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import progstr, vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'datatext')
SCRIPT = os.path.join(ROOT, 'script', 'datatext.json')
FILES = {'jobdata': 'JOBDATA.DAT', 'bevent': 'BEVENT.DAT'}
JOB_SIZE, JOB_LINES, GOAL, BOX_W = 302, 10, 33, vwf.LINE_W
KEYLINE = re.compile(r'([0-9a-f]+)\|(.*)$')


def sjis_start(b):
    return len(b) >= 2 and (0x81 <= b[0] <= 0x9f or 0xe0 <= b[0] <= 0xef)


def slots(name, d):
    """[(offset, size, kind)] of the text slots of a clean file"""
    out = []
    if name == 'jobdata':
        for i in range(len(d) // JOB_SIZE):
            if d[i * JOB_SIZE]:
                out.append((i * JOB_SIZE, JOB_SIZE, 'job'))
        return out
    for i in range(struct.unpack_from('>I', d, 0)[0] // 8):
        o, sz = struct.unpack_from('>II', d, 8 * i)
        if not sz:
            continue
        b = d[o:o + sz]
        n = struct.unpack_from('>H', b, 0)[0]
        g = 2 + 4 * n
        first = struct.unpack_from('>H', b, 2)[0]
        assert first == g + 8 * GOAL, (i, hex(o))
        for k in range(8):
            if b[g + GOAL * k]:
                out.append((o + g + GOAL * k, GOAL, 'win' if k < 4 else 'lose'))
        for m in re.finditer(rb'\x06([\x02-\x06])', b[first:]):
            p, c = first + m.end(), m.group(1)[0]
            if all(sjis_start(b[p + GOAL * k:p + GOAL * k + 2]) for k in range(c)):
                for k in range(c):
                    out.append((o + p + GOAL * k, GOAL, 'choice%d/%d' % (k + 1, c)))
    return out


def export():
    rows = {}
    for name, fn in FILES.items():
        d = open(os.path.join(ROOT, 'extract', fn), 'rb').read()
        rows[name] = [{'key': ('%02d' % (o // JOB_SIZE)) if name == 'jobdata' else '%05x' % o,
                       'off': o, 'size': sz, 'kind': kd,
                       'jp': progstr.to_tagged(d[o:o + sz].split(b'\0')[0])} for o, sz, kd in slots(name, d)]
    os.makedirs(os.path.dirname(SCRIPT), exist_ok=True)
    json.dump(rows, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(', '.join('%s %d' % (k, len(v)) for k, v in rows.items()), '->', SCRIPT)


def rows():
    if not os.path.exists(SCRIPT):
        export()
    return json.load(open(SCRIPT, encoding='utf-8'))


def read_tl(name):
    en = {}
    p = os.path.join(TL, name + '.txt')
    if os.path.exists(p):
        for ln, line in enumerate(open(p, encoding='utf-8'), 1):
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue
            m = KEYLINE.match(line)
            assert m, '%s:%d: bad line %r' % (p, ln, line)
            if m.group(2):
                en[m.group(1)] = m.group(2)
    return en


def english(name):
    """{key: tagged English} after translation memory"""
    en = read_tl(name)
    mem = {}
    for r in rows()[name]:
        if r['key'] in en:
            mem.setdefault(r['jp'], en[r['key']])
    return {r['key']: en.get(r['key'], mem.get(r['jp'])) for r in rows()[name]
            if r['key'] in en or r['jp'] in mem}


def lines(e):
    return vwf.wrap(re.sub(r'\{n\}', '\n', re.sub(r'\{(?!n\})[^}]*\}', '', e)), BOX_W)


def jp_width(t):
    return progstr.jp_width(t)


def errors(name, r, e):
    out = []
    b = progstr.from_tagged(e)
    if len(b) >= r['size']:
        out.append('%d bytes > %d' % (len(b), r['size'] - 1))
    if progstr.ctrl(e) and name == 'bevent':
        out.append('no tags in goals / choices')
    bad = [c for c in re.sub(progstr.TAGRE, '', e) if c not in vwf.ENC]
    if bad:
        out.append('characters not in the font: %r' % ''.join(bad))
    if name == 'jobdata' and len(lines(e)) > JOB_LINES:
        out.append('%d lines > %d' % (len(lines(e)), JOB_LINES))
    return out


def notes(name, r, e):
    if name == 'bevent' and vwf.width(e) > jp_width(r['jp']) + 12:
        return ['note: %d px > Japanese %d px' % (vwf.width(e), jp_width(r['jp']))]
    return []


def patch(name, d):
    """file with the English; returns (bytes, problems)"""
    d = bytearray(d)
    R = {r['key']: r for r in rows()[name]}
    probs = []
    for k, e in english(name).items():
        r = R[k]
        x = errors(name, r, e)
        if x:
            probs.append('%s %s: %s' % (name, k, '; '.join(x))); continue
        b = progstr.from_tagged(e)
        d[r['off']:r['off'] + r['size']] = b.ljust(r['size'], b'\0')
    return bytes(d), probs


def init():
    os.makedirs(TL, exist_ok=True)
    for name, R in rows().items():
        p = os.path.join(TL, name + '.txt')
        if os.path.exists(p):
            print('exists: %s' % p); continue
        seen = set()
        with open(p, 'w', encoding='utf-8') as f:
            f.write('# KEY|English (tools/datatext.py; Japanese: datatext.py show %s)\n' % name)
            for r in R:
                if r['jp'] in seen:
                    continue
                seen.add(r['jp'])
                f.write('%s|\n' % r['key'])
        print('%s: %d keys' % (p, len(seen)))


def show(name=None, todo=False):
    for nm, R in rows().items():
        if name and nm != name:
            continue
        en, own = english(nm), read_tl(nm)
        listed = set(k for k in open(os.path.join(TL, nm + '.txt'), encoding='utf-8').read().split('\n')
                     for k in [k.split('|')[0]]) if os.path.exists(os.path.join(TL, nm + '.txt')) else None
        for r in R:
            if listed is not None and r['key'] not in listed:
                continue                                  # a repeat (translation memory)
            if todo and r['key'] in en:
                continue
            print('%s [%s %d] %s' % (r['key'], r['kind'], r['size'] - 1, r['jp']))
            if r['key'] in own:
                print('%s|%s' % (r['key'], own[r['key']]))


def apply(name, batch):
    R = {r['key']: r for r in rows()[name]}
    p = os.path.join(TL, name + '.txt')
    L = open(p, encoding='utf-8').read().split('\n')
    idx = {m.group(1): i for i, l in enumerate(L) for m in [KEYLINE.match(l)] if m}
    errs = 0
    for line in open(batch, encoding='utf-8'):
        m = KEYLINE.match(line.rstrip('\n'))
        if not m:
            continue
        k, e = m.groups()
        if k not in idx:
            print('%s: not in %s' % (k, p)); errs += 1; continue
        x = errors(name, R[k], e)
        if x:
            print('%s: %s' % (k, '; '.join(x))); errs += 1; continue
        L[idx[k]] = '%s|%s' % (k, e)
    open(p, 'w', encoding='utf-8').write('\n'.join(L))
    print('%d errors' % errs)


def check():
    errs = 0
    for name, R in rows().items():
        en = english(name)
        for r in R:
            if r['key'] not in en:
                continue
            for x in errors(name, r, en[r['key']]):
                print('%s %s: %s' % (name, r['key'], x)); errs += 1
            for x in notes(name, r, en[r['key']]):
                print('%s %s: %s' % (name, r['key'], x))
    print('%d errors' % errs)
    return errs


def stats():
    for name, R in rows().items():
        en = english(name)
        print('%s: %d slots, %d unique Japanese, %d in English'
              % (name, len(R), len({r['jp'] for r in R}), sum(r['key'] in en for r in R)))


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == 'export':
        export()
    elif a[0] == 'show':
        rest = [x for x in a[1:] if x != '--todo']
        show(rest[0] if rest else None, '--todo' in a)
    elif a[0] == 'init':
        init()
    elif a[0] == 'apply':
        apply(a[1], a[2])
    elif a[0] == 'check':
        sys.exit(1 if check() else 0)
    elif a[0] == 'stats':
        stats()
    else:
        sys.exit(__doc__)
