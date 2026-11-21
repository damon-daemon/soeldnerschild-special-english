"""Battle cheat for testing: leave one soldier in each unit of companies FIRST..LAST (live RAM, via GDB).
Company records: 97 bytes from 0x800ca324; 3 units each, 26 soldier bytes at +0x13 + 26 * unit (non-zero =
alive; the men count = non-zero bytes, 0x800489ec). Pirate mission (s33): enemy companies 10-15.
Hero rank (Guild jobs / hiring need >= 2 = Merc Cpt): byte 0x13 & 0x1f of person 0 = 0x800c755b
(e.g. gdb 'M800c755b,1:42').

usage: python3 tools/emu/weaken.py FIRST LAST
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdbmem import G

B = 0x800ca324
g = G()
g.cmd('?')
for c in range(int(sys.argv[1]), int(sys.argv[2]) + 1):
    for k in range(3):
        a = B + c * 97 + 0x13 + 26 * k
        d = g.read(a, 26)
        if any(d):
            i = next(j for j in range(26) if d[j])
            n = bytes(d[i] if j == i else 0 for j in range(26))
            print(c, k, g.cmd('M%x,%x:%s' % (a, 26, n.hex())))
g.resume()
