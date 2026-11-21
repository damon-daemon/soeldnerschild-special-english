"""Write the exe changes of a build into the running emulator's RAM (a save state restores the exe of
the time it was made). Every byte where the built exe differs from the clean one is written, except in
the SCENARIO.DAT mirror (0x800c66ec-0x800caceb: persons, companies ... are game state there), where
only the name fields of tables.py's tables (nations, towns, companies) are written.

usage: python3 tools/emu/exepoke.py [build.bin]     (default build/soeldnerschild_en.bin)
"""
import os, sys

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D); sys.path.insert(0, os.path.dirname(D))
import gdbmem, iso, setup, tables

BASE, FOFF = 0x80010000, 0x800
SKIP = (0x800c66ec, 0x800cacec)
RUNTIME = [(0x800c5dfc, 0x800c5f04)]   # mission goal buffers (written at battle start) after the class table


def runs(a, b):
    i, n = 0, min(len(a), len(b))
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and (a[j] != b[j] or (j + 8 < n and a[j:j + 8] != b[j:j + 8])):
                j += 1
            k = j + 1 if j < n and b[j] == 0 else j   # + the string terminator: a state made with
            yield i, k                                # an older English exe may hold a longer string
            i = k
        else:
            i += 1


def merged(a, b, gap=48):
    """runs() with gaps of up to `gap` unchanged bytes bridged: a byte the new build shares with the
    clean exe may still differ in a state made with an older English exe (e.g. full-width spaces
    inside a re-spaced string)."""
    cur = None
    for i, k in runs(a, b):
        if cur and i - cur[1] <= gap and not any(lo < BASE + i and BASE + cur[1] < hi for lo, hi in RUNTIME + [SKIP]):
            cur = (cur[0], k)
        else:
            if cur:
                yield cur
            cur = (i, k)
    if cur:
        yield cur


def main():
    built = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(D)), 'build', 'soeldnerschild_en.bin')
    clean = iso.Disc(setup.CLEAN); new = iso.Disc(built)
    c = clean.file(iso.EXE_NAME, clean.records()); n = new.file(iso.EXE_NAME, new.records())
    g = gdbmem.G()
    total = 0
    for i, j in merged(c[FOFF:], n[FOFF:]):
        va = BASE + i
        if SKIP[0] <= va < SKIP[1]:
            continue
        if any(lo <= BASE + j - 1 < hi for lo, hi in RUNTIME):
            j -= 1                     # not the terminator byte: a runtime buffer starts there
        data = n[FOFF + i:FOFF + j]
        for k in range(0, len(data), 0x200):
            part = data[k:k + 0x200]
            r = g.cmd('M%x,%x:%s' % (va + k, len(part), part.hex()))
            assert r == 'OK', r
        total += len(data)
    for t, k, va, fb in tables.slots():
        if SKIP[0] <= va < SKIP[1]:
            o = FOFF + va - BASE
            if n[o:o + fb] != c[o:o + fb]:
                r = g.cmd('M%x,%x:%s' % (va, fb, n[o:o + fb].hex()))
                assert r == 'OK', r
                total += fb
    g.resume()
    print('%d bytes written' % total)


if __name__ == '__main__':
    main()
