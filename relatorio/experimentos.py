"""Roda toda a bateria de experimentos do relatório e grava os dados em resultados/.

Uso (na raiz do repositório):  py relatorio/experimentos.py

O que é executado:
  1. Cenário base (pensar 20 ms, comer 30 ms), código exatamente como está no
     repositório: V0, V2 e V3 rodadas 6 vezes cada (6 x 5 = 30 execuções).
     A 1ª rodada de cada versão é a "oficial" e sua saída completa vai para
     resultados/<versao>.txt. A V1 roda uma vez (trava).
  2. Cenários de carga: as mesmas versões com outras durações de pensar/comer
     (a soma continua 50 ms, então a V0 leva o mesmo tempo nos três cenários).
     Só as duas constantes de tempo mudam, numa cópia temporária do código.
  3. GOMAXPROCS=1: cenário base com um único núcleo para o Go.
  4. V1 sem o atraso artificial (atrasoEntreGarfos = 0), 50 execuções, para
     medir com que frequência o deadlock acontece "sozinho"; e V1 com o atraso,
     10 execuções.
"""

import csv
import os
import pathlib
import re
import subprocess
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
RESULTADOS = RAIZ / "resultados"
VERSOES = {"V0": "v0-sequencial", "V1": "v1-deadlock", "V2": "v2-mesa", "V3": "v3-ordenacao"}
CENARIOS = {  # nome: (pensar ms, comer ms)
    "base": (20, 30),
    "pouca-disputa": (40, 10),
    "muita-disputa": (10, 40),
}
GO = "go"


def compilar(versao, pasta_tmp, pensar=20, comer=30, atraso=None):
    """Compila a versão. Sem mudanças de constantes, compila o próprio pacote do
    repositório; senão, uma cópia do main.go com só as constantes pedidas trocadas."""
    if (pensar, comer, atraso) == (20, 30, None):
        exe = pathlib.Path(pasta_tmp) / f"{versao}_repo.exe"
        subprocess.run([GO, "build", "-o", str(exe), "./" + VERSOES[versao]], cwd=RAIZ, check=True)
        return exe
    codigo = (RAIZ / VERSOES[versao] / "main.go").read_text(encoding="utf-8")
    codigo = re.sub(r"(tempoPensar\s*=\s*)20 \* time\.Millisecond", rf"\g<1>{pensar} * time.Millisecond", codigo)
    codigo = re.sub(r"(tempoComer\s*=\s*)30 \* time\.Millisecond", rf"\g<1>{comer} * time.Millisecond", codigo)
    if atraso is not None:
        codigo = re.sub(r"(atrasoEntreGarfos\s*=\s*)10 \* time\.Millisecond", rf"\g<1>{atraso} * time.Millisecond", codigo)
    nome = f"{versao}_{pensar}_{comer}_{atraso}"
    pasta = pathlib.Path(pasta_tmp) / nome
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "main.go").write_text(codigo, encoding="utf-8")
    exe = pasta / f"{nome}.exe"
    subprocess.run([GO, "build", "-o", str(exe), "main.go"], cwd=pasta, check=True)
    return exe


def executar(exe, gomaxprocs=None, timeout=600):
    env = dict(os.environ)
    if gomaxprocs:
        env["GOMAXPROCS"] = str(gomaxprocs)
    p = subprocess.run([str(exe)], capture_output=True, env=env, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", errors="replace")


def linhas_csv(saida, versao):
    """Extrai as linhas CSV impressas no final do programa."""
    regs = []
    for linha in saida.splitlines():
        if linha.startswith(versao + ","):
            v, ex, total, media, maxima, maxcom, ciclos = linha.split(",")
            regs.append({"execucao": int(ex), "tempo_total_ms": float(total), "espera_media_ms": float(media),
                         "espera_max_ms": float(maxima), "max_comendo": int(maxcom), "ciclos": ciclos})
    return regs


def espera_por_filosofo(saida):
    return [(int(m.group(1)), float(m.group(2)), float(m.group(3)))
            for m in re.finditer(r"F(\d): média\s+([\d.]+) ms \| máxima\s+([\d.]+) ms", saida)]


def main():
    RESULTADOS.mkdir(exist_ok=True)
    execucoes, por_filosofo, v1_freq = [], [], []

    with tempfile.TemporaryDirectory() as tmp:
        # 1 e 2: cenários (o base usa o código sem alterações de tempo)
        for cenario, (pensar, comer) in CENARIOS.items():
            rodadas = 6 if cenario == "base" else 1
            for versao in ("V0", "V2", "V3"):
                exe = compilar(versao, tmp, pensar, comer)
                for rodada in range(1, rodadas + 1):
                    print(f"[{cenario}] {versao} rodada {rodada}/{rodadas}", flush=True)
                    cod, saida = executar(exe)
                    if cenario == "base" and rodada == 1:
                        (RESULTADOS / f"{VERSOES[versao]}.txt").write_text(saida, encoding="utf-8")
                    for r in linhas_csv(saida, versao):
                        execucoes.append({"cenario": cenario, "pensar_ms": pensar, "comer_ms": comer,
                                          "gomaxprocs": "padrao", "versao": versao, "rodada": rodada, **r})
                    if cenario == "base":
                        for fid, media, maxima in espera_por_filosofo(saida):
                            por_filosofo.append({"versao": versao, "rodada": rodada, "filosofo": f"F{fid}",
                                                 "espera_media_ms": media, "espera_max_ms": maxima})

        # 3: um único núcleo
        for versao in ("V0", "V2", "V3"):
            exe = compilar(versao, tmp)
            print(f"[GOMAXPROCS=1] {versao}", flush=True)
            cod, saida = executar(exe, gomaxprocs=1)
            for r in linhas_csv(saida, versao):
                execucoes.append({"cenario": "base", "pensar_ms": 20, "comer_ms": 30, "gomaxprocs": "1",
                                  "versao": versao, "rodada": 1, **r})

        # 4: V1 oficial, V1 com atraso (10x) e sem atraso (50x)
        exe = compilar("V1", tmp)
        cod, saida = executar(exe, timeout=60)
        (RESULTADOS / "v1-deadlock.txt").write_text(saida, encoding="utf-8")
        for atraso, vezes in ((10, 10), (0, 50)):
            exe = compilar("V1", tmp, atraso=atraso)
            for i in range(1, vezes + 1):
                print(f"[V1 atraso={atraso}ms] {i}/{vezes}", flush=True)
                cod, saida = executar(exe, timeout=60)
                refeicoes = len(re.findall(r"F\d: C\d+", saida))
                v1_freq.append({"atraso_ms": atraso, "execucao": i, "deadlock": int("deadlock!" in saida),
                                "refeicoes_antes_de_parar": refeicoes})

    def gravar(nome, linhas):
        with open(RESULTADOS / nome, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
            w.writeheader()
            w.writerows(linhas)

    gravar("execucoes.csv", execucoes)
    gravar("espera_por_filosofo.csv", por_filosofo)
    gravar("v1_frequencia_deadlock.csv", v1_freq)
    print("Pronto: resultados/execucoes.csv, espera_por_filosofo.csv, v1_frequencia_deadlock.csv")


if __name__ == "__main__":
    main()
