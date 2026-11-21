"""Build the patched disc image from the clean one and tl/.

Output: build/soeldnerschild_en.bin + .cue and build/soeldnerschild_en.xdelta. With nothing
translated the image is identical to the clean one (same SHA-1).

usage: python3 tools/build.py [--force] [clean.bin] [out.bin]
  --force   build even with errors in tl/ or an oversized block (emulator tests only)
"""
import os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(__file__))
import datatext, gfx, gfxbattle, iso, msg, nameentry, names, progstr, exefix, setup, tables, tl, vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'build', 'soeldnerschild_en.bin')
PATCH = 'soeldnerschild_en.xdelta'
FIXED = (iso.EXE_NAME, 'SYSTEM.CNF')     # must keep their place
SECTOR = 2048
MAXBLOCK = 40960                         # the game loads a block to 0x80152000; other data from 0x8015c000
MARKER = '－－－'                        # writers' section markers (never shown): emptied


def block(clean, b):
    """(bytes of block b as the build makes it, English entries, errors)."""
    o, s = msg.blocks(clean)[b]
    strs = [st for _, st in msg.strings(clean, o, s)]
    en = tl.read_tl(os.path.join(tl.TL, '%03d.txt' % b))
    if not en:
        return clean[o:o + s], en, []
    errs = []
    J = {x['n']: x['jp'] for x in tl.jp(b)}; T = tl.targets(J)
    for n, e in en.items():
        errs += ['%03d @%d: %s' % (b, n, x) for x in tl.errors(J[n], e, en, n in T, b == tl.BIO, tl.caption_limits(b).get(n))]
        strs[n] = msg.from_tagged(e.replace('\n', ''), vwf.encode)
    for n, j in J.items():
        if MARKER in j:
            strs[n] = b'\0'
    last = msg.to_tagged(strs[-1])           # drop the sector padding after the last string
    while last.endswith('{x:00}'):
        last = last[:-6]
    strs[-1] = msg.from_tagged(last) + b'\0'
    blk = msg.build_block(strs, share=True)
    blk += b'\0' * (-len(blk) % SECTOR)
    if len(blk) > MAXBLOCK:
        errs.append('block %03d: %d bytes > %d (the game\'s buffer): shorten its English' % (b, len(blk), MAXBLOCK))
    return blk, en, errs


def message(clean, force=False):
    """Rebuilt MESSAGE.DAT (or None if nothing is translated)."""
    blocks = msg.blocks(clean)
    out = []; changed = 0; errs = []
    for b in range(len(blocks)):
        blk, en, e = block(clean, b)
        out.append(blk); changed += len(en); errs += e
    if force:
        for e in errs:
            print('warning (--force): ' + e)
        errs = []
    if errs:
        sys.exit('\n'.join(errs) + '\n%d errors' % len(errs))
    if not changed:
        return None
    hdr = bytearray(blocks[0][0]); pos = len(hdr)
    for i, blk in enumerate(out):
        hdr[8 * i:8 * i + 8] = pos.to_bytes(4, 'big') + len(blk).to_bytes(4, 'big')
        pos += len(blk)
    print('MESSAGE.DAT: %d strings in English' % changed)
    return bytes(hdr) + b''.join(out)


def build_files(disc, recs, force=False):
    files = {}
    m = message(disc.file('MESSAGE.DAT', recs), force)
    if m is not None:
        files['MESSAGE.DAT'] = m
        font, slot0 = vwf.font(disc.file('FONT12.BIN', recs), vwf.used_codes(os.path.join(ROOT, 'extract')))
        files['FONT12.BIN'] = font
        exe, pool = vwf.patch(disc.file(iso.EXE_NAME, recs), slot0)
        exe, files['SCENARIO.DAT'], pool = names.patch(exe, disc.file('SCENARIO.DAT', recs), pool, vwf.CAVE_END)
        pool = (pool + 3) & ~3
        exe, pool = nameentry.patch(exe, slot0, pool, vwf.CAVE_END)
        print('exe cave: %d bytes free' % (vwf.CAVE_END - pool))
        exe, probs = progstr.patch(exe)
        if probs and not force:
            sys.exit('\n'.join(probs) + '\n%d program string errors' % len(probs))
        for p in probs:
            print('warning (--force): ' + p)
        print('program strings: %d in English, pool %d bytes left' % (len(progstr.english()), progstr.patch.free))
        exe = exefix.patch(exe)
        exe, files['SCENARIO.DAT'] = tables.patch(exe, files['SCENARIO.DAT'])
        if tables.patch.problems and not force:
            sys.exit('\n'.join(tables.patch.problems) + '\n%d table errors' % len(tables.patch.problems))
        for p in tables.patch.problems:
            print('warning (--force): ' + p)
        print('tables: %d entries in English' % len(tables.english()))
        files[iso.EXE_NAME] = exe
    files['GRP.BIN'] = gfx.patch(disc.file('GRP.BIN', recs))
    print('GRP.BIN: labels, town plates, town names and the date plate in English')
    files['MARCH.GRP'] = gfxbattle.patch_march(disc.file('MARCH.GRP', recs))
    files['BATTLE.GRP'] = gfxbattle.patch_battle(disc.file('BATTLE.GRP', recs))
    print('MARCH.GRP / BATTLE.GRP: mission result, turn and melee result banners in English')
    for name, fn in datatext.FILES.items():
        if datatext.english(name):
            files[fn], probs = datatext.patch(name, disc.file(fn, recs))
            if probs and not force:
                sys.exit('\n'.join(probs) + '\n%d data text errors' % len(probs))
            for p in probs:
                print('warning (--force): ' + p)
            print('%s: %d strings in English' % (fn, len(datatext.english(name))))
    return files


def write(clean, out, files):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    moved = iso.write_image(clean, out, files)
    print('rebuilt %s%s' % (out, ' (moved: %s)' % ', '.join(moved) if moved else ''))
    if set(moved) & set(FIXED):
        sys.exit('%s moved on the disc' % ', '.join(set(moved) & set(FIXED)))
    iso.verify(out, files)
    iso.write_cue(out[:-4] + '.cue', out, [])
    patch = os.path.join(os.path.dirname(out), PATCH)
    try:
        subprocess.run(['xdelta3', '-e', '-f', '-9', '-S', 'djw', '-B', str(1 << 28), '-s', clean, out, patch], check=True)
        print('patch %s (%d bytes)' % (patch, os.path.getsize(patch)))
    except FileNotFoundError:
        print('xdelta3 not installed; skipped patch')


def main():
    args = sys.argv[1:]
    force = '--force' in args
    args = [a for a in args if a != '--force']
    clean = args[0] if args else setup.CLEAN
    out = args[1] if len(args) > 1 else OUT
    disc = iso.Disc(clean)
    files = build_files(disc, disc.records(), force)
    write(clean, out, files)
    if not files:
        same = setup.sha1(out) == setup.CLEAN_SHA1
        print('identity build: SHA-1 %s the clean image' % ('matches' if same else 'DIFFERS from'))


if __name__ == '__main__':
    main()
