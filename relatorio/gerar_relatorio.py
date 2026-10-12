"""Gera o relatório (HTML + PDF) a partir dos dados em resultados/.

Uso (na raiz do repositório, depois de rodar relatorio/experimentos.py):
    py relatorio/gerar_relatorio.py

Todos os números do texto, das tabelas e dos gráficos são calculados aqui a
partir de resultados/*.csv e das saídas oficiais resultados/*.txt.
Os trechos de código são extraídos diretamente dos main.go de cada versão.
"""

import csv
import html
import math
import pathlib
import re
import statistics as st
import subprocess
from collections import defaultdict

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import GoLexer

RAIZ = pathlib.Path(__file__).resolve().parent.parent
RES = RAIZ / "resultados"
SAIDA = RAIZ / "relatorio"
FIG = SAIDA / "figuras"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
REPO = "https://github.com/eduardolobocode/fppd-t1-filosofos"

COR = {"V0": "#2a78d6", "V2": "#eb6834", "V3": "#1baf7a"}  # slots 1-3 da paleta categórica
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
CRIT = "#d03b3b"
FONTE = "Segoe UI, system-ui, sans-serif"


# ---------------------------------------------------------------------------
# Formatação (padrão brasileiro)
# ---------------------------------------------------------------------------

def br(x, casas=1):
    s = f"{x:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fms(x, casas=1):
    return br(x, casas) + " ms"


def fs(x_ms, casas=2):
    return br(x_ms / 1000, casas) + " s"


def fx(x, casas=1):
    return br(x, casas) + "×"


def pct(x, casas=0):
    return br(x, casas) + "%"


# ---------------------------------------------------------------------------
# Leitura dos dados
# ---------------------------------------------------------------------------

def ler_csv(nome):
    with open(RES / nome, encoding="utf-8") as f:
        return list(csv.DictReader(f))


execs = ler_csv("execucoes.csv")
pfil = ler_csv("espera_por_filosofo.csv")
v1freq = ler_csv("v1_frequencia_deadlock.csv")

PENSAR, COMER = 20, 30


def teorico(v, p=PENSAR, c=COMER):
    if v == "V0":
        return 100 * (p + c)
    if v == "V2":
        return max(20 * (p + c), 100 * c)
    return max(20 * (p + c), 50 * c)


def sel(cenario="base", gmp="padrao", versao=None):
    return [r for r in execs if r["cenario"] == cenario and r["gomaxprocs"] == gmp
            and (versao is None or r["versao"] == versao)]


V = ("V0", "V2", "V3")
base = {v: sel(versao=v) for v in V}
T = {v: [float(r["tempo_total_ms"]) for r in base[v]] for v in V}
W = {v: [float(r["espera_media_ms"]) for r in base[v]] for v in V}
M = {v: [float(r["espera_max_ms"]) for r in base[v]] for v in V}
CM = {v: [int(r["max_comendo"]) for r in base[v]] for v in V}
CIC = {v: {r["ciclos"] for r in base[v]} for v in V}
N = {v: len(T[v]) for v in V}

mT = {v: st.mean(T[v]) for v in V}
sdT = {v: st.stdev(T[v]) for v in V}
mW = {v: st.mean(W[v]) for v in V}
sdW = {v: st.stdev(W[v]) for v in V}
maxM = {v: max(M[v]) for v in V}
maxC = {v: max(CM[v]) for v in V}
conc = {v: 100 * COMER / mT[v] for v in V}  # refeições * tempo de comer / tempo total
sobre = {v: (mT[v] / teorico(v) - 1) * 100 for v in V}

CENARIOS = [("pouca-disputa", 40, 10, "Pouca disputa"), ("base", 20, 30, "Base"), ("muita-disputa", 10, 40, "Muita disputa")]
S = {c: {v: st.mean([float(r["tempo_total_ms"]) for r in sel(c, versao=v)]) for v in V} for c, *_ in CENARIOS}
SW = {c: {v: st.mean([float(r["espera_media_ms"]) for r in sel(c, versao=v)]) for v in V} for c, *_ in CENARIOS}
G1 = {v: st.mean([float(r["tempo_total_ms"]) for r in sel(gmp="1", versao=v)]) for v in V}
G1C = {v: max(int(r["max_comendo"]) for r in sel(gmp="1", versao=v)) for v in V}

PF = defaultdict(dict)
_acc = defaultdict(lambda: ([], []))
for r in pfil:
    a = _acc[(r["versao"], r["filosofo"])]
    a[0].append(float(r["espera_media_ms"]))
    a[1].append(float(r["espera_max_ms"]))
for (v, f), (medias, maximas) in _acc.items():
    PF[v][f] = (st.mean(medias), max(maximas))
FILS = [f"F{i}" for i in range(5)]

dl = {a: [r for r in v1freq if r["atraso_ms"] == a] for a in ("0", "10")}
dl_n = {a: sum(int(r["deadlock"]) for r in dl[a]) for a in dl}
dl_tot = {a: len(dl[a]) for a in dl}
dl_ref = sorted(int(r["refeicoes_antes_de_parar"]) for r in dl["0"] if r["deadlock"] == "1")

# efeito de imprimir a linha do tempo (só a 1ª execução de cada rodada imprime)
d1 = {v: st.mean([float(r["tempo_total_ms"]) for r in base[v] if r["execucao"] == "1"])
      - st.mean([float(r["tempo_total_ms"]) for r in base[v] if r["execucao"] != "1"]) for v in V}

concorrentes_ok = [r for r in execs if r["versao"] in ("V2", "V3")]
todas_completas = all(r["ciclos"] == "20 20 20 20 20" for r in execs)
total_execs = len(execs)

# ---------------------------------------------------------------------------
# Saídas oficiais
# ---------------------------------------------------------------------------

saida = {v: (RES / f"{p}.txt").read_text(encoding="utf-8") for v, p in
         (("V0", "v0-sequencial"), ("V1", "v1-deadlock"), ("V2", "v2-mesa"), ("V3", "v3-ordenacao"))}
cabecalho_ambiente = next(l for l in saida["V0"].splitlines() if l.startswith("Go "))


def linha_do_tempo(txt):
    """Eventos (instante, filósofo, tipo, ciclo) da 1ª execução."""
    ev = []
    for linha in txt.splitlines():
        m = re.match(r"^\s*([\d.]+) ms  ( *)([PC])(\d+)\s*$", linha)
        if m:
            ev.append((float(m.group(1)), len(m.group(2)) // 8, m.group(3), int(m.group(4))))
    return ev


def intervalos_comendo(ev):
    """Para cada filósofo, lista de (início, fim) das refeições."""
    res = defaultdict(list)
    for t, f, tipo, c in ev:
        if tipo == "C":
            res[f].append((t, t + COMER))  # cada refeição dura o Sleep de comer
    return res


LT = {v: linha_do_tempo(saida[v]) for v in V}
IC = {v: intervalos_comendo(LT[v]) for v in V}


def primeira_sobreposicao(ic):
    """Primeiro instante em que dois filósofos estão comendo ao mesmo tempo."""
    eventos = sorted([(a, 1) for f in ic for a, b in ic[f]] + [(b, -1) for f in ic for a, b in ic[f]],
                     key=lambda e: (e[0], e[1]))
    n = 0
    for t, d in eventos:
        n += d
        if n >= 2:
            return t
    return None


t_par_v3 = primeira_sobreposicao(IC["V3"])
primeiro_a_comer_v3 = min(((a, f) for f in IC["V3"] for a, b in IC["V3"][f]))[1]
# espera da largada na V3: todos terminam de pensar juntos (instante da 1ª refeição de todas)
_fome = min(a for f in IC["V3"] for a, b in IC["V3"][f])
espera_largada = {f: IC["V3"][f][0][0] - _fome for f in IC["V3"]}
f_largada = max(espera_largada, key=espera_largada.get)

# GOMAXPROCS=1: desvio padrão
sdG1 = {v: st.stdev([float(r["tempo_total_ms"]) for r in sel(gmp="1", versao=v)]) for v in V}

# V1: quem segura e quem espera, a partir da saída oficial
v1_ev = [(float(m.group(1)), int(m.group(2)), m.group(3)) for m in
         re.finditer(r"^\s*([\d.]+) ms  F(\d): (.*)$", saida["V1"], re.M)]
segura, espera, t_pegou, t_tenta = {}, {}, [], []
for t, f, texto in v1_ev:
    if m := re.match(r"pegou g(\d) \(esquerdo\)", texto):
        segura[f] = int(m.group(1))
        t_pegou.append(t)
    elif m := re.match(r"tentando pegar g(\d)", texto):
        espera[f] = int(m.group(1))
        t_tenta.append(t)
dono = {g: f for f, g in segura.items()}
linha_lock = re.search(r"main\.pegarGarfos\([^)]*\)\s*\n[^\n]*main\.go:(\d+)", saida["V1"]).group(1)
v1_trava = "deadlock!" in saida["V1"]

# ---------------------------------------------------------------------------
# Código-fonte (extraído dos main.go)
# ---------------------------------------------------------------------------

def extrair(pasta, nome, com_comentario=True):
    linhas = (RAIZ / pasta / "main.go").read_text(encoding="utf-8").splitlines()
    ini = next(i for i, l in enumerate(linhas) if re.match(rf"^func (\(\w+ \*?\w+\) )?{nome}\(", l))
    fim = next(i for i in range(ini, len(linhas)) if linhas[i] == "}")
    if com_comentario:
        while ini > 0 and linhas[ini - 1].startswith("//"):
            ini -= 1
    return "\n".join(linhas[ini:fim + 1])


def extrair_trecho(pasta, inicio_regex, n_linhas):
    linhas = (RAIZ / pasta / "main.go").read_text(encoding="utf-8").splitlines()
    ini = next(i for i, l in enumerate(linhas) if re.match(inicio_regex, l))
    return "\n".join(linhas[ini:ini + n_linhas])


FORMATADOR = HtmlFormatter(style="default", nowrap=True)


def codigo(fonte, titulo):
    corpo = highlight(fonte, GoLexer(), FORMATADOR)
    return (f'<figure class="codigo"><div class="code-tit">{html.escape(titulo)}</div>'
            f'<pre class="highlight">{corpo}</pre></figure>')


def terminal(comando, linhas, titulo="Windows PowerShell"):
    corpo = html.escape("\n".join(linhas))
    return (f'<div class="term"><div class="term-bar"><span class="dot"></span><span class="dot"></span>'
            f'<span class="dot"></span><span class="term-tit">{html.escape(titulo)}</span></div>'
            f'<pre><span class="prompt">PS fppd-t1-filosofos&gt;</span> {html.escape(comando)}\n{corpo}</pre></div>')


# ---------------------------------------------------------------------------
# Gráficos (SVG)
# ---------------------------------------------------------------------------

def svg_abre(w, h, rotulo, margem=8):
    # fundo branco com margem: o gráfico continua legível no tema escuro do GitHub
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-margem} {-margem} {w + 2 * margem} {h + 2 * margem}" '
            f'width="100%" role="img" aria-label="{html.escape(rotulo)}" font-family="{FONTE}" font-size="10">'
            f'<rect x="{-margem}" y="{-margem}" width="{w + 2 * margem}" height="{h + 2 * margem}" rx="6" fill="#ffffff"/>')


def txt(x, y, s, cor=INK2, anc="start", tam=10, peso=400, extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{cor}" text-anchor="{anc}" font-size="{tam}" '
            f'font-weight="{peso}" {extra}>{html.escape(str(s))}</text>')


def barra_h(x0, y, w, h, cor, r=4):
    """Barra horizontal com a ponta direita arredondada e a base reta."""
    if w <= 0:
        return ""
    r = min(r, w, h / 2)
    return (f'<path d="M{x0:.1f},{y:.1f} H{x0 + w - r:.1f} Q{x0 + w:.1f},{y:.1f} {x0 + w:.1f},{y + r:.1f} '
            f'V{y + h - r:.1f} Q{x0 + w:.1f},{y + h:.1f} {x0 + w - r:.1f},{y + h:.1f} H{x0:.1f} Z" fill="{cor}"/>')


def barra_v(x, y0, w, h, cor, r=4):
    """Coluna com o topo arredondado e a base reta (y0 = linha de base)."""
    if h <= 0:
        return ""
    r = min(r, h, w / 2)
    yt = y0 - h
    return (f'<path d="M{x:.1f},{y0:.1f} V{yt + r:.1f} Q{x:.1f},{yt:.1f} {x + r:.1f},{yt:.1f} '
            f'H{x + w - r:.1f} Q{x + w:.1f},{yt:.1f} {x + w:.1f},{yt + r:.1f} V{y0:.1f} Z" fill="{cor}"/>')


def grafico_tempo_total():
    w, h, esq, dir_, topo = 360, 168, 34, 70, 30
    xmax = 6000
    X = lambda v: esq + v / xmax * (w - esq - dir_)
    s = [svg_abre(w, h, "Tempo total por versão")]
    s.append(txt(0, 12, "Tempo total do jantar (média de 30 execuções)", INK, tam=11, peso=600))
    for k in range(0, 7):
        x = X(k * 1000)
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{topo - 4}" y2="{h - 22}" stroke="{GRID}" stroke-width="1"/>')
        s.append(txt(x, h - 9, f"{k} s", MUTED, "middle", 9))
    for i, v in enumerate(V):
        y = topo + i * 38
        s.append(txt(esq - 8, y + 14, v, INK, "end", 11, 600))
        s.append(barra_h(X(0), y + 2, X(mT[v]) - X(0), 20, COR[v]))
        lo, hi = X(min(T[v])), X(max(T[v]))
        s.append(f'<line x1="{lo:.1f}" x2="{hi:.1f}" y1="{y + 12}" y2="{y + 12}" stroke="{INK}" stroke-width="1.2"/>')
        s.append(f'<line x1="{lo:.1f}" x2="{lo:.1f}" y1="{y + 7}" y2="{y + 17}" stroke="{INK}" stroke-width="1.2"/>')
        s.append(f'<line x1="{hi:.1f}" x2="{hi:.1f}" y1="{y + 7}" y2="{y + 17}" stroke="{INK}" stroke-width="1.2"/>')
        xt = X(teorico(v))
        s.append(f'<line x1="{xt:.1f}" x2="{xt:.1f}" y1="{y - 1}" y2="{y + 25}" stroke="{INK}" stroke-width="1.5" stroke-dasharray="2 2"/>')
        s.append(txt(max(hi, X(mT[v])) + 6, y + 16, fs(mT[v]), INK, tam=10, peso=600))
    s.append(f'<line x1="{X(0):.1f}" x2="{X(0):.1f}" y1="{topo - 4}" y2="{h - 22}" stroke="{AXIS}" stroke-width="1"/>')
    s.append("</svg>")
    return "".join(s)


def grafico_espera():
    w, h, esq, dir_, topo = 360, 176, 34, 14, 40
    xmax = math.ceil((max(maxM.values()) + 5) / 20) * 20
    X = lambda v: esq + v / xmax * (w - esq - dir_)
    s = [svg_abre(w, h, "Espera pelos garfos por versão")]
    s.append(txt(0, 12, "Espera pelos garfos: média (barra) e maior (ponto)", INK, tam=11, peso=600))
    for k in range(0, xmax + 1, 20 if xmax <= 160 else 40):
        x = X(k)
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{topo - 4}" y2="{h - 22}" stroke="{GRID}" stroke-width="1"/>')
        s.append(txt(x, h - 9, f"{k} ms", MUTED, "middle", 9))
    for i, v in enumerate(V):
        y = topo + i * 40
        s.append(txt(esq - 8, y + 14, v, INK, "end", 11, 600))
        s.append(barra_h(X(0), y + 2, X(mW[v]) - X(0), 20, COR[v]))
        xm = X(maxM[v])
        s.append(f'<line x1="{X(mW[v]):.1f}" x2="{xm:.1f}" y1="{y + 12}" y2="{y + 12}" stroke="{INK2}" stroke-width="1"/>')
        s.append(f'<circle cx="{xm:.1f}" cy="{y + 12}" r="4.5" fill="{COR[v]}" stroke="#fcfcfb" stroke-width="2"/>')
        rot = f"média {fms(mW[v])} · maior {fms(maxM[v])}" if mW[v] > 0.05 else "sem disputa: espera ≈ 0"
        s.append(txt(X(0) + 2, y - 2, rot, INK, tam=9, peso=600))
    s.append(f'<line x1="{X(0):.1f}" x2="{X(0):.1f}" y1="{topo - 4}" y2="{h - 22}" stroke="{AXIS}" stroke-width="1"/>')
    s.append("</svg>")
    return "".join(s)


def grafico_gantt():
    w, esq, dir_ = 720, 92, 14
    janela = 600
    lin, painel_h, gap = 11, 5 * 11 + 8, 14
    X = lambda t: esq + t / janela * (w - esq - dir_)
    h = 22 + 3 * (painel_h + gap) + 18
    s = [svg_abre(w, h, "Quem está comendo ao longo do tempo")]
    s.append(txt(0, 12, f"Quem está comendo nos primeiros {janela} ms (1ª execução de cada versão)", INK, tam=11, peso=600))
    nomes = {"V0": "V0 · sequencial", "V2": "V2 · mesa global", "V3": "V3 · ordenação"}
    for p, v in enumerate(V):
        y0 = 24 + p * (painel_h + gap)
        s.append(txt(0, y0 + painel_h / 2 + 1, nomes[v], INK, tam=10, peso=600))
        for t in range(0, janela + 1, 100):
            s.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{y0}" y2="{y0 + 5 * lin}" stroke="{GRID}" stroke-width="1"/>')
        for f in range(5):
            yy = y0 + f * lin
            s.append(txt(esq - 6, yy + 8.5, f"F{f}", MUTED, "end", 8.5))
            for a, b in IC[v][f]:
                if a >= janela:
                    continue
                b = min(b, janela)
                s.append(f'<rect x="{X(a):.1f}" y="{yy + 1.5:.1f}" width="{max(X(b) - X(a) - 1, 1):.1f}" height="{lin - 3}" rx="2" fill="{COR[v]}"/>')
    yb = 24 + 3 * (painel_h + gap) - gap + 4
    for t in range(0, janela + 1, 100):
        s.append(txt(X(t), yb + 10, f"{t} ms", MUTED, "middle", 9))
    s.append("</svg>")
    return "".join(s)


def grafico_cenarios():
    w, h, esq, base_y, topo = 360, 210, 40, 170, 40
    ymax = 6000
    Y = lambda v: base_y - v / ymax * (base_y - topo)
    s = [svg_abre(w, h, "Tempo total por cenário de carga")]
    s.append(txt(0, 12, "Tempo total por cenário (pensar / comer)", INK, tam=11, peso=600))
    lx = esq
    for v in V:
        s.append(f'<rect x="{lx}" y="20" width="10" height="10" rx="2" fill="{COR[v]}"/>')
        s.append(txt(lx + 14, 29, v, INK2, tam=9.5))
        lx += 46
    for k in range(0, 7):
        y = Y(k * 1000)
        s.append(f'<line x1="{esq}" x2="{w - 6}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID if k else AXIS}" stroke-width="1"/>')
        s.append(txt(esq - 6, y + 3, f"{k} s", MUTED, "end", 9))
    largura_grupo = (w - esq - 10) / 3
    bw = 22
    for g, (c, p, cm, nome) in enumerate(CENARIOS):
        gx = esq + g * largura_grupo + (largura_grupo - 3 * bw - 2 * 3) / 2
        for i, v in enumerate(V):
            x = gx + i * (bw + 3)
            val = S[c][v]
            s.append(barra_v(x, base_y, bw, base_y - Y(val), COR[v]))
            s.append(txt(x + bw / 2, Y(val) - 3, br(val / 1000, 1), INK, "middle", 8.5, 600))
        cx = esq + g * largura_grupo + largura_grupo / 2
        s.append(txt(cx, base_y + 14, nome, INK, "middle", 9.5, 600))
        s.append(txt(cx, base_y + 26, f"{p} / {cm} ms", MUTED, "middle", 9))
    s.append("</svg>")
    return "".join(s)


def grafico_por_filosofo():
    w, h, esq, base_y, topo = 360, 200, 40, 160, 40
    ymax = math.ceil((max(PF[v][f][1] for v in ("V2", "V3") for f in FILS) + 5) / 20) * 20
    Y = lambda v: base_y - v / ymax * (base_y - topo)
    s = [svg_abre(w, h, "Espera por filósofo")]
    s.append(txt(0, 12, "Espera por filósofo: média (coluna) e maior (ponto)", INK, tam=11, peso=600))
    lx = esq
    for v in ("V2", "V3"):
        s.append(f'<rect x="{lx}" y="20" width="10" height="10" rx="2" fill="{COR[v]}"/>')
        s.append(txt(lx + 14, 29, v, INK2, tam=9.5))
        lx += 46
    for k in range(0, ymax + 1, 20 if ymax <= 160 else 40):
        y = Y(k)
        s.append(f'<line x1="{esq}" x2="{w - 6}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID if k else AXIS}" stroke-width="1"/>')
        s.append(txt(esq - 6, y + 3, f"{k}", MUTED, "end", 9))
    s.append(txt(8, topo - 6, "ms", MUTED, "start", 9))
    lg = (w - esq - 10) / 5
    bw = 20
    for i, f in enumerate(FILS):
        gx = esq + i * lg + (lg - 2 * bw - 4) / 2
        for j, v in enumerate(("V2", "V3")):
            x = gx + j * (bw + 4)
            media, maxima = PF[v][f]
            s.append(barra_v(x, base_y, bw, base_y - Y(media), COR[v]))
            s.append(f'<circle cx="{x + bw / 2:.1f}" cy="{Y(maxima):.1f}" r="4" fill="{COR[v]}" stroke="#fcfcfb" stroke-width="2"/>')
        s.append(txt(esq + i * lg + lg / 2, base_y + 14, f, INK, "middle", 10, 600))
    s.append("</svg>")
    return "".join(s)


def grafico_ciclo_v1():
    w, h, cx, cy, R = 300, 284, 150, 128, 92
    pos = {}
    for k in range(10):
        ang = math.radians(-90 + 36 * k)
        nome = f"g{k // 2}" if k % 2 == 0 else f"F{k // 2}"
        pos[nome] = (cx + R * math.cos(ang), cy + R * math.sin(ang))
    s = [svg_abre(w, h, "Grafo de espera da V1 travada")]
    s.append('<defs><marker id="seta-p" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
             f'<path d="M0 0L10 5L0 10z" fill="{INK2}"/></marker>'
             '<marker id="seta-e" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
             f'<path d="M0 0L10 5L0 10z" fill="{CRIT}"/></marker></defs>')

    def seta(a, b, ra, rb, cor, marca, tracejado):
        (x1, y1), (x2, y2) = pos[a], pos[b]
        d = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / d, (y2 - y1) / d
        return (f'<line x1="{x1 + ux * (ra + 3):.1f}" y1="{y1 + uy * (ra + 3):.1f}" x2="{x2 - ux * (rb + 4):.1f}" '
                f'y2="{y2 - uy * (rb + 4):.1f}" stroke="{cor}" stroke-width="1.6" {tracejado} marker-end="url(#{marca})"/>')

    for f, g in segura.items():
        s.append(seta(f"g{g}", f"F{f}", 12, 17, INK2, "seta-p", ""))
    for f, g in espera.items():
        s.append(seta(f"F{f}", f"g{g}", 17, 12, CRIT, "seta-e", 'stroke-dasharray="4 3"'))
    for i in range(5):
        x, y = pos[f"F{i}"]
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="17" fill="#fcfcfb" stroke="{INK2}" stroke-width="1.2"/>')
        s.append(txt(x, y + 4, f"F{i}", INK, "middle", 11, 600))
        x, y = pos[f"g{i}"]
        s.append(f'<rect x="{x - 12:.1f}" y="{y - 12:.1f}" width="24" height="24" rx="6" fill="#f0efec" stroke="{INK2}" stroke-width="1"/>')
        s.append(txt(x, y + 3.5, f"g{i}", INK, "middle", 9.5))
    s.append(txt(cx, cy - 2, "ciclo fechado", INK, "middle", 10, 600))
    s.append(txt(cx, cy + 12, "ninguém solta", INK2, "middle", 9))
    s.append(f'<line x1="10" x2="34" y1="{h - 22}" y2="{h - 22}" stroke="{INK2}" stroke-width="1.6" marker-end="url(#seta-p)"/>')
    s.append(txt(40, h - 18.5, "garfo → filósofo: está com ele", INK2, tam=9))
    s.append(f'<line x1="10" x2="34" y1="{h - 7}" y2="{h - 7}" stroke="{CRIT}" stroke-width="1.6" stroke-dasharray="4 3" marker-end="url(#seta-e)"/>')
    s.append(txt(40, h - 3.5, "filósofo → garfo: espera por ele", INK2, tam=9))
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# Montagem do HTML
# ---------------------------------------------------------------------------

def tabela_resultados():
    def cel(v, f):
        return f'<td class="num">{f(v)}</td>'

    def faixa(v):
        return f'{fs(mT[v])}<span class="sub">± {fms(sdT[v], 0)} · {fs(min(T[v]))}–{fs(max(T[v]))}</span>'

    linhas = [
        ("Tempo total", [faixa(v) for v in V], "não termina (deadlock)"),
        ("Mínimo teórico", [f"{fs(teorico(v), 1)}<span class='sub'>medido: +{pct(sobre[v], 1)}</span>" for v in V], "—"),
        ("Espera média pelos garfos", [f"{fms(mW[v])}<span class='sub'>± {fms(sdW[v])}</span>" for v in V], "infinita"),
        ("Maior espera observada", [fms(maxM[v]) for v in V], "infinita"),
        ("Máx. comendo ao mesmo tempo", [str(maxC[v]) for v in V], "0"),
        ("Concorrência média (comendo)", [br(conc[v], 2) for v in V], "0"),
        ("Ciclos por filósofo", ["20 em todas" if CIC[v] == {"20 20 20 20 20"} else ", ".join(CIC[v]) for v in V],
         "0 (trava no 1º ciclo)"),
    ]
    h = ['<table class="res"><thead><tr><th>Métrica</th><th class="c-v0">V0 · sequencial</th>'
         '<th class="c-v1">V1 · deadlock</th><th class="c-v2">V2 · mesa global</th><th class="c-v3">V3 · ordenação</th></tr></thead><tbody>']
    for nome, vals, v1 in linhas:
        h.append(f"<tr><th>{nome}</th><td class='num'>{vals[0]}</td><td class='num v1'>{v1}</td>"
                 f"<td class='num destaque'>{vals[1]}</td><td class='num'>{vals[2]}</td></tr>")
    h.append("</tbody></table>")
    return "".join(h)


def tabela_cenarios():
    h = ['<table class="mini cen"><thead><tr><th>Cenário</th><th>V0</th><th>V2</th><th>V3</th>'
         '<th>V2÷V3</th><th>Espera V2</th><th>Espera V3</th></tr></thead><tbody>']
    for c, p, cm, nome in CENARIOS:
        h.append(f"<tr><th>{nome}<span class='sub'>{p} / {cm} ms</span></th><td class='num'>{fs(S[c]['V0'])}</td>"
                 f"<td class='num'>{fs(S[c]['V2'])}</td><td class='num'>{fs(S[c]['V3'])}</td>"
                 f"<td class='num'>{fx(S[c]['V2'] / S[c]['V3'], 2)}</td><td class='num'>{fms(SW[c]['V2'])}</td>"
                 f"<td class='num'>{fms(SW[c]['V3'])}</td></tr>")
    h.append("</tbody></table>")
    return "".join(h)


def tabela_concorrencia():
    h = ['<table class="mini"><thead><tr><th>Versão</th><th>Máx. comendo junto</th><th>Concorrência média</th>'
         '<th>Ocupação dos lugares</th><th>Tempo total</th><th>Ganho sobre a V0</th></tr></thead><tbody>']
    for v in V:
        h.append(f"<tr><th>{v}</th><td class='num'>{maxC[v]}</td><td class='num'>{br(conc[v], 2)}</td>"
                 f"<td class='num'>{pct(conc[v] / maxC[v] * 100)}</td><td class='num'>{fs(mT[v])}</td>"
                 f"<td class='num'>{fx(mT['V0'] / mT[v], 2)}</td></tr>")
    h.append("</tbody></table>")
    return "".join(h)


def tabela_nucleos():
    h = ['<table class="mini"><thead><tr><th>Versão</th><th>GOMAXPROCS = 20 (padrão)</th><th>GOMAXPROCS = 1</th>'
         '<th>Diferença</th><th>Máx. comendo (1 núcleo)</th></tr></thead><tbody>']
    for v in V:
        h.append(f"<tr><th>{v}</th><td class='num'>{fs(mT[v])}</td><td class='num'>{fs(G1[v])}</td>"
                 f"<td class='num'>{'+' if G1[v] >= mT[v] else '−'}{pct(abs(G1[v] / mT[v] - 1) * 100, 1)}</td>"
                 f"<td class='num'>{G1C[v]}</td></tr>")
    h.append("</tbody></table>")
    return "".join(h)


def tabela_v1():
    h = ['<table class="mini"><thead><tr><th>Filósofo</th><th>Segura</th><th>Espera</th><th>Quem tem o garfo esperado</th></tr></thead><tbody>']
    for f in sorted(segura):
        g = espera[f]
        h.append(f"<tr><th>F{f}</th><td>g{segura[f]}</td><td>g{g}</td><td>F{dono[g]}"
                 f"{' (fecha o ciclo)' if f == max(segura) else ''}</td></tr>")
    h.append("</tbody></table>")
    return "".join(h)


def montar():
    # trechos de terminal
    v1_linhas = saida["V1"].splitlines()
    i_fatal = next(i for i, l in enumerate(v1_linhas) if l.startswith("fatal error"))
    i_g1 = next(i for i, l in enumerate(v1_linhas) if l.startswith("goroutine 1 "))
    i_gm = next(i for i, l in enumerate(v1_linhas) if "[sync.Mutex.Lock]" in l)
    i_pg = next(i for i in range(i_gm, len(v1_linhas)) if v1_linhas[i].startswith("main.pegarGarfos"))
    curto = lambda l: re.sub(r"C:/Users/.*?/fppd-t1-filosofos/", ".../", l)
    term_v1 = (v1_linhas[:i_fatal + 1] + [""] + [curto(l) for l in v1_linhas[i_g1:i_g1 + 2]] + ["..."]
               + [v1_linhas[i_gm]] + [curto(l) for l in v1_linhas[i_pg:i_pg + 2]] + ["..."])
    term_v1 = [l for l in term_v1 if l.strip() and not l.startswith("P = ") and not l.startswith("Cada filósofo")]
    v3_linhas = saida["V3"].splitlines()
    i_lt = next(i for i, l in enumerate(v3_linhas) if "instante" in l)
    term_v3 = v3_linhas[:3] + v3_linhas[i_lt - 1:i_lt + 22] + ["..."]

    cod_v0 = codigo(extrair("v0-sequencial", "jantar", False), "v0-sequencial/main.go · jantar (laço sequencial)")
    cod_ciclo = codigo(extrair("v3-ordenacao", "umCiclo"), "umCiclo · igual nas quatro versões")
    cod_v1 = codigo(extrair("v1-deadlock", "pegarGarfos", False), "v1-deadlock/main.go · pegarGarfos")
    cod_v2 = codigo(extrair_trecho("v2-mesa", r"^var garfos", 2) + "\n\n" + extrair("v2-mesa", "pegarGarfos", False)
                    + "\n\n" + extrair("v2-mesa", "soltarGarfos", False), "v2-mesa/main.go · mesa global")
    cod_v3 = codigo(extrair("v3-ordenacao", "pegarGarfos", False), "v3-ordenacao/main.go · pegarGarfos")
    cod_jantar = codigo(extrair("v3-ordenacao", "jantar", False), "jantar · uma goroutine por filósofo (V1, V2, V3)")
    cod_metr = codigo(extrair("v3-ordenacao", "comecouComer", False) + "\n\n" + extrair("v3-ordenacao", "terminouComer", False),
                      "métricas · contagem de quem está comendo")

    for nome, svg in (("tempo_total", grafico_tempo_total()), ("espera", grafico_espera()), ("gantt", grafico_gantt()),
                      ("cenarios", grafico_cenarios()), ("espera_por_filosofo", grafico_por_filosofo()),
                      ("ciclo_v1", grafico_ciclo_v1())):
        (FIG / f"{nome}.svg").write_text(svg, encoding="utf-8")
    fig = lambda n: (FIG / f"{n}.svg").read_text(encoding="utf-8")

    pf3 = PF["V3"]
    pf2 = PF["V2"]
    f3_media = sorted(pf3, key=lambda f: pf3[f][0])
    p_base, p_pouca, p_muita = "base", "pouca-disputa", "muita-disputa"

    corpo = f"""
<section class="pagina p1">
  <header class="capa">
    <div class="disciplina">FPPD · Fundamentos de Processamento Paralelo e Distribuído · Trabalho 1</div>
    <h1>Concorrência e Sincronização: o Problema dos Filósofos Jantando</h1>
    <div class="trio"><b>Grupo:</b> Eduardo Pacheco Lobo · Igor Xavier Nunes · Rodrigo Fehlauer Lauermann</div>
    <div class="repo"><b>Código:</b> <a href="{REPO}">{REPO.replace("https://", "")}</a> · Go 1.27 · outubro de 2026</div>
  </header>

  <p class="lead">Implementamos e medimos quatro versões do problema em Go. Todas usam os mesmos parâmetros
  (5 filósofos, 20 ciclos, pensar {PENSAR} ms e comer {COMER} ms, na proporção 2:3 do <code>filo_seq.go</code> de referência)
  e o mesmo esqueleto de ciclo: <i>pensar → pegar garfos → comer → soltar garfos</i>. Entre V1, V2 e V3 só mudam as funções
  <code>pegarGarfos</code> e <code>soltarGarfos</code>, então qualquer diferença medida vem da estratégia de sincronização.</p>

  <h2>1. Soluções e mecanismos de sincronização</h2>
  <table class="solucoes">
    <thead><tr><th>Versão</th><th>Como funciona</th><th>Mecanismos (Go)</th><th>Deadlock?</th></tr></thead>
    <tbody>
      <tr><th class="c-v0">V0<br><span>sequencial</span></th>
          <td>Um laço executa os filósofos um depois do outro, ciclo a ciclo. É a versão do professor com 20 ciclos e tempos em ms.
          Serve de linha de base (pior caso).</td>
          <td>Nenhum: não há disputa por garfos.</td><td>Impossível.</td></tr>
      <tr><th class="c-v1">V1<br><span>ingênua</span></th>
          <td>Uma goroutine por filósofo; cada garfo é um mutex. Todos pegam o garfo esquerdo (<code>i</code>) e depois o direito
          (<code>(i+1)%5</code>). Um atraso de 10 ms entre os dois <code>Lock</code> torna o deadlock reproduzível na demonstração.</td>
          <td><code>go</code>, <code>sync.Mutex</code> por garfo, <code>sync.WaitGroup</code>.</td>
          <td class="sim">Sim: as 4 condições de Coffman estão presentes.</td></tr>
      <tr><th class="c-v2">V2<br><span>mesa global</span></th>
          <td>A V1 (sem o atraso) com um mutex global, a "mesa", trancado do momento em que o filósofo vai pegar os garfos até
          soltá-los. Só um filósofo por vez pega, come e solta.</td>
          <td>Mutex global de granularidade grossa + mutex por garfo.</td>
          <td>Não: só um disputa garfos por vez, logo não há espera circular.</td></tr>
      <tr><th class="c-v3">V3<br><span>ordenação</span></th>
          <td>A V1 (sem o atraso) com uma regra: pegar sempre o garfo de <b>menor número</b> primeiro. Só o F4, que usa g4 e g0,
          muda de comportamento (pega g0 antes de g4).</td>
          <td>Mutex por garfo (granularidade fina) + ordem global de aquisição.</td>
          <td>Não: a ordem global impede que o ciclo de espera se feche.</td></tr>
    </tbody>
  </table>

  <h2>2. Análise comparativa</h2>
  <div class="tiles">
    <div class="tile"><div class="val">{fx(mT['V0'] / mT['V3'])}</div><div class="lab">mais rápida: V3 em relação à V0
      ({fs(mT['V3'])} contra {fs(mT['V0'])})</div></div>
    <div class="tile"><div class="val">{fx(mW['V2'] / mW['V3'])}</div><div class="lab">mais espera pelos garfos na V2 do que na V3
      ({fms(mW['V2'], 0)} contra {fms(mW['V3'], 0)})</div></div>
    <div class="tile"><div class="val">{dl_n['10']}/{dl_tot['10']}</div><div class="lab">execuções da V1 em deadlock com o atraso
      ({dl_n['0']}/{dl_tot['0']} sem ele)</div></div>
  </div>
  <p><b>Corretude.</b> A V1 trava: na execução oficial os cinco filósofos pegaram o garfo esquerdo
  {f"em {fms(min(t_pegou))}" if min(t_pegou) == max(t_pegou) else f"entre {fms(min(t_pegou))} e {fms(max(t_pegou))}"}, ficaram esperando o direito, e o runtime do Go encerrou o programa com
  <code>fatal error: all goroutines are asleep - deadlock!</code>. V2 e V3 completaram os 20 ciclos de cada filósofo nas
  {len(concorrentes_ok)} execuções feitas (todos os cenários).</p>
  <p><b>Desempenho.</b> Entre as versões corretas, a V3 foi a mais rápida ({fs(mT['V3'])}), {fx(mT['V2'] / mT['V3'], 2)}
  mais rápida que a V2 ({fs(mT['V2'])}) e {fx(mT['V0'] / mT['V3'], 2)} mais rápida que a V0 ({fs(mT['V0'])}). A V2 é correta, mas
  serializa as refeições: nunca houve mais de {maxC['V2']} filósofo comendo e a espera média foi de {fms(mW['V2'])}. Mesmo assim
  ela supera a V0, porque <i>pensar</i> continua em paralelo: a sincronização excessiva só custa na parte que ela serializa.
  A V3 atingiu {maxC['V3']} filósofos comendo ao mesmo tempo, o máximo possível com 5 garfos.</p>
  <p><b>Teoria × medição.</b> Os tempos ficaram próximos dos mínimos teóricos (V0: 100 × 50 ms = 5 s; V2: 100 refeições
  × 30 ms em fila = 3 s; V3: duas refeições por vez = 1,5 s), com sobrecusto de {pct(sobre['V0'], 1)}, {pct(sobre['V2'], 1)} e
  {pct(sobre['V3'], 1)}, respectivamente. A dispersão foi pequena (desvio padrão de {fms(sdT['V0'], 0)}, {fms(sdT['V2'], 0)}
  e {fms(sdT['V3'], 0)} em 30 execuções).</p>
  <p><b>Outros achados</b> (seção 4):</p>
  <ul class="achados">
    <li><b>A carga decide o custo da V2:</b> com pouca disputa ela leva só {fx(S['pouca-disputa']['V2'] / S['pouca-disputa']['V3'], 2)}
    o tempo da V3; com muita disputa, {fx(S['muita-disputa']['V2'] / S['muita-disputa']['V3'], 2)}.</li>
    <li><b>A largada é o momento crítico:</b> sem o atraso, a V1 travou em {dl_n['0']} de {dl_tot['0']} execuções, todas no primeiro
    ciclo; na V3, a largada forma uma corrente de espera e o primeiro par só come junto em {fms(t_par_v3)}.</li>
    <li><b>Concorrência não é paralelismo:</b> com um único núcleo (<code>GOMAXPROCS=1</code>) nenhuma versão ficou mais lenta,
    porque o gargalo são os garfos, não a CPU.</li>
  </ul>
</section>

<section class="pagina p2">
  <h2>3. Resultados experimentais</h2>
  <p class="nota topo">Cenário base: pensar {PENSAR} ms, comer {COMER} ms, 20 ciclos. V0, V2 e V3: média de {N['V2']} execuções
  (6 rodadas do programa × 5 execuções); abaixo do valor, desvio padrão e faixa mín–máx. A V1 é analisada à parte porque não termina.
  Espera = tempo entre pedir e obter os dois garfos. Comendo ao mesmo tempo = contador protegido por um mutex usado só para medir.
  Concorrência média = 100 refeições × 30 ms ÷ tempo total.</p>
  {tabela_resultados()}
  <div class="graficos">
    <figure>{fig('tempo_total')}<figcaption><b>Figura 1.</b> Barra: média; traço preto: faixa mín–máx;
      tracejado: mínimo teórico.</figcaption></figure>
    <figure>{fig('espera')}<figcaption><b>Figura 2.</b> A V2 tem a maior espera média; a maior espera isolada foi na V3, na largada
      do jantar (seção 4.8). Na V0 ninguém espera.</figcaption></figure>
  </div>
  <div class="prints">
    <figure>{terminal("go run ./v1-deadlock", term_v1)}
      <figcaption><b>Figura 3.</b> Evidência do deadlock da V1 (saída real, trecho): cada filósofo pega o garfo esquerdo e fica
      tentando pegar o direito; o runtime detecta que todas as goroutines estão bloqueadas. As outras quatro goroutines de filósofo
      aparecem iguais, bloqueadas em <code>sync.Mutex.Lock</code> na linha {linha_lock}.</figcaption></figure>
    <figure>{terminal("go run ./v3-ordenacao", term_v3)}
      <figcaption><b>Figura 4.</b> Linha do tempo da V3 (saída real, trecho). Cada coluna é um filósofo; P = pensando, C = comendo.
      Na largada só o F{primeiro_a_comer_v3} come (os outros formam uma corrente de espera); a partir de {fms(t_par_v3)} duas
      refeições começam no mesmo instante.</figcaption></figure>
  </div>
</section>

<section class="analise">
  <h2>4. Análise dos resultados</h2>
  <p>As respostas abaixo seguem as 12 questões propostas no enunciado (4.1 a 4.12) e acrescentam quatro análises que os dados
  permitiram (4.13 a 4.16). Os números vêm do cenário base, salvo indicação.</p>

  <h3>4.1 Como funciona cada solução?</h3>
  <p>As quatro versões compartilham a função <code>umCiclo</code> (Apêndice A): o filósofo pensa (<code>time.Sleep</code> de
  {PENSAR} ms), mede o tempo que leva para obter os garfos, come ({COMER} ms), solta os garfos e conta o ciclo.</p>
  <ul>
    <li><b>V0:</b> dois laços aninhados, ciclo de 1 a 20 e filósofo de 0 a 4. Como nada roda em paralelo, os garfos não precisam
    de proteção e <code>pegarGarfos</code> é vazia. O tempo é a soma de tudo: 20 × 5 × 50 ms = 5 s.</li>
    <li><b>V1:</b> o <code>main</code> cria uma goroutine por filósofo e espera todas com um <code>sync.WaitGroup</code>.
    <code>pegarGarfos</code> faz <code>Lock</code> no garfo esquerdo e depois no direito.</li>
    <li><b>V2:</b> igual à V1, mas <code>pegarGarfos</code> começa com <code>mesa.Lock()</code> e <code>soltarGarfos</code> termina com
    <code>mesa.Unlock()</code>. Do pedido dos garfos até a devolução, o filósofo tem a mesa inteira só para ele.</li>
    <li><b>V3:</b> igual à V1, mas antes dos <code>Lock</code> os dois índices são ordenados. F0 a F3 já pegavam o menor primeiro;
    o F4, cujos garfos são g4 e g0, passa a pegar g0 primeiro. Essa assimetria é toda a diferença.</li>
  </ul>

  <h3>4.2 Quais mecanismos de sincronização são utilizados?</h3>
  <ul>
    <li><b>Exclusão mútua por mutex</b> (V1, V2, V3): cada garfo é um recurso não compartilhável protegido por um lock.</li>
    <li><b>Lock global de granularidade grossa</b> (V2): um único mutex protege a mesa inteira, transformando a seção de pegar,
    comer e soltar em uma seção crítica única.</li>
    <li><b>Ordenação de recursos</b> (V3): não é uma primitiva, é um protocolo de uso dos mutexes. Todos adquirem os locks na mesma
    ordem global.</li>
    <li><b>Espera pelo término</b> (V1, V2, V3): <code>sync.WaitGroup</code> faz o <code>main</code> aguardar os cinco filósofos.</li>
    <li><b>Medição sem interferência:</b> as esperas e ciclos de cada filósofo ficam em posições de vetor só dele (sem lock);
    só o contador de "comendo agora" é compartilhado e usa um mutex próprio, fora da estratégia avaliada.</li>
  </ul>

  <h3>4.3 Como esses mecanismos são implementados em Go?</h3>
  <ul>
    <li><b>Goroutines:</b> tarefas leves criadas com <code>go f()</code>. O runtime as distribui entre threads do sistema
    (modelo M:N); nesta máquina, <code>GOMAXPROCS</code> = 20. Uma goroutine em <code>time.Sleep</code> ou bloqueada num mutex é
    estacionada e não consome CPU.</li>
    <li><b><code>sync.Mutex</code>:</b> <code>Lock()</code> bloqueia se o mutex estiver ocupado; <code>Unlock()</code> libera e acorda
    um interessado. O valor zero já é um mutex livre. Ele <i>não</i> é reentrante e não tem dono: nenhuma goroutine consegue tomá-lo
    de outra (é a "ausência de preempção"). Por padrão não é FIFO, mas entra em <i>modo starvation</i> quando alguém espera mais de
    1 ms e passa a atender por ordem de chegada.</li>
    <li><b><code>sync.WaitGroup</code>:</b> contador com <code>Add</code>, <code>Done</code> e <code>Wait</code>.</li>
    <li><b>Detector de deadlock do runtime:</b> se todas as goroutines estão bloqueadas, o programa é abortado com a pilha de cada uma
    (Figura 3). Ele só funciona quando <i>todas</i> estão paradas.</li>
    <li>Go não tem semáforo nem monitor nativos (seriam feitos com canal com buffer e com <code>sync.Cond</code>); nenhuma das
    estratégias escolhidas precisou deles.</li>
  </ul>
  {cod_v1}

  <h3>4.4 Por que ocorre deadlock na V1?</h3>
  <p>Porque as quatro condições de Coffman valem ao mesmo tempo, e a ordem "esquerdo, depois direito", igual para todos, fecha o
  círculo. A saída oficial (Figura 3) mostra o estado final:</p>
  <div class="lado">
    <div>{tabela_v1()}
      <ol class="coffman">
        <li><b>Exclusão mútua:</b> cada garfo é um <code>sync.Mutex</code>; só um filósofo o segura.</li>
        <li><b>Posse e espera:</b> cada filósofo segura o garfo esquerdo enquanto espera o direito.</li>
        <li><b>Ausência de preempção:</b> nenhuma goroutine pode tirar o mutex de outra.</li>
        <li><b>Espera circular:</b> F0 espera F1, que espera F2, … e F4 espera F0.</li>
      </ol>
    </div>
    <figure>{fig('ciclo_v1')}<figcaption><b>Figura 5.</b> Grafo de espera da execução oficial: o ciclo fechado é o deadlock.</figcaption></figure>
  </div>
  <p>O atraso de 10 ms entre os dois <code>Lock</code> não cria o defeito: ele apenas alarga a janela em que todos seguram o garfo
  esquerdo. Sem o atraso, o mesmo código travou em <b>{dl_n['0']} de {dl_tot['0']}</b> execuções (seção 4.13): o defeito existe
  sempre, mas só se manifesta quando o escalonador produz a intercalação ruim.</p>

  <h3>4.5 Como V2 e V3 evitam deadlock?</h3>
  <p>As duas quebram a <b>espera circular</b>, por caminhos diferentes.</p>
  <ul>
    <li><b>V2:</b> só o dono da mesa pode segurar ou esperar garfos. Um ciclo de espera precisa de pelo menos dois filósofos segurando
    recursos, e isso nunca acontece. Na prática, os mutexes dos garfos ficam até redundantes.</li>
    <li><b>V3:</b> suponha um ciclo de espera. Cada filósofo nele segura um garfo e espera outro de número <i>maior</i> (é a regra).
    Percorrendo o ciclo, os números teriam de crescer a cada passo e voltar ao início, o que é impossível. Logo não há ciclo nem
    deadlock, e sem limitar quem não disputa garfos.</li>
  </ul>
  <p>Evidência: as {len(concorrentes_ok)} execuções de V2 e V3 (três cenários de carga e com um único núcleo) terminaram com
  20 ciclos para cada filósofo.</p>
  <div class="dois-codigos">{cod_v2}{cod_v3}</div>

  <h3>4.6 Existe possibilidade de starvation? Justifique.</h3>
  <p><b>Na V0, não:</b> a ordem é fixa. <b>Na V2 e na V3, sim em teoria</b>, porque nenhuma das duas garante a vez de cada filósofo:
  um mutex não é uma fila, e na V3 dois vizinhos podem se alternar e deixar o do meio sempre encontrando um garfo ocupado.
  <b>Na prática, não observamos starvation:</b> todos completaram os 20 ciclos e a espera foi parecida entre os filósofos
  (Figura 6). Na V2, as médias por filósofo ficaram entre {fms(min(pf2[f][0] for f in FILS))} e
  {fms(max(pf2[f][0] for f in FILS))}; o modo starvation do mutex do Go aproxima a mesa de uma fila. Na V3, ficaram entre
  {fms(pf3[f3_media[0]][0])} ({f3_media[0]}) e {fms(pf3[f3_media[-1]][0])} ({f3_media[-1]}), e a maior espera de um filósofo foi
  {fms(max(pf3[f][1] for f in FILS))}, cerca de {br(max(pf3[f][1] for f in FILS) / COMER, 1)} refeições. F0 e F4 esperam um pouco
  mais porque os dois começam pelo mesmo garfo, g0, efeito direto da regra de ordenação. A maior espera isolada da V3 não é
  starvation em regime: é a espera da largada do jantar, explicada em 4.8 e 4.9.</p>
  <div class="lado">
    <figure>{fig('espera_por_filosofo')}<figcaption><b>Figura 6.</b> Espera por filósofo (média de 6 rodadas; ponto = maior
    espera). Nenhum filósofo foi sistematicamente preterido.</figcaption></figure>
    <div><p>Com só 20 ciclos e tempos fixos, a carga é regular e favorece a justiça. Uma garantia formal exigiria um mecanismo com
    ordem de chegada explícita, como um "garçom" que atende por fila de senhas.</p>
    <p>Na V2, as colunas são praticamente iguais: a mesa funciona como uma fila. Na V3, F1, F2 e F3 esperam menos que F0 e F4, os dois
    que disputam o g0 como primeiro garfo. O ponto alto do F4 é a espera da largada.</p></div>
  </div>

  <h3>4.7 Qual solução apresentou maior tempo total de execução?</h3>
  <p>Desconsiderando a V1, que nunca termina, a <b>V0</b>: {fs(mT['V0'])} em média, contra 5 s teóricos. Era o esperado, porque
  ela soma todos os tempos de pensar e comer. Entre as concorrentes, a <b>V2</b> foi a mais lenta ({fs(mT['V2'])}),
  {fx(mT['V2'] / mT['V3'], 2)} o tempo da V3.</p>

  <h3>4.8 Qual solução apresentou maior tempo de espera pelos recursos?</h3>
  <p><b>Na média, a V2:</b> {fms(mW['V2'])}, contra {fms(mW['V3'])} na V3 (V0: zero; V1: infinita). O número da V2 bate com um
  cálculo simples: como a mesa atende um por vez, em regime cada filósofo volta à mesa a cada 5 × 30 = 150 ms; descontando 30 ms
  comendo e 20 ms pensando, sobram cerca de 100 ms de espera. A maior espera da V2 ({fms(maxM['V2'])}) corresponde a aguardar os
  outros quatro comerem: 4 × 30 = 120 ms.</p>
  <p><b>Na maior espera isolada, a V3:</b> {fms(maxM['V3'])}. Ela vem da largada: na execução oficial, o F{f_largada} só comeu pela
  primeira vez {fms(espera_largada[f_largada])} depois de ficar com fome, preso na corrente de espera descrita em 4.9. Passada a
  largada, as esperas da V3 caem para a faixa de 20 a 30 ms. Em resumo: a V2 faz todos esperarem muito o tempo todo; a V3 faz
  poucos esperarem bastante, e só no começo.</p>

  <h3>4.9 Quantos filósofos conseguiram comer simultaneamente em cada solução?</h3>
  <p>V0: 1 · V1: 0 (trava antes da primeira refeição) · V2: {maxC['V2']} · V3: {maxC['V3']}. Dois é o limite teórico: cada refeição
  ocupa 2 dos 5 garfos e dois vizinhos nunca comem juntos. A Figura 7 mostra a diferença no tempo: na V2 as refeições formam uma
  fila contínua, sem sobreposição; na V3, passada a largada, aparecem quase sempre dois filósofos não vizinhos comendo em paralelo.</p>
  <figure>{fig('gantt')}<figcaption><b>Figura 7.</b> Refeições ao longo do tempo, reconstruídas da linha do tempo impressa pelos
  programas. A V0 percorre um filósofo por vez com pausas para pensar; a V2 elimina as pausas mas não a fila; a V3 forma pares
  depois de uma largada em fila.</figcaption></figure>
  <p><b>Um efeito que só a linha do tempo mostra.</b> Como todos começam a pensar no mesmo instante, todos ficam com fome juntos.
  Na V3, F0 pega g0, F1 pega g1, F2 pega g2 e F3 pega g3; o F4 tenta g0 (seu primeiro garfo pela regra) e fica bloqueado sem
  segurar nada. Assim o F3 consegue g4 e come sozinho, enquanto F2, F1 e F0 formam uma <b>corrente de espera</b>, cada um segurando
  o garfo de que o vizinho precisa. A corrente se desfaz um elo por vez, e só em {fms(t_par_v3)} aparece o primeiro par comendo junto.
  Ou seja: a ordenação elimina o <i>ciclo</i>, mas não a <i>posse e espera</i>, que ainda pode serializar filósofos por um tempo.
  É por isso que a V3 fica um pouco acima do 1,5 s teórico e varia mais entre execuções.</p>

  <h3>4.10 Qual foi o impacto da sincronização excessiva da V2?</h3>
  <p>No cenário base, a mesa global deixou o programa {pct((mT['V2'] / mT['V3'] - 1) * 100)} mais lento que a V3, multiplicou a espera
  média por {br(mW['V2'] / mW['V3'], 1)} e reduziu a concorrência máxima de 2 para 1. O impacto, porém, depende da carga. Rodamos
  mais dois cenários mantendo pensar + comer = 50 ms (por isso a V0 leva sempre cerca de 5 s):</p>
  <div class="lado lado-cen">
    <figure>{fig('cenarios')}<figcaption><b>Figura 8.</b> Tempo total médio (5 execuções por cenário; base: 30).</figcaption></figure>
    <div>{tabela_cenarios()}
      <p class="nota">Com <b>pouca disputa</b> (comer é curto), a mesa quase nunca está ocupada e a V2 fica perto da V3
      ({fx(S[p_pouca]['V2'] / S[p_pouca]['V3'], 2)}). Com <b>muita disputa</b>, a fila da mesa domina: a V2 leva
      {fs(S[p_muita]['V2'])}, mais perto da V0 ({fs(S[p_muita]['V0'])}) do que da V3 ({fs(S[p_muita]['V3'])}).</p></div>
  </div>
  <p>Conclusão: o custo da sincronização excessiva é proporcional ao quanto a seção serializada pesa no trabalho total. Ele é baixo
  quando a seção crítica é curta e cresce até anular o paralelismo quando ela domina.</p>

  <h3>4.11 A solução com maior sincronização foi necessariamente a de melhor desempenho?</h3>
  <p><b>Não, foi o contrário.</b> V2 e V3 são igualmente corretas (nenhuma trava), mas a V2 sincroniza mais: tranca três mutexes por
  refeição em vez de dois, e um deles bloqueia todos os filósofos, inclusive os que não disputam garfo nenhum. O resultado foi
  {fx(mT['V2'] / mT['V3'], 2)} mais tempo e {fx(mW['V2'] / mW['V3'], 1)} mais espera. Sincronização garante corretude, mas cada
  lock a mais é uma fila a mais. A melhor solução sincroniza só o necessário: protege cada garfo (granularidade fina) e evita o
  deadlock com uma regra de ordem, sem bloquear quem não compete.</p>

  <h3>4.12 Qual é a relação entre o grau de concorrência observado e o tempo total de execução?</h3>
  <p>Inversa. O trabalho de comer é fixo: 100 refeições de 30 ms, ou 3.000 ms. O que muda entre as versões é quantas refeições
  acontecem ao mesmo tempo. A <b>concorrência média</b> (3.000 ms divididos pelo tempo do jantar) é o número médio de filósofos
  comendo a cada instante; a <b>ocupação</b> compara esse número com o máximo que a versão permite.</p>
  {tabela_concorrencia()}
  <p>Duas leituras saem da tabela. Primeiro, V2 e V3 mantêm seus "lugares" à mesa quase sempre ocupados
  ({pct(conc['V2'] / maxC['V2'] * 100)} e {pct(conc['V3'] / maxC['V3'] * 100)}): a diferença de tempo entre elas vem
  inteiramente de quantos lugares existem, 1 ou 2. Dobrar a concorrência permitida reduziu o tempo quase à metade. Segundo, a V0
  tem concorrência abaixo de 1 porque, enquanto um filósofo pensa, ninguém come. O ganho tem dois tetos: o físico (no máximo 2
  comendo ao mesmo tempo) e o de cada filósofo, que precisa de pelo menos 20 × (20 + 30) ms = 1 s para os próprios ciclos. No
  cenário de pouca disputa é esse segundo teto que manda, e por isso V2 e V3 se aproximam (Figura 8).</p>

  <h3>4.13 O deadlock da V1 acontece sem o atraso artificial?</h3>
  <p>Sim, em parte das execuções. Sem o atraso, a V1 travou em <b>{dl_n['0']} de {dl_tot['0']}</b> execuções
  ({pct(dl_n['0'] / dl_tot['0'] * 100)}); com o atraso, em {dl_n['10']} de {dl_tot['10']}. A frequência também oscila entre baterias:
  num teste exploratório anterior, a mesma versão sem atraso travou em apenas 2 de 20 execuções.
  {"Em todas as execuções que travaram, o deadlock aconteceu no primeiro ciclo, antes de qualquer refeição. É o momento de maior risco: como todos começam a pensar juntos e pensam pelo mesmo tempo, todos ficam com fome no mesmo instante e pegam o garfo esquerdo quase simultaneamente. Depois da largada, as refeições se desencontram e a intercalação fatal fica improvável." if dl_ref and max(dl_ref) == 0 else (f"Nas execuções que travaram, o deadlock veio depois de {dl_ref[0]} a {dl_ref[-1]} refeições." if dl_ref else "")}</p>
  <p>É o comportamento típico de defeitos de concorrência: o programa passa em vários testes e falha de repente, conforme a ordem
  escolhida pelo escalonador. Por isso a análise das quatro condições é mais confiável que "testar e ver se trava".</p>

  <h3>4.14 Mais núcleos deixam o jantar mais rápido?</h3>
  {tabela_nucleos()}
  <p>Não. Com <code>GOMAXPROCS=1</code>, um único núcleo executa todas as goroutines e nenhuma versão ficou mais lenta; a V3
  manteve {G1C['V3']} filósofos comendo ao mesmo tempo. Isso acontece porque pensar e comer são <code>Sleep</code>: as goroutines
  passam quase todo o tempo bloqueadas, sem usar CPU. O gargalo é a disputa pelos garfos, não o processador. É a diferença entre
  concorrência (estruturar o programa em tarefas independentes) e paralelismo (executá-las ao mesmo tempo em núcleos distintos).</p>
  <p>A V3 com um núcleo foi até um pouco mais rápida e bem mais estável (desvio padrão de {fms(sdG1['V3'])} contra {fms(sdT['V3'])}).
  Uma explicação provável é que, com um só núcleo, as goroutines acordam numa ordem mais regular e a corrente de espera da largada se
  desfaz sempre do mesmo jeito. Como esse teste teve 5 execuções por versão, a diferença deve ser lida como indicativa.</p>

  <h3>4.15 As medições são confiáveis?</h3>
  <ul>
    <li><b>Repetição:</b> 30 execuções por versão no cenário base (o enunciado pede 5), com desvio padrão de {fms(sdT['V0'], 0)} (V0),
    {fms(sdT['V2'], 0)} (V2) e {fms(sdT['V3'], 0)} (V3). A V3 varia mais porque o pareamento de quem come junto muda a cada execução.</li>
    <li><b>Sobrecusto previsível:</b> a V0 levou {fms(mT['V0'] - 5000, 0)} a mais que os 5 s teóricos, cerca de
    {fms((mT['V0'] - 5000) / 200, 2)} por <code>Sleep</code> (são 200), o custo de acordar uma goroutine no Windows.</li>
    <li><b>Sem condições de corrida:</b> V0, V2 e V3 rodaram com o detector de corrida do Go (<code>go run -race</code>) sem nenhum
    alerta. Com <code>-race</code>, a V1 não aborta: o detector desativa a detecção automática de deadlock e o programa fica parado em
    silêncio, como aconteceria num sistema real.</li>
    <li><b>Impressão:</b> a linha do tempo só é impressa na 1ª execução de cada rodada. Na V0 e na V2 a diferença entre a 1ª
    execução e as outras foi desprezível ({'+' if d1['V0'] >= 0 else '−'}{fms(abs(d1['V0']))} e
    {'+' if d1['V2'] >= 0 else '−'}{fms(abs(d1['V2']))}). Na V3, a 1ª execução foi em média {fms(d1['V3'])} mais lenta, da ordem do
    próprio desvio padrão da versão ({fms(sdT['V3'])}); como só 6 das 30 execuções imprimem, o efeito na média da V3 é de cerca de
    {fms(d1['V3'] * 6 / 30, 0)}.</li>
    <li><b>Limitações:</b> uma única máquina e um único sistema operacional; tempos de pensar e comer fixos (sem aleatoriedade), o que
    torna o comportamento mais regular do que num sistema real.</li>
  </ul>

  <h3>4.16 Conclusão</h3>
  <p>Os dados confirmam a teoria em todos os pontos. A versão ingênua (V1) é concorrente mas incorreta: as quatro condições de Coffman
  produzem deadlock, às vezes raro, mas sempre possível. Resolver o deadlock com um lock global (V2) devolve a corretude ao preço da
  concorrência: o jantar vira uma fila, a espera é a maior de todas e o desempenho fica entre a versão sequencial e a ideal, mais
  perto da sequencial quanto maior a disputa. Resolver o mesmo problema quebrando só a espera circular (V3) mantém a granularidade fina,
  atinge o máximo teórico de dois filósofos comendo ao mesmo tempo e entrega o menor tempo ({fs(mT['V3'])}, {fx(mT['V0'] / mT['V3'], 1)}
  mais rápido que a V0). A lição central é que a quantidade de sincronização não mede a qualidade de uma solução: o melhor desempenho
  veio de sincronizar menos, mas no lugar certo.</p>

  <h2>5. Ambiente de execução e reprodução</h2>
  <table class="mini amb">
    <tbody>
      <tr><th>Linguagem</th><td>Go 1.27.0 (windows/amd64); módulo exige Go ≥ 1.22</td></tr>
      <tr><th>Sistema operacional</th><td>Windows 11 Home Single Language</td></tr>
      <tr><th>Processador</th><td>13th Gen Intel Core i7-13700H</td></tr>
      <tr><th>Núcleos</th><td>14 núcleos físicos, 20 lógicos (<code>runtime.NumCPU()</code> = 20, <code>GOMAXPROCS</code> = 20)</td></tr>
      <tr><th>Execução</th><td><code>go run ./v0-sequencial</code> · <code>go run ./v1-deadlock</code> · <code>go run ./v2-mesa</code> ·
        <code>go run ./v3-ordenacao</code> (na raiz do repositório)</td></tr>
      <tr><th>Compilação</th><td><code>go build -o v3.exe ./v3-ordenacao</code> (idem para as outras); verificação: <code>go vet ./...</code>,
        <code>gofmt -l .</code>, <code>go run -race</code></td></tr>
      <tr><th>Experimentos</th><td><code>py relatorio/experimentos.py</code> (gera <code>resultados/*.csv</code>) e
        <code>py relatorio/gerar_relatorio.py</code> (gera este PDF)</td></tr>
      <tr><th>Repositório</th><td><a href="{REPO}">{REPO}</a></td></tr>
    </tbody>
  </table>
</section>

<section class="apendice">
  <h2>Apêndice A · Código-fonte (trechos)</h2>
  <p class="nota">Código completo e formatado com <code>gofmt</code> no repositório. Os trechos abaixo são extraídos automaticamente dos
  arquivos <code>main.go</code>.</p>
  {cod_ciclo}
  {cod_v0}
  {cod_jantar}
  {cod_metr}
</section>
"""
    return corpo


CSS = """
@page { size: A4; margin: 12mm 13mm 13mm 13mm;
  @bottom-right { content: counter(page); font: 8pt 'Segoe UI', sans-serif; color: #898781; } }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: 'Segoe UI', system-ui, sans-serif; color: #1b1b1a; font-size: 9.4pt; line-height: 1.42; margin: 0; }
h1 { font-size: 17pt; line-height: 1.15; margin: 2mm 0 2mm; color: #0b0b0b; letter-spacing: -0.2pt; }
h2 { font-size: 12pt; margin: 3.2mm 0 1.6mm; color: #104281; border-bottom: 1px solid #e1e0d9; padding-bottom: 1mm; }
h3 { font-size: 10.2pt; margin: 4mm 0 1.2mm; color: #0b0b0b; break-after: avoid; }
p { margin: 0 0 1.8mm; }
ul, ol { margin: 0 0 2mm; padding-left: 5mm; }
li { margin-bottom: 0.8mm; }
code { font-family: 'Cascadia Mono', Consolas, monospace; font-size: 0.9em; background: #f0efec; padding: 0 2px; border-radius: 2px; }
a { color: #1c5cab; text-decoration: none; }
.pagina { break-after: page; }
.capa { border-left: 4px solid #2a78d6; padding: 1mm 0 1mm 4mm; margin-bottom: 3mm; }
.disciplina { font-size: 8.4pt; color: #52514e; text-transform: uppercase; letter-spacing: 0.4pt; }
.trio, .repo { font-size: 9pt; color: #1b1b1a; }
.lead { font-size: 9.6pt; }
table { border-collapse: collapse; width: 100%; }
.solucoes { font-size: 8.5pt; margin-bottom: 1.5mm; }
.solucoes th, .solucoes td { border-bottom: 1px solid #e1e0d9; padding: 1.3mm 1.6mm; vertical-align: top; text-align: left; }
.solucoes thead th { font-size: 7.8pt; color: #52514e; text-transform: uppercase; letter-spacing: 0.3pt; border-bottom: 1.5px solid #c3c2b7; }
.solucoes tbody th { width: 17mm; font-size: 10pt; }
.solucoes tbody th span { font-size: 7.6pt; font-weight: 400; color: #52514e; }
.solucoes td:nth-child(3) { width: 38mm; }
.solucoes td:nth-child(4) { width: 34mm; }
.sim { color: #b02a2a; font-weight: 600; }
.c-v0 { border-left: 3px solid #2a78d6 !important; }
.c-v1 { border-left: 3px solid #d03b3b !important; }
.c-v2 { border-left: 3px solid #eb6834 !important; }
.c-v3 { border-left: 3px solid #1baf7a !important; }
.nota { font-size: 8.2pt; color: #52514e; }
.nota.topo { margin-bottom: 2mm; }
.tiles { display: flex; gap: 3mm; margin: 1mm 0 2.5mm; }
.tile { flex: 1; border: 1px solid #e1e0d9; border-radius: 2mm; padding: 2mm 3mm; background: #fcfcfb; }
.tile .val { font-size: 17pt; font-weight: 650; color: #0b0b0b; line-height: 1.1; }
.tile .lab { font-size: 8pt; color: #52514e; }
.res { font-size: 8.3pt; margin-bottom: 2mm; }
.res th, .res td { border-bottom: 1px solid #e1e0d9; padding: 0.8mm 1.6mm; text-align: left; vertical-align: top; }
.res thead th { font-size: 7.8pt; border-bottom: 1.5px solid #c3c2b7; color: #0b0b0b; }
.res tbody th { font-weight: 600; color: #1b1b1a; width: 46mm; }
.res td.num { font-variant-numeric: tabular-nums; }
.res td.destaque { background: #fdf1ec; }
.res td.v1 { color: #8a2a2a; }
.sub { display: block; font-size: 7pt; color: #898781; }
.graficos { display: flex; gap: 5mm; margin-bottom: 1mm; }
.graficos figure { flex: 1; margin: 0; }
figure { margin: 2mm 0; break-inside: avoid; }
figcaption { font-size: 7.6pt; color: #52514e; margin-top: 0.8mm; line-height: 1.3; }
.prints { display: flex; gap: 4mm; align-items: flex-start; }
.prints figure { flex: 1; margin: 0; min-width: 0; }
.term { border-radius: 2mm; overflow: hidden; border: 1px solid #2c2c2a; background: #0c0c0c; }
.term-bar { background: #2b2b2b; padding: 1mm 2mm; display: flex; align-items: center; gap: 1.2mm; }
.term-bar .dot { width: 2.2mm; height: 2.2mm; border-radius: 50%; background: #5a5a5a; display: inline-block; }
.term-tit { color: #c8c8c8; font-size: 7pt; margin-left: 1.5mm; }
.term pre { margin: 0; padding: 1.8mm 2.2mm; color: #cccccc; font-family: 'Cascadia Mono', Consolas, monospace;
  font-size: 5.8pt; line-height: 1.24; white-space: pre-wrap; word-break: break-all; tab-size: 4; }
.term .prompt { color: #61d6d6; }
.codigo { margin: 2.5mm 0; border: 1px solid #e1e0d9; border-radius: 1.5mm; overflow: hidden; break-inside: avoid; }
.code-tit { background: #f0efec; font-size: 7.6pt; color: #52514e; padding: 0.8mm 2.5mm; font-family: 'Segoe UI', sans-serif; }
.codigo pre { tab-size: 4; -moz-tab-size: 4; margin: 0; padding: 2mm 2.5mm; font-family: 'Cascadia Mono', Consolas, monospace; font-size: 7.6pt;
  line-height: 1.35; background: #fbfbfa; white-space: pre-wrap; }
.dois-codigos { display: flex; gap: 3mm; }
.dois-codigos .codigo { flex: 1; min-width: 0; }
.lado { display: flex; gap: 5mm; align-items: flex-start; break-inside: avoid; }
.lado > * { flex: 1; min-width: 0; }
.mini { font-size: 8.3pt; margin: 1.5mm 0 2mm; break-inside: avoid; }
.mini th, .mini td { border-bottom: 1px solid #e1e0d9; padding: 0.9mm 1.6mm; text-align: left; }
.mini thead th { font-size: 7.6pt; color: #52514e; border-bottom: 1.5px solid #c3c2b7; }
.mini td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.cen { font-size: 7.9pt; }
.lado-cen > figure { flex: 0 0 44%; }
.achados { font-size: 9pt; }
.amb th { width: 34mm; }
.coffman { font-size: 8.6pt; margin-top: 2mm; }
.meia { width: 60%; }
.analise h2:first-child { margin-top: 0; }
.apendice { break-before: page; }
"""


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    estilo_codigo = FORMATADOR.get_style_defs(".highlight")
    corpo = montar()
    doc = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
           f'<title>FPPD T1 - Filósofos Jantando</title><style>{CSS}{estilo_codigo}</style></head><body>{corpo}</body></html>')
    html_path = SAIDA / "relatorio.html"
    html_path.write_text(doc, encoding="utf-8")
    pdf_path = SAIDA / "relatorio.pdf"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", html_path.as_uri()], check=True, capture_output=True)
    print("Gerado:", pdf_path)


if __name__ == "__main__":
    main()
