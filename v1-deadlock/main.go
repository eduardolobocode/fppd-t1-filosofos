// V1 - Versão concorrente sujeita a deadlock
//
// Cada filósofo é uma goroutine e cada garfo é um sync.Mutex. Todos pegam
// primeiro o garfo da esquerda (id) e depois o da direita ((id+1) % 5).
//
// Por que trava: as 4 condições de Coffman estão presentes.
//   1. Exclusão mútua: cada garfo é um mutex, só um filósofo o segura.
//   2. Posse e espera: o filósofo segura o garfo esquerdo enquanto espera o direito.
//   3. Ausência de preempção: nenhuma goroutine pode tomar o mutex de outra.
//   4. Espera circular: F0 espera F1, que espera F2, ..., e F4 espera F0.
//
// O atraso entre os dois Lock (atrasoEntreGarfos) não cria o defeito: ele só
// alarga a janela em que todos seguram o garfo esquerdo, para que o deadlock
// aconteça sempre na demonstração. Com atrasoEntreGarfos = 0 o programa pode
// travar ou terminar, dependendo da ordem que o escalonador escolher.
//
// Quando todas as goroutines ficam bloqueadas (os 5 filósofos nos mutexes e o
// main no wg.Wait), o runtime do Go detecta e encerra com:
//   fatal error: all goroutines are asleep - deadlock!
//
// Executar (na raiz do repositório): go run ./v1-deadlock

package main

import (
	"fmt"
	"runtime"
	"sync"
	"time"
)

const (
	numFilosofos      = 5
	numCiclos         = 20
	tempoPensar       = 20 * time.Millisecond
	tempoComer        = 30 * time.Millisecond
	atrasoEntreGarfos = 10 * time.Millisecond
)

// ---------------------------------------------------------------------------
// Garfos: um mutex por garfo. Todos na mesma ordem: esquerdo, depois direito.
// ---------------------------------------------------------------------------

var garfos [numFilosofos]sync.Mutex

func pegarGarfos(id int) {
	esquerdo, direito := id, (id+1)%numFilosofos

	garfos[esquerdo].Lock()
	imprimir(true, id, fmt.Sprintf("pegou g%d (esquerdo)", esquerdo))

	time.Sleep(atrasoEntreGarfos) // alarga a janela perigosa (ver comentário no topo)

	imprimir(true, id, fmt.Sprintf("tentando pegar g%d (direito)...", direito))
	garfos[direito].Lock() // se o vizinho segura este garfo e espera o dele, ninguém sai daqui
	imprimir(true, id, fmt.Sprintf("pegou g%d (direito)", direito))
}

func soltarGarfos(id int) {
	esquerdo, direito := id, (id+1)%numFilosofos
	garfos[direito].Unlock()
	garfos[esquerdo].Unlock()
	imprimir(true, id, fmt.Sprintf("soltou g%d e g%d", esquerdo, direito))
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
	wg.Wait() // em deadlock, o main fica preso aqui para sempre

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
	tempoTotal   time.Duration
	esperaMedia  time.Duration
	esperaMaxima time.Duration
	maxComendo   int
	ciclos       [numFilosofos]int
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
	}
	if refeicoes > 0 {
		r.esperaMedia = soma / time.Duration(refeicoes)
	}
	return r
}

// ---------------------------------------------------------------------------
// Impressão
// ---------------------------------------------------------------------------

// inicioJantar marca o começo do jantar, para cada linha mostrar o instante
// do evento. É escrito antes de os filósofos começarem.
var inicioJantar time.Time

// imprimir escreve uma linha "<instante>  F<id>: <evento>" numa única chamada.
func imprimir(mostrar bool, id int, evento string) {
	if mostrar {
		fmt.Printf("%8.1f ms  F%d: %s\n", ms(time.Since(inicioJantar)), id, evento)
	}
}

func ms(d time.Duration) float64 {
	return float64(d.Microseconds()) / 1000
}

func main() {
	fmt.Println("V1 - Versão concorrente sujeita a deadlock")
	fmt.Printf("Go %s | %s/%s | %d núcleos lógicos | GOMAXPROCS=%d\n",
		runtime.Version(), runtime.GOOS, runtime.GOARCH, runtime.NumCPU(), runtime.GOMAXPROCS(0))
	fmt.Printf("%d filósofos | %d ciclos | pensar %v | comer %v | atraso entre garfos %v\n\n",
		numFilosofos, numCiclos, tempoPensar, tempoComer, atrasoEntreGarfos)
	fmt.Println("P = pensando, C = comendo, número = ciclo")
	fmt.Println("Cada filósofo pega o garfo esquerdo e depois o direito.")
	fmt.Println()

	r := jantar(true)

	fmt.Println("\nO jantar terminou sem deadlock desta vez (a ordem do escalonador ajudou).")
	fmt.Printf("Tempo total %.1f ms | espera média %.1f ms | espera máx %.1f ms | máx comendo junto %d | ciclos %v\n",
		ms(r.tempoTotal), ms(r.esperaMedia), ms(r.esperaMaxima), r.maxComendo, r.ciclos)
}
