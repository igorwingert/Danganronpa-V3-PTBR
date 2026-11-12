"""Leitura do formato CPK (CRI) e das tabelas @UTF, com a posição de cada valor no arquivo
(para o instalador poder editar o índice no lugar). Só leitura aqui; a escrita fica em instalador/patcher.py."""
import struct

TIPOS = {0: ('>B', 1), 1: ('>b', 1), 2: ('>H', 2), 3: ('>h', 2), 4: ('>I', 4), 5: ('>i', 4),
         6: ('>Q', 8), 7: ('>q', 8), 8: ('>f', 4), 9: ('>d', 8), 0xA: ('>I', 4), 0xB: ('>II', 8)}


def _decifra(b):
    """tabelas @UTF cifradas (XOR com chave que avança): usado por alguns jogos"""
    out = bytearray(len(b)); m, t = 0x655F, 0x4115
    for i, c in enumerate(b):
        out[i] = c ^ (m & 0xFF); m = (m * t) & 0xFFFFFFFF
    return bytes(out)


class Utf:
    """tabela @UTF. base = posição no arquivo do '@UTF' (para calcular onde cada valor está)"""

    def __init__(self, b, base=0):
        self.cifrada = b[:4] != b'@UTF'
        if self.cifrada: b = _decifra(b)
        assert b[:4] == b'@UTF', 'tabela @UTF inválida'
        self.raw = b; self.base = base
        size, = struct.unpack('>I', b[4:8]); d = b[8:8 + size]
        _, rows_off, str_off, data_off, name_off, ncol, rowlen, nrows = struct.unpack('>HHIIIHHI', d[:24])
        self.nrows, self.rowlen = nrows, rowlen
        def s(o):
            e = d.index(b'\0', str_off + o); return d[str_off + o:e].decode('utf-8', 'replace')
        self.name = s(name_off); self.cols = []
        p = 24
        for _ in range(ncol):
            fl = d[p]; nm, = struct.unpack('>I', d[p + 1:p + 5]); p += 5
            st, ty = fl & 0xF0, fl & 0x0F; const = None
            if st == 0x30:
                fmt, n = TIPOS[ty]; const = (struct.unpack(fmt, d[p:p + n]), 8 + p); p += n
            self.cols.append((s(nm), st, ty, const))
        self.rows = []
        for r in range(nrows):
            q = rows_off + r * rowlen; row = {}; pos = {}
            for nm, st, ty, const in self.cols:
                if st == 0x50:
                    fmt, n = TIPOS[ty]; v = struct.unpack(fmt, d[q:q + n]); pos[nm] = (8 + q, fmt); q += n
                elif st == 0x30: v = const[0]; pos[nm] = (const[1], TIPOS[ty][0])
                else: row[nm] = None; continue
                if ty == 0xA: v = s(v[0])
                elif ty == 0xB: v = d[data_off + v[0]:data_off + v[0] + v[1]] if v[1] else b''
                else: v = v[0]
                row[nm] = v
            self.rows.append(row); self.rows[-1]['_pos'] = pos
        self.str_off, self.data_off = str_off, data_off

    def colunas(self): return [(nm, hex(st), ty) for nm, st, ty, _ in self.cols]


def chunk(f, off):
    """lê um bloco do CPK ('CPK ', 'TOC ', 'ITOC', 'ETOC'...): 16 bytes de cabeçalho + @UTF"""
    f.seek(off); h = f.read(16); size, = struct.unpack('<Q', h[8:16])
    return h[:4], Utf(f.read(size), off + 16)


class Cpk:
    def __init__(self, path):
        self.path = path; f = self.f = open(path, 'rb')
        tag, self.hdr = chunk(f, 0); assert tag == b'CPK ', 'não é um CPK'
        H = self.H = self.hdr.rows[0]
        self.toc = chunk(f, H['TocOffset'])[1] if H.get('TocOffset') else None
        self.itoc = chunk(f, H['ItocOffset'])[1] if H.get('ItocOffset') else None
        self.etoc = chunk(f, H['EtocOffset'])[1] if H.get('EtocOffset') else None
        add = H['TocOffset']
        if H.get('ContentOffset') is not None and H['ContentOffset'] < add: add = H['ContentOffset']
        self.add = add  # FileOffset do TOC é relativo a isso
        self.files = {}
        for i, r in enumerate(self.toc.rows):
            p = (r['DirName'] + '/' if r.get('DirName') else '') + r['FileName']
            self.files[p.lower()] = i

    def entrada(self, path): return self.toc.rows[self.files[path.lower()]]

    def le(self, path):
        r = self.entrada(path); self.f.seek(self.add + r['FileOffset']); return self.f.read(r['FileSize']), r


if __name__ == '__main__':
    import sys
    c = Cpk(sys.argv[1])
    print('cabeçalho:', {k: v for k, v in c.H.items() if k != '_pos'})
    print('TOC', c.toc.name, len(c.toc.rows), 'linhas, cifrada', c.toc.cifrada, c.toc.colunas())
    for t in ('itoc', 'etoc'):
        u = getattr(c, t)
        if u: print(t.upper(), u.name, len(u.rows), u.colunas())
    for r in c.toc.rows[:3]: print({k: v for k, v in r.items() if k != '_pos'})
