"""Check your own disc image and create the working folder extract/ (and the Japanese
script dump script/), both generated on each machine and never distributed.

usage: python3 tools/setup.py [image.bin]
"""
import hashlib, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import iso

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACT = os.path.join(ROOT, 'extract')
CLEAN = os.path.join(ROOT, 'soeldnerschild.bin')
CLEAN_SHA1 = 'd506e24da6e1772c61d2b9b67a89ad7b698747c9'


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        while chunk := f.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else CLEAN
    digest = sha1(path)
    if digest != CLEAN_SHA1:
        sys.exit('%s: SHA-1 %s does not match the clean dump (%s)' % (path, digest, CLEAN_SHA1))
    disc = iso.Disc(path); n = 0
    for name, lba, size in disc.walk():
        if name.endswith('.STR') or name == 'XA.DAT':
            continue                     # movies, XA audio
        p = os.path.join(EXTRACT, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(disc.read(lba, size))
        n += 1
    print('extract/: %d files' % n)
    import tl
    tl.dump()
    print('ready')


if __name__ == '__main__':
    main()
