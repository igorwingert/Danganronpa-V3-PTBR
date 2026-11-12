"""Instala/desinstala a tradução direto nos .cpk do jogo (sem Reloaded-II).

Como funciona (para cada .cpk):
  - o jogo NÃO lê nada além do tamanho original do .cpk (testado: no partition_resident ele fecha, no
    partition_data_win_us fica num loading infinito depois dos avisos). Então nada é anexado no fim:
  - o espaço dos arquivos originais que vão ser trocados fica livre; espaços vizinhos se juntam em regiões maiores;
  - os arquivos traduzidos são encaixados nessas regiões (maior primeiro, na região que sobrar menos espaço);
  - o índice (TOC) passa a apontar para eles. Cabeçalho e tamanho do arquivo não mudam.
  - antes de tudo, cabeçalho + TOC + o conteúdo original das regiões vão para data/win/ptbr_backup/.
Desinstalar = regravar tudo isso (fica idêntico ao da Steam).

Uso por linha de comando (testes): python patcher.py instalar|desinstalar|estado PASTA_DO_JOGO [dados.zip]"""
import os, sys, json, struct, hashlib, zipfile, time, shutil, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # ferramentas/ (cpk.py)
from cpk import Cpk

PASTA_BACKUP = 'ptbr_backup'
EXTS = ('.json', '.cabecalho.bin', '.toc.bin', '.lugar.bin')
EXE = 'Dangan3Win.exe'


class Erro(Exception):
    pass


def _sha1(b): return hashlib.sha1(b).hexdigest()


def _alinha(x, a): return (x + a - 1) // a * a


def pasta_win(jogo): return os.path.join(jogo, 'data', 'win')


def jogo_valido(jogo):
    w = pasta_win(jogo)
    return bool(jogo) and os.path.isfile(os.path.join(w, 'partition_data_win_us.cpk')) and os.path.isfile(os.path.join(w, 'partition_resident_win.cpk'))


def jogo_aberto():
    try:
        out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {EXE}'], capture_output=True, text=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
        return EXE.lower() in out.lower()
    except Exception:
        return False


def _ler(path, off, n):
    with open(path, 'rb') as f:
        f.seek(off); return f.read(n)


def _regioes(c):
    """(cabeçalho, TOC) originais: cabeçalho = 0..TocOffset; TOC = TocOffset..TocOffset+TocSize"""
    H = c.H
    return (0, H['TocOffset']), (H['TocOffset'], H['TocSize'])


def plano(c, fs):
    """Onde gravar cada arquivo traduzido sem passar do fim original do .cpk.
    c = Cpk aberto (original); fs = [{p, tam}] -> (regioes [(ini, fim)] em posição absoluta no arquivo, {p: posição absoluta})"""
    from collections import Counter
    H = c.H; A = H['Align']; eoff = H['EtocOffset']
    offs = sorted({r['FileOffset'] for r in c.toc.rows} | {eoff - c.add})
    usos = Counter(r['FileOffset'] for r in c.toc.rows)  # dados compartilhados por 2 entradas: não dá pra liberar
    trocados = {i['p'].lower() for i in fs}
    sl = []
    for i in fs:
        r = c.entrada(i['p']); o = r['FileOffset']
        if usos[o] == 1 or all((x['DirName'] + '/' + x['FileName']).lower() in trocados
                               for x in c.toc.rows if x['FileOffset'] == o):
            sl.append((c.add + o, c.add + offs[offs.index(o) + 1]))
    reg = []
    for a, b in sorted(set(sl)):
        if reg and reg[-1][1] == a: reg[-1][1] = b
        else: reg.append([a, b])
    pos = [a for a, b in reg]; livre = [b - a for a, b in reg]; onde = {}
    for i in sorted(fs, key=lambda i: (-i['tam'], i['p'])):
        n = _alinha(i['tam'], A)
        cand = [k for k, v in enumerate(livre) if v >= n]
        if not cand:
            raise Erro(f'{i["p"]} não cabe no espaço livre do pacote ({sum(livre) // 1024} KB livres).')
        k = min(cand, key=lambda k: (livre[k], k))
        onde[i['p']] = pos[k]; pos[k] += n; livre[k] -= n
    return [tuple(x) for x in reg], onde


def _arq_estado(jogo, nome): return os.path.join(pasta_win(jogo), PASTA_BACKUP, nome + '.json')


def estado(jogo):
    """{cpk: 'original' | 'instalado' | 'desconhecido'} + versão instalada"""
    res = {}; versao = None
    for nome in ('partition_data_win_us.cpk', 'partition_resident_win.cpk'):
        path = os.path.join(pasta_win(jogo), nome); st = _arq_estado(jogo, nome)
        if not os.path.exists(st):
            res[nome] = 'original'; continue
        e = json.load(open(st, encoding='utf-8'))
        c = Cpk(path); (h0, hn), (t0, tn) = _regioes(c); c.f.close()
        toc = _sha1(_ler(path, t0, tn))
        if toc == e['toc_patch_sha1'] and os.path.getsize(path) == e['tam_patch']:
            res[nome] = 'instalado'; versao = e.get('versao')
        elif toc == e['toc_orig_sha1'] and os.path.getsize(path) == e['tam_orig']:
            res[nome] = 'original'  # a Steam restaurou o arquivo: o backup não vale mais
        else:
            res[nome] = 'desconhecido'
    return res, versao


def _restaura(jogo, nome, prog):
    path = os.path.join(pasta_win(jogo), nome); st = _arq_estado(jogo, nome)
    e = json.load(open(st, encoding='utf-8')); bk = os.path.join(pasta_win(jogo), PASTA_BACKUP)
    hdr = open(os.path.join(bk, nome + '.cabecalho.bin'), 'rb').read()
    toc = open(os.path.join(bk, nome + '.toc.bin'), 'rb').read()
    assert _sha1(hdr) == e['hdr_orig_sha1'] and _sha1(toc) == e['toc_orig_sha1'], 'backup corrompido'
    lugar = e.get('no_lugar', [])
    if lugar:
        orig = open(os.path.join(bk, nome + '.lugar.bin'), 'rb').read()
        assert _sha1(orig) == e['lugar_sha1'], 'backup corrompido'
    prog(None, f'Restaurando {nome}...')
    with open(path, 'r+b') as f:
        for off, n, ini in lugar:  # bytes originais dos arquivos trocados no lugar
            f.seek(off); f.write(orig[ini:ini + n])
        f.seek(e['toc_off']); f.write(toc)
        f.seek(0); f.write(hdr)
        f.truncate(e['tam_orig']); f.flush(); os.fsync(f.fileno())
    # confere
    assert os.path.getsize(path) == e['tam_orig']
    assert _sha1(_ler(path, 0, len(hdr))) == e['hdr_orig_sha1'] and _sha1(_ler(path, e['toc_off'], len(toc))) == e['toc_orig_sha1']
    for ext in EXTS:
        p = os.path.join(bk, nome + ext)
        if os.path.exists(p): os.remove(p)


def desinstalar(jogo, prog=lambda f, m: None):
    if jogo_aberto(): raise Erro('Feche o jogo antes de continuar.')
    est, _ = estado(jogo)
    if 'desconhecido' in est.values():
        raise Erro('Os arquivos do jogo foram alterados por outro programa ou atualização.\n'
                   'Para voltar ao original, use na Steam: botão direito no jogo > Propriedades > '
                   'Arquivos instalados > Verificar integridade dos arquivos.')
    for nome, s in est.items():
        st = _arq_estado(jogo, nome)
        if s == 'instalado': _restaura(jogo, nome, prog)
        elif os.path.exists(st):  # backup velho de um arquivo que a Steam já restaurou
            for ext in EXTS:
                p = os.path.join(pasta_win(jogo), PASTA_BACKUP, nome + ext)
                if os.path.exists(p): os.remove(p)
    bk = os.path.join(pasta_win(jogo), PASTA_BACKUP)
    if os.path.isdir(bk) and not os.listdir(bk): os.rmdir(bk)
    prog(1.0, 'Tradução removida.')


def instalar(jogo, dados, prog=lambda f, m: None):
    """dados = caminho do dados.zip (manifest.json + <cpk>/<arquivo>)"""
    if not jogo_valido(jogo): raise Erro('Essa pasta não parece ser a do Danganronpa V3 (falta data/win/*.cpk).')
    if jogo_aberto(): raise Erro('Feche o jogo antes de continuar.')
    z = zipfile.ZipFile(dados); man = json.loads(z.read('manifest.json'))
    est, _ = estado(jogo)
    if 'desconhecido' in est.values():
        raise Erro('Os arquivos do jogo foram alterados por outro programa ou atualização.\n'
                   'Use na Steam: botão direito no jogo > Propriedades > Arquivos instalados > '
                   'Verificar integridade dos arquivos, e depois rode o instalador de novo.')
    if 'instalado' in est.values():  # reinstalação / atualização: volta ao original primeiro
        desinstalar(jogo, prog)
    total = sum(sum(i['tam'] for i in fs) for fs in man['cpks'].values())
    livre = shutil.disk_usage(pasta_win(jogo)).free
    if livre < total + 64 * 2 ** 20:
        raise Erro(f'Espaço insuficiente no disco: precisa de {total / 2 ** 20 + 64:.0f} MB livres.')
    for nome, fs in man['cpks'].items():  # confere se tudo cabe ANTES de mexer em qualquer .cpk
        c = Cpk(os.path.join(pasta_win(jogo), nome))
        try:
            if [i['p'] for i in fs if i['p'].lower() not in c.files]:
                raise Erro(f'{nome} não tem os arquivos esperados: versão do jogo diferente?')
            plano(c, fs)
        finally:
            c.f.close()
    feito = 0
    bk = os.path.join(pasta_win(jogo), PASTA_BACKUP); os.makedirs(bk, exist_ok=True)
    for nome, fs in man['cpks'].items():
        path = os.path.join(pasta_win(jogo), nome)
        c = Cpk(path); H = c.H; A = H['Align']; tam0 = os.path.getsize(path)
        (h0, hn), (t0, tn) = _regioes(c)
        eoff = H['EtocOffset']
        if not (H.get('ItocOffset') in (None, 0) and H.get('EnableTocCrc') in (None, 0) and not c.toc.cifrada and eoff
                and eoff + H['EtocSize'] == tam0):
            raise Erro(f'Formato inesperado em {nome}: esta versão do jogo não é suportada.')
        faltam = [i['p'] for i in fs if i['p'].lower() not in c.files]
        if faltam: raise Erro(f'{nome} não tem os arquivos esperados ({faltam[0]}...): versão do jogo diferente?')
        hdr, toc = _ler(path, h0, hn), _ler(path, t0, tn)
        regioes, onde = plano(c, fs)  # Erro se algo não couber
        # 1) backup do original: cabeçalho, TOC e o conteúdo das regiões que vão ser sobrescritas
        lugar = []; orig = bytearray()
        for a, b in regioes:
            lugar.append((a, b - a, len(orig))); orig += _ler(path, a, b - a)
        open(os.path.join(bk, nome + '.cabecalho.bin'), 'wb').write(hdr)
        open(os.path.join(bk, nome + '.toc.bin'), 'wb').write(toc)
        with open(os.path.join(bk, nome + '.lugar.bin'), 'wb') as fb:
            fb.write(orig); fb.flush(); os.fsync(fb.fileno())
        # 2) arquivos novos nas regiões livres (nunca além do fim original)
        tam1 = tam0
        with open(path, 'r+b') as f:
            for i in fs:
                prog(feito / total, f'Gravando {i["p"]}')
                b = z.read(nome + '/' + i['p'])
                assert len(b) == i['tam'] and _sha1(b) == i['sha1'], 'dados do instalador corrompidos'
                f.seek(onde[i['p']]); f.write(b)
                feito += len(b)
            f.flush(); os.fsync(f.fileno())
            # 3) índice apontando para os arquivos novos
            base_toc = t0 + 16  # o @UTF do TOC começa depois dos 16 bytes do bloco "TOC "
            for i in fs:
                pz = c.entrada(i['p'])['_pos']
                for col, v in (('FileOffset', onde[i['p']] - c.add), ('FileSize', i['tam']), ('ExtractSize', i['tam'])):
                    rel, fmt = pz[col]; f.seek(base_toc + rel); f.write(struct.pack(fmt, v))
            f.flush(); os.fsync(f.fileno())
        assert os.path.getsize(path) == tam0
        c.f.close()
        e = dict(versao=man['versao'], tam_orig=tam0, tam_patch=tam1, toc_off=t0,
                 hdr_orig_sha1=_sha1(hdr), toc_orig_sha1=_sha1(toc), toc_patch_sha1=_sha1(_ler(path, t0, tn)),
                 no_lugar=lugar, lugar_sha1=_sha1(bytes(orig)), data=time.strftime('%Y-%m-%d %H:%M'))
        json.dump(e, open(_arq_estado(jogo, nome), 'w', encoding='utf-8'), indent=1)
        # 4) confere lendo de volta pelo índice novo
        prog(feito / total, f'Conferindo {nome}...')
        c2 = Cpk(path)
        for i in fs:
            b, _ = c2.le(i['p'])
            if _sha1(b) != i['sha1']:
                c2.f.close(); raise Erro(f'Falha ao conferir {i["p"]} em {nome}.')
        c2.f.close()
    prog(1.0, 'Tradução instalada!')
    return man['versao']


if __name__ == '__main__':
    acao, jogo = sys.argv[1], sys.argv[2]
    pr = lambda f, m: print(f'[{f * 100:5.1f}%] {m}' if f is not None else m)
    if acao == 'instalar': print('versão', instalar(jogo, sys.argv[3], pr))
    elif acao == 'desinstalar': desinstalar(jogo, pr)
    print(estado(jogo))
