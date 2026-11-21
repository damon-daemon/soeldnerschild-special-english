"""English person and role names (tl/names/).

  persons.txt  id|name   the person table: 21-byte records, name = first 16 bytes (zero padded), both in
               the exe at 0x800c7548 (what the game reads) and in SCENARIO.DAT at 0xe5c (same data)
  roles.txt    id|name   speaker ids 0x2bc-0x2d2: pointer table 0x800c040c to strings in the exe; a name
               longer than its old string's room goes to the pool (free bytes after our VWF code)
Names are in our one-byte encoding (vwf.encode).
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERSONS_EXE, PERSONS_SCN, REC, NAME_B = 0x800c7548, 0xe5c, 21, 16
ROLES, ROLE0 = 0x800c040c, 0x2bc


def read(name):
    out = {}
    for line in open(os.path.join(ROOT, 'tl', 'names', name), encoding='utf-8'):
        line = line.rstrip('\n')
        if line and not line.startswith('#'):
            k, v = line.split('|')
            out[int(k, 16)] = v
    return out


def at(va):
    return va - vwf.EXE_BASE + vwf.EXE_OFF


def patch(exe, scenario, pool, pool_end):
    """(exe, scenario, next free pool byte) with English names; pool..pool_end = free exe bytes."""
    exe, scenario = bytearray(exe), bytearray(scenario)
    for k, name in read('persons.txt').items():
        b = vwf.encode(name)
        assert len(b) < NAME_B, 'person %03x: %r too long' % (k, name)
        for buf, o in ((exe, at(PERSONS_EXE) + REC * k), (scenario, PERSONS_SCN + REC * k)):
            buf[o:o + NAME_B] = b.ljust(NAME_B, b'\0')
    for k, name in read('roles.txt').items():
        b = vwf.encode(name) + b'\0'
        po = at(ROLES) + 4 * (k - ROLE0)
        o = at(struct.unpack_from('<I', exe, po)[0])
        end = exe.index(b'\0', o)
        room = end - o + 1
        while exe[end + 1] == 0 and (end + 1 - o) < 64:
            end += 1; room += 1
        room -= 1                                  # keep a zero before the next string
        if len(b) <= room:
            exe[o:o + room] = b.ljust(room, b'\0')
        else:
            assert pool + len(b) <= pool_end, 'name pool full'
            exe[at(pool):at(pool) + len(b)] = b
            struct.pack_into('<I', exe, po, pool)
            pool += len(b)
    return bytes(exe), bytes(scenario), pool
