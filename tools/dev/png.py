import zlib, struct
def write(path, w, h, rows):
    """rows: list of bytes, RGB, len 3w each"""
    raw=b''.join(b'\0'+bytes(r) for r in rows)
    def ch(t,b): return struct.pack('>I',len(b))+t+b+struct.pack('>I',zlib.crc32(t+b))
    open(path,'wb').write(b'\x89PNG\r\n\x1a\n'+ch(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+ch(b'IDAT',zlib.compress(raw,6))+ch(b'IEND',b''))
