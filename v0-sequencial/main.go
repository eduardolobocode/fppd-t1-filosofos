// V0 - Versão sequencial (baseline / pior caso)
//
// Baseada no filo_seq.go do Prof. Cesar De Rose. Os filósofos executam um
// depois do outro, sem concorrência. Como ninguém disputa garfos, não há
// sincronização: pegarGarfos e soltarGarfos não fazem nada.
//
// Mudanças em relação ao código original:
//   - 20 ciclos por filósofo (o enunciado pede 20; o original tinha 5);
//   - tempos em milissegundos (20 ms pensando, 30 ms comendo), mantendo a
//     proporção 2:3 do original, que usava segundos;
//   - cada linha da linha do tempo é impressa com um único Printf, para não
//     misturar com a saída de outros filósofos nas versões concorrentes;
//   - coleta das métricas pedidas e repetição do jantar 5 vezes.
//
// Tempo esperado: ciclos * filósofos * (pensar + comer) = 20 * 5 * 50 ms = 5 s.
//
// Executar (na raiz do repositório): go run ./v0-sequencial

package main

import (
	"fmt"
	"runtime"
	"strings"
	"time"
)

const (
	numFilosofos  = 5
	numCiclos     = 20
	numExecucoes  = 5
	tempoPensar   = 20 * time.Millisecond
	tempoComer    = 30 * time.Millisecond
	larguraColuna = 8
)

// ---------------------------------------------------------------------------
// Garfos: na versão sequencial ninguém disputa, então não há o que proteger.
// ---------------------------------------------------------------------------

func pegarGarfos(id int)  {}
func soltarGarfos(id int) {}

// ---------------------------------------------------------------------------
// Ciclo de um filósofo: pensar -> pegar garfos -> comer -> soltar garfos.
// Este trecho é igual em todas as versões.
// ---------------------------------------------------------------------------

func umCiclo(id, ciclo int, m *metricas, mostrar bool) {
	imprimir(mostrar, id, fmt.Sprintf("P%d", ciclo))
	time.Sleep(tempoPensar)

	inicioEspera := time.Now()
	pegarGarfos(id)
	m.registrarEspera(id, time.Since(inicioEspera))

	m.comecouComer()
	imprimir(mostrar, id, fmt.Sprintf("C%d", ciclo))
	time.Sleep(tempoComer)
	m.terminouComer() // antes de soltar os garfos, para o vizinho não começar antes da contagem baixar

	soltarGarfos(id)
	m.ciclos[id]++
}

// jantar executa um jantar completo e devolve as métricas dele.
func jantar(mostrar bool) resultado {
	m := &metricas{}
	inicio := time.Now()
	inicioJantar = inicio

	for ciclo := 1; ciclo <= numCiclos; ciclo++ {
		for id := 0; id < numFilosofos; id++ {
			umCiclo(id, ciclo, m, mostrar)
		}
	}

	return m.resumo(time.Since(inicio))
}

// ---------------------------------------------------------------------------
// Métricas (iguais em todas as versões)
// ---------------------------------------------------------------------------

type metricas struct {
	somaEspera [numFilosofos]time.Duration // escrita só pelo próprio filósofo
	maxEspera  [numFilosofos]time.Duration // escrita só pelo próprio filósofo
	ciclos     [numFilosofos]int           // escrita só pelo próprio filósofo

	comendo    int // quantos estão comendo agora (sem mutex: aqui é sequencial)
	maxComendo int
}

func (m *metricas) registrarEspera(id int, espera time.Duration) {
	m.somaEspera[id] += espera
	if espera > m.maxEspera[id] {
		m.maxEspera[id] = espera
	}
}

func (m *metricas) comecouComer() {
	m.comendo++
	if m.comendo > m.maxComendo {
		m.maxComendo = m.comendo
	}
}

func (m *metricas) terminouComer() {
	m.comendo--
}

type resultado struct {
	tempoTotal           time.Duration
	esperaMedia          time.Duration
	esperaMaxima         time.Duration
	maxComendo           int
	ciclos               [numFilosofos]int
	esperaMediaFilosofo  [numFilosofos]time.Duration
	esperaMaximaFilosofo [numFilosofos]time.Duration
}

func (m *metricas) resumo(tempoTotal time.Duration) resultado {
	r := resultado{tempoTotal: tempoTotal, maxComendo: m.maxComendo, ciclos: m.ciclos}
	var soma time.Duration
	refeicoes := 0
	for id := 0; id < numFilosofos; id++ {
		soma += m.somaEspera[id]
		refeicoes += m.ciclos[id]
		if m.maxEspera[id] > r.esperaMaxima {
			r.esperaMaxima = m.maxEspera[id]
		}
		if m.ciclos[id] > 0 {
			r.esperaMediaFilosofo[id] = m.somaEspera[id] / time.Duration(m.ciclos[id])
		}
		r.esperaMaximaFilosofo[id] = m.maxEspera[id]
	}
	if refeicoes > 0 {
		r.esperaMedia = soma / time.Duration(refeicoes)
	}
	return r
}

// ---------------------------------------------------------------------------
// Impressão
// ---------------------------------------------------------------------------

// inicioJantar marca o começo do jantar atual, para a linha do tempo mostrar
// o instante de cada evento. É escrito antes de os filósofos começarem.
var inicioJantar time.Time

// imprimir escreve o instante e o evento na coluna do filósofo, numa única chamada.
func imprimir(mostrar bool, id int, evento string) {
	if mostrar {
		fmt.Printf("%8.1f ms  %s%s\n", ms(time.Since(inicioJantar)), strings.Repeat(" ", id*larguraColuna), evento)
	}
}

func ms(d time.Duration) float64 {
	return float64(d.Microseconds()) / 1000
}

func main() {
	fmt.Println("V0 - Versão sequencial")
	fmt.Printf("Go %s | %s/%s | %d núcleos lógicos | GOMAXPROCS=%d\n",
		runtime.Version(), runtime.GOOS, runtime.GOARCH, runtime.NumCPU(), runtime.GOMAXPROCS(0))
	fmt.Printf("%d filósofos | %d ciclos | pensar %v | comer %v | %d execuções\n\n",
		numFilosofos, numCiclos, tempoPensar, tempoComer, numExecucoes)

	var resultados []resultado
	for exec := 1; exec <= numExecucoes; exec++ {
		mostrar := exec == 1 // a linha do tempo só é impressa na 1ª execução
		if mostrar {
			fmt.Println("Linha do tempo da execução 1 (P = pensando, C = comendo, número = ciclo)")
			cabecalho := fmt.Sprintf("%11s  ", "instante")
			for id := 0; id < numFilosofos; id++ {
				cabecalho += fmt.Sprintf("%-*s", larguraColuna, fmt.Sprintf("F%d", id))
			}
			fmt.Println(cabecalho)
		}

		r := jantar(mostrar)
		resultados = append(resultados, r)

		if mostrar {
			fmt.Println()
		}
		fmt.Printf("Execução %d: tempo total %8.1f ms | espera média %6.1f ms | espera máx %6.1f ms | máx comendo junto %d | ciclos %v\n",
			exec, ms(r.tempoTotal), ms(r.esperaMedia), ms(r.esperaMaxima), r.maxComendo, r.ciclos)
	}

	imprimirResumo("V0", resultados)
}

// imprimirResumo mostra as médias das execuções, a espera por filósofo
// (para discutir starvation) e as linhas em CSV para a planilha.
func imprimirResumo(versao string, resultados []resultado) {
	n := time.Duration(len(resultados))
	var somaTotal, somaEspera, maiorEspera time.Duration
	maxComendo := 0
	var esperaMediaFil, esperaMaxFil [numFilosofos]time.Duration
	for _, r := range resultados {
		somaTotal += r.tempoTotal
		somaEspera += r.esperaMedia
		if r.esperaMaxima > maiorEspera {
			maiorEspera = r.esperaMaxima
		}
		if r.maxComendo > maxComendo {
			maxComendo = r.maxComendo
		}
		for id := 0; id < numFilosofos; id++ {
			esperaMediaFil[id] += r.esperaMediaFilosofo[id] / n
			if r.esperaMaximaFilosofo[id] > esperaMaxFil[id] {
				esperaMaxFil[id] = r.esperaMaximaFilosofo[id]
			}
		}
	}

	fmt.Printf("\nMédia de %d execuções: tempo total %.1f ms | espera média %.1f ms | maior espera %.1f ms | máx comendo junto %d\n",
		len(resultados), ms(somaTotal/n), ms(somaEspera/n), ms(maiorEspera), maxComendo)

	fmt.Println("\nEspera por filósofo (todas as execuções):")
	for id := 0; id < numFilosofos; id++ {
		fmt.Printf("  F%d: média %6.1f ms | máxima %6.1f ms\n", id, ms(esperaMediaFil[id]), ms(esperaMaxFil[id]))
	}

	fmt.Println("\nCSV (copiar para a planilha):")
	fmt.Println("versao,execucao,tempo_total_ms,espera_media_ms,espera_max_ms,max_comendo,ciclos")
	for i, r := range resultados {
		fmt.Printf("%s,%d,%.1f,%.1f,%.1f,%d,%s\n", versao, i+1, ms(r.tempoTotal), ms(r.esperaMedia),
			ms(r.esperaMaxima), r.maxComendo, strings.Trim(fmt.Sprint(r.ciclos), "[]"))
	}
}
