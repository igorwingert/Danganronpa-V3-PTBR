# Instalador

Código do `Instalador_DRV3_PTBR.exe` (Python + tkinter, empacotado com PyInstaller).

- `app.py`: a janela.
- `patcher.py`: instala e desinstala.
- `cpk.py`: lê o formato `.cpk` da CRI.

## O que ele faz em cada `.cpk` do jogo (`data/win`)

O jogo não lê nada além do tamanho original do `.cpk`. Dados anexados no fim fazem o jogo fechar (`partition_resident_win.cpk`) ou travar num loading infinito (`partition_data_win_us.cpk`). Por isso o tamanho do arquivo nunca muda:

1. O espaço ocupado pelos arquivos originais que vão ser trocados fica livre. Espaços vizinhos se juntam em regiões maiores.
2. Guarda o cabeçalho, o índice (TOC) e o conteúdo original dessas regiões em `data/win/ptbr_backup/` (uns 180 MB).
3. Encaixa os arquivos traduzidos nessas regiões, do maior para o menor, cada um na região onde sobra menos espaço.
4. Atualiza o índice para apontar para os arquivos novos e confere tudo lendo de volta.

Antes de mexer em qualquer coisa, ele confere se tudo cabe. O `gerar.py` faz a mesma conferência ao montar o `.exe`.

**Desinstalar** regrava as regiões, o índice e o cabeçalho originais. O resultado é **idêntico byte a byte** ao arquivo da Steam.

## Linha de comando

```
Instalador_DRV3_PTBR.exe --instalar "C:\caminho\do\jogo" --log log.txt
Instalador_DRV3_PTBR.exe --desinstalar "C:\caminho\do\jogo" --log log.txt
```

Os arquivos da tradução (`dados.zip`) vão dentro do `.exe` e não ficam neste repositório.
