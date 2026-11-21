"""MESSAGE.DAT format helpers."""
import struct
ARGS={ord('z'):0,ord('g'):0,ord('n'):0,ord('w'):0,ord('u'):0,ord('v'):2,ord('f'):0,ord('o'):0,ord('d'):0,
      ord('s'):2,ord('j'):2,ord('l'):2,ord('a'):2,ord('b'):1,ord('p'):1,ord('c'):1,ord('y'):5}
def blocks(d):
    first=struct.unpack('>I',d[0:4])[0]
    return [struct.unpack('>II',d[i:i+8]) for i in range(0,first,8) if struct.unpack('>II',d[i:i+8])!=(0,0)]
def strings(d,o,s):
    b=d[o:o+s]; n=struct.unpack('>H',b[:2])[0]
    offs=[struct.unpack('>H',b[2+2*j:4+2*j])[0] for j in range(n)]
    return [(offs[j], b[offs[j]:(offs[j+1] if j+1<n else s)]) for j in range(n)]
def tokenize(st):
    """Return list of ('t',text) / ('c',cmdchar,argbytes) / ('x',bytes) tokens."""
    out=[];i=0;txt=b''
    def flush():
        nonlocal txt
        if txt: out.append(('t',txt.decode('cp932'))); txt=b''
    while i<len(st):
        c=st[i]
        if (0x81<=c<=0x9f or 0xe0<=c<=0xfc) and i+1<len(st):
            try: st[i:i+2].decode('cp932'); txt+=st[i:i+2]; i+=2; continue
            except UnicodeDecodeError: pass
        if 0x30<=c<=0x39: txt+=bytes([c]); i+=1; continue
        flush()
        if c in ARGS:
            k=ARGS[c]; out.append(('c',chr(c),st[i+1:i+1+k])); i+=1+k
        else:
            out.append(('x',bytes([c]))); i+=1
    flush(); return out

NOARG='zgnwufod'
def to_tagged(st):
    """bytes -> editable tagged string. Round-trips via from_tagged."""
    out=[]
    for t in tokenize(st):
        if t[0]=='t': out.append(t[1])
        elif t[0]=='c':
            out.append('{%s}'%t[1] if not t[2] else '{%s:%s}'%(t[1],t[2].hex()))
        else: out.append('{x:%s}'%t[1].hex())
    s=''.join(out)
    return s.replace('{n}','{n}\n')
def from_tagged(s, encode=lambda t: t.encode('cp932')):
    import re
    s=s.replace('{n}\n','{n}')
    out=b''
    for part in re.split(r'(\{[a-z](?::[0-9a-f]*)?\})',s):
        if not part: continue
        m=re.fullmatch(r'\{([a-z])(?::([0-9a-f]*))?\}',part)
        if m:
            if m.group(1)=='x': out+=bytes.fromhex(m.group(2))
            else: out+=m.group(1).encode()+bytes.fromhex(m.group(2) or '')
        else: out+=encode(part)
    return out
def build_block(strs, share=False):
    """share: identical strings get one copy (their offsets point to the same bytes)."""
    n=len(strs); hdr=2+2*n; offs=[]; body=b''; seen={}
    for st in strs:
        if share and st in seen: offs.append(seen[st]); continue
        seen[st]=hdr+len(body); offs.append(hdr+len(body)); body+=st
    assert hdr+len(body)<0x10000, 'block overflow'
    return struct.pack('>H',n)+b''.join(struct.pack('>H',x) for x in offs)+body
