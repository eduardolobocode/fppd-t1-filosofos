// V3 - Versão concorrente aprimorada (ordenação de recursos)
//
// É a V1 (sem o atraso artificial) com uma única regra a mais: todo filósofo
// pega primeiro o garfo de MENOR número. F0 a F3 continuam pegando esquerdo e
// depois direito; só o F4, que usa os garfos 4 e 0, passa a pegar o g0 antes
// do g4. Não há mutex global: cada garfo é protegido só pelo próprio mutex.
//
// Por que não trava: para existir um ciclo de espera, algum filósofo teria de
// segurar um garfo de número maior e esperar um de número menor. A regra
// proíbe isso, então o ciclo nunca fecha. A condição de Coffman quebrada é a
// espera circular, mas sem limitar quem não disputa garfos: até 2 filósofos
// não vizinhos comem ao mesmo tempo, o máximo possível com 5 garfos.
//
// Starvation: é possível em teoria, porque nada garante a vez de cada um (dois
// vizinhos podem se alternar e deixar o do meio esperando). Na prática o
// sync.Mutex do Go entra em "modo starvation" quando alguém espera mais de
// 1 ms e passa a atender por ordem de chegada. A espera máxima por filósofo,
// impressa no final, mostra se algum deles foi prejudicado.
//
// Tempo mínimo esperado: 2 comem por vez, 100 refeições * 30 ms / 2 = 1,5 s.
//
// Executar (na raiz do repositório): go run ./v3-ordenacao

package main

import (
	"fmt"
	"runtime"
	"strings"
	"sync"
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
// Garfos: um mutex por garfo, sempre pegando primeiro o de menor número.
// ---------------------------------------------------------------------------

var garfos [numFilosofos]sync.Mutex

func pegarGarfos(id int) {
	primeiro, segundo := id, (id+1)%numFilosofos
	if primeiro > segundo {
		primeiro, segundo = segundo, primeiro // só o F4 inverte: g0 antes de g4
	}
	garfos[primeiro].Lock()
	garfos[segundo].Lock()
}

func soltarGarfos(id int) {
	esquerdo, direito := id, (id+1)%numFilosofos
	garfos[direito].Unlock()
	garfos[esquerdo].Unlock()
}

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

func filosofo(id int, m *metricas, mostrar bool, wg *sync.WaitGroup) {
	defer wg.Done()
	for ciclo := 1; ciclo <= numCiclos; ciclo++ {
		umCiclo(id, ciclo, m, mostrar)
	}
}

// jantar cria uma goroutine por filósofo e espera todas terminarem.
func jantar(mostrar bool) resultado {
	m := &metricas{}
	var wg sync.WaitGroup
	inicio := time.Now()
	inicioJantar = inicio

	for id := 0; id < numFilosofos; id++ {
		wg.Add(1)
		go filosofo(id, m, mostrar, &wg)
	}
	wg.Wait()

	return m.resumo(time.Since(inicio))
}

// ---------------------------------------------------------------------------
// Métricas (iguais em todas as versões concorrentes)
// ---------------------------------------------------------------------------

type metricas struct {
	somaEspera [numFilosofos]time.Duration // escrita só pelo próprio filósofo
	maxEspera  [numFilosofos]time.Duration // escrita só pelo próprio filósofo
	ciclos     [numFilosofos]int           // escrita só pelo próprio filósofo

	mu         sync.Mutex // protege os dois campos abaixo (usado só para medir)
	comendo    int        // quantos estão comendo agora
	maxComendo int
}

func (m *metricas) registrarEspera(id int, espera time.Duration) {
	m.somaEspera[id] += espera
	if espera > m.maxEspera[id] {
		m.maxEspera[id] = espera
	}
}

func (m *metricas) comecouComer() {
	m.mu.Lock()
	m.comendo++
	if m.comendo > m.maxComendo {
		m.maxComendo = m.comendo
	}
	m.mu.Unlock()
}

func (m *metricas) terminouComer() {
	m.mu.Lock()
	m.comendo--
	m.mu.Unlock()
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
	fmt.Println("V3 - Versão concorrente aprimorada (ordenação de recursos)")
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

	imprimirResumo("V3", resultados)
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
