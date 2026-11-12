"""Janela do Instalador_DRV3_PTBR.exe (tkinter). A lógica fica em patcher.py."""
import os, sys, re, json, zipfile, threading, queue, webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patcher

BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE, 'dados.zip')
if not os.path.exists(DADOS):  # rodando direto do código-fonte
    DADOS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'release', 'build_instalador', 'dados.zip')
BANNER = os.path.join(BASE, 'banner.png')
if not os.path.exists(BANNER): BANNER = os.path.join(os.path.dirname(DADOS), 'banner.png')
REPO = 'https://github.com/igorwingert/Danganronpa-V3-PTBR'
APPID = '567640'
PRETO, CINZA, ROSA, BRANCO, VERDE, AMARELO = '#0d0d0f', '#1c1c21', '#ff208a', '#f6f6f6', '#47e08a', '#ffd23f'


def acha_jogo():
    """procura o jogo nas bibliotecas da Steam"""
    libs = []
    try:
        import winreg
        for hive, key, val in [(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                               (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
                               (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath')]:
            try: libs.append(winreg.QueryValueEx(winreg.OpenKey(hive, key), val)[0])
            except OSError: pass
        for k in (rf'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {APPID}',
                  rf'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {APPID}'):
            try:
                p = winreg.QueryValueEx(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, k), 'InstallLocation')[0]
                if patcher.jogo_valido(p): return os.path.normpath(p)
            except OSError: pass
    except ImportError:
        pass
    libs += [r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam']
    for s in list(libs):
        try:
            vdf = open(os.path.join(s, 'steamapps', 'libraryfolders.vdf'), encoding='utf-8', errors='ignore').read()
            libs += [p.replace('\\\\', '\\') for p in re.findall(r'"path"\s+"([^"]+)"', vdf)]
        except OSError: pass
    vistos = set()
    for lib in libs:
        common = os.path.normcase(os.path.join(lib, 'steamapps', 'common'))
        if common in vistos or not os.path.isdir(common): continue
        vistos.add(common)
        for d in os.listdir(common):
            p = os.path.join(common, d)
            if patcher.jogo_valido(p): return os.path.normpath(p)
    # fora da Steam: pastas "Danganronpa..." na raiz dos discos e em Games/Jogos
    for letra in 'CDEFGH':
        for raiz in (f'{letra}:\\', f'{letra}:\\Games', f'{letra}:\\Jogos'):
            try: ds = os.listdir(raiz)
            except OSError: continue
            for d in ds:
                if 'danganronpa' in d.lower() and patcher.jogo_valido(os.path.join(raiz, d)): return os.path.normpath(os.path.join(raiz, d))
    return ''


def normaliza(p):
    """aceita a pasta do jogo, a pasta data ou a data/win"""
    p = os.path.normpath(p)
    for _ in range(3):
        if patcher.jogo_valido(p): return p
        p = os.path.dirname(p)
    return ''


class App:
    def __init__(self, root):
        self.root = root; self.fila = queue.Queue(); self.ocupado = False
        self.versao = json.loads(zipfile.ZipFile(DADOS).read('manifest.json'))['versao']
        root.title(f'Danganronpa V3 - Tradução PT-BR  ·  instalador v{self.versao}')
        root.configure(bg=PRETO); root.resizable(False, False)
        try: root.iconbitmap(default=os.path.join(BASE, 'icone.ico'))
        except Exception: pass
        st = ttk.Style(root); st.theme_use('clam')
        st.configure('R.Horizontal.TProgressbar', troughcolor=CINZA, background=ROSA, bordercolor=PRETO, lightcolor=ROSA, darkcolor=ROSA)
        try:
            self.img = tk.PhotoImage(file=BANNER); tk.Label(root, image=self.img, bg=PRETO, bd=0).pack()
        except Exception:
            tk.Label(root, text='DANGANRONPA V3 · TRADUÇÃO PT-BR', font=('Impact', 26), fg=ROSA, bg=PRETO).pack(pady=20)
        f = tk.Frame(root, bg=PRETO, padx=24, pady=16); f.pack(fill='x')
        tk.Label(f, text='PASTA DO JOGO', font=('Impact', 14), fg=ROSA, bg=PRETO).pack(anchor='w')
        lin = tk.Frame(f, bg=PRETO); lin.pack(fill='x', pady=(4, 6))
        self.pasta = tk.StringVar()
        tk.Entry(lin, textvariable=self.pasta, font=('Segoe UI', 10), bg=CINZA, fg=BRANCO, insertbackground=BRANCO,
                 relief='flat', highlightthickness=1, highlightbackground='#333', highlightcolor=ROSA).pack(side='left', fill='x', expand=True, ipady=6)
        self.b_proc = self._botao(lin, 'Procurar...', self.procurar, CINZA, BRANCO, 10); self.b_proc.pack(side='left', padx=(8, 0))
        self.status = tk.Label(f, text='', font=('Segoe UI', 10, 'bold'), fg=BRANCO, bg=PRETO, anchor='w', justify='left', wraplength=590)
        self.status.pack(fill='x', pady=(2, 12))
        bts = tk.Frame(f, bg=PRETO); bts.pack(fill='x')
        self.b_inst = self._botao(bts, 'INSTALAR TRADUÇÃO', self.instalar, ROSA, BRANCO, 16, ('Impact', 18))
        self.b_inst.pack(side='left', fill='x', expand=True, ipady=4)
        self.b_desi = self._botao(bts, 'DESINSTALAR', self.desinstalar, CINZA, BRANCO, 12, ('Impact', 14))
        self.b_desi.pack(side='left', padx=(10, 0), ipady=6)
        self.prog = ttk.Progressbar(f, style='R.Horizontal.TProgressbar', maximum=1.0, length=590)
        self.prog.pack(fill='x', pady=(14, 4))
        self.msg = tk.Label(f, text='', font=('Consolas', 9), fg='#9a9aa2', bg=PRETO, anchor='w'); self.msg.pack(fill='x')
        rod = tk.Frame(root, bg=CINZA, padx=24, pady=8); rod.pack(fill='x')
        tk.Label(rod, text='Projeto de fã para fã  ·  Discord: okarma.', font=('Segoe UI', 9), fg='#b5b5bd', bg=CINZA).pack(side='left')
        lk = tk.Label(rod, text='GitHub', font=('Segoe UI', 9, 'underline'), fg=ROSA, bg=CINZA, cursor='hand2'); lk.pack(side='right')
        lk.bind('<Button-1>', lambda e: webbrowser.open(REPO))
        self.pasta.trace_add('write', lambda *a: self.atualiza())
        self.pasta.set(acha_jogo())
        if not self.pasta.get(): self.atualiza()
        root.after(100, self.loop)

    def _botao(self, pai, txt, cmd, bg, fg, w, fonte=('Segoe UI', 10, 'bold')):
        return tk.Button(pai, text=txt, command=cmd, bg=bg, fg=fg, activebackground=BRANCO, activeforeground=PRETO,
                         relief='flat', bd=0, font=fonte, cursor='hand2', width=w, disabledforeground='#666')

    def procurar(self):
        p = filedialog.askdirectory(title='Escolha a pasta do Danganronpa V3 (onde fica o Dangan3Win.exe)')
        if p:
            n = normaliza(p)
            if not n: messagebox.showerror('Pasta errada', 'Não achei o jogo nessa pasta.\nEscolha a pasta onde fica o Dangan3Win.exe.')
            else: self.pasta.set(n)

    def atualiza(self):
        if self.ocupado: return
        p = self.pasta.get(); inst = desi = False
        if not p:
            t, c = 'Não achei o jogo automaticamente. Clique em "Procurar..." e escolha a pasta do Danganronpa V3.', AMARELO
        elif not patcher.jogo_valido(p):
            t, c = 'Essa pasta não parece ser a do Danganronpa V3 (falta data/win/*.cpk).', AMARELO
        else:
            try:
                est, v = patcher.estado(p)
                vals = set(est.values())
                if vals == {'instalado'}:
                    if v == self.versao: t, c = f'✔ Tradução v{v} instalada. Pode jogar pela Steam normalmente!', VERDE
                    else: t, c = f'Tradução v{v} instalada. Clique em instalar para atualizar para a v{self.versao}.', AMARELO
                    inst = desi = True
                elif 'desconhecido' in vals:
                    t, c = ('Os arquivos do jogo foram alterados por outro programa ou atualização. Verifique a integridade '
                            'dos arquivos na Steam e depois instale de novo.'), AMARELO
                else:
                    t, c = '✔ Jogo encontrado. Tradução ainda não instalada.', BRANCO; inst = True
            except Exception as e:
                t, c = f'Erro ao ler os arquivos do jogo: {e}', AMARELO
        self.status.config(text=t, fg=c)
        self.b_inst.config(state='normal' if inst else 'disabled')
        self.b_desi.config(state='normal' if desi else 'disabled')

    def _rodar(self, fn, ok):
        self.ocupado = True
        for b in (self.b_inst, self.b_desi, self.b_proc): b.config(state='disabled')
        def trab():
            try:
                fn(self.pasta.get(), lambda fr, m: self.fila.put(('p', fr, m))); self.fila.put(('ok', ok, None))
            except patcher.Erro as e: self.fila.put(('erro', str(e), None))
            except PermissionError: self.fila.put(('admin', None, None))
            except Exception as e: self.fila.put(('erro', f'Erro inesperado: {e!r}', None))
        threading.Thread(target=trab, daemon=True).start()

    def instalar(self):
        self._rodar(lambda p, pr: patcher.instalar(p, DADOS, pr),
                    'Tradução instalada!\n\nAbra o jogo pela Steam normalmente.\n'
                    'Se a Steam verificar ou atualizar os arquivos do jogo, é só rodar este instalador de novo.')

    def desinstalar(self):
        if messagebox.askyesno('Desinstalar', 'Remover a tradução e voltar o jogo para o inglês?'):
            self._rodar(patcher.desinstalar, 'Tradução removida. O jogo voltou ao original.')

    def loop(self):
        try:
            while True:
                k, a, b = self.fila.get_nowait()
                if k == 'p':
                    if a is not None: self.prog['value'] = a
                    self.msg.config(text=b[:90])
                elif k == 'admin':
                    self.ocupado = False; self.atualiza(); self.prog['value'] = 0
                    if messagebox.askyesno('Permissão', 'O Windows não deixou alterar os arquivos do jogo.\n\n'
                                           'Se o jogo estiver aberto, feche e tente de novo.\n'
                                           'Quer reabrir o instalador como administrador?'):
                        reabre_admin(self.pasta.get())
                else:
                    self.ocupado = False; self.atualiza()
                    if k == 'ok': messagebox.showinfo('Pronto!', a)
                    else: self.prog['value'] = 0; self.msg.config(text=''); messagebox.showerror('Não deu certo', a)
        except queue.Empty:
            pass
        self.root.after(100, self.loop)


def reabre_admin(pasta):
    import ctypes
    exe = sys.executable; args = f'--pasta "{pasta}"'
    if not getattr(sys, 'frozen', False): args = f'"{os.path.abspath(__file__)}" ' + args
    if ctypes.windll.shell32.ShellExecuteW(None, 'runas', exe, args, None, 1) > 32: os._exit(0)


def linha_de_comando(argv):
    """Instalador.exe --instalar|--desinstalar|--estado PASTA [--log ARQUIVO] (sem janela)"""
    acao = next(a for a in argv if a in ('--instalar', '--desinstalar', '--estado'))
    pasta = argv[argv.index(acao) + 1]
    log = open(argv[argv.index('--log') + 1], 'w', encoding='utf-8') if '--log' in argv else sys.stdout
    pr = lambda f, m: print(m, file=log, flush=True) if log else None
    try:
        if acao == '--instalar': patcher.instalar(pasta, DADOS, pr)
        elif acao == '--desinstalar': patcher.desinstalar(pasta, pr)
        print('ESTADO', json.dumps(patcher.estado(pasta)), file=log, flush=True); return 0
    except Exception as e:
        print('ERRO', repr(e), file=log, flush=True); return 1


if __name__ == '__main__':
    if any(a in sys.argv for a in ('--instalar', '--desinstalar', '--estado')): sys.exit(linha_de_comando(sys.argv))
    root = tk.Tk(); a = App(root)
    if '--pasta' in sys.argv: a.pasta.set(sys.argv[sys.argv.index('--pasta') + 1])
    root.mainloop()
