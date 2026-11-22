"""Mediciones independientes de siete algoritmos de QuiroRed.

Greedy se evalúa en benchmarks_execution.py junto a la referencia FCFS.
No se conecta a PostgreSQL; no altera RESULTADOS.csv ni la aplicación web.
"""
from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
import time
import tracemalloc
import threading
from collections import Counter, defaultdict, deque
from datetime import date, datetime, time as hora
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

RAIZ = Path(__file__).resolve().parent.parent
MOTORES = RAIZ / "9 Aplicacion Web" / "backend" / "motores"
sys.path.insert(0, str(MOTORES))

from algoritmos_integrados import (  # noqa: E402
    bfs_compatibilidades, dfs_impacto, seleccionar_dinamica,
    ford_fulkerson, backtracking_asignacion,
)
from motor_programacion_v1 import Programador  # noqa: E402
from red_vial import construir_arcos, bellman_ford, prim  # noqa: E402

COLUMNAS = [
    "ALGORITMO", "TIPO_ENTRADA", "N_ENTRADA", "TIEMPO_PROMEDIO_MS",
    "TIEMPO_DESV_MS", "MEMORIA_PYTHON_PICO_KB", "RAM_PROCESO_OBSERVADA_MB",
    "REPETICIONES", "SEMILLA", "RESULTADO",
]


def leer_csv(ruta: Path, delimitador=";"):
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delimitador))


def medir(algoritmo, tipo_entrada, n, ejecutar, repeticiones, semilla):
    """Tiempo sin instrumentación; pico Python por tracemalloc en corrida separada."""
    tiempos = []
    ultimo = None
    for _ in range(repeticiones):
        t0 = time.perf_counter()
        ultimo = ejecutar()
        tiempos.append((time.perf_counter() - t0) * 1000)
    max_rss = [0]
    stop = threading.Event()
    hilo = None
    if psutil is not None:
        proceso = psutil.Process()
        max_rss[0] = proceso.memory_info().rss
        def observar_ram():
            while not stop.wait(0.002):
                max_rss[0] = max(max_rss[0], proceso.memory_info().rss)
        hilo = threading.Thread(target=observar_ram, daemon=True)
        hilo.start()
    tracemalloc.start()
    try:
        ejecutar()
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        stop.set()
        if hilo is not None:
            hilo.join()
            max_rss[0] = max(max_rss[0], proceso.memory_info().rss)
    return {
        "ALGORITMO": algoritmo, "TIPO_ENTRADA": tipo_entrada, "N_ENTRADA": n,
        "TIEMPO_PROMEDIO_MS": round(statistics.mean(tiempos), 4),
        "TIEMPO_DESV_MS": round(statistics.stdev(tiempos), 4) if len(tiempos) > 1 else 0,
        "MEMORIA_PYTHON_PICO_KB": round(pico / 1024, 3),
        "RAM_PROCESO_OBSERVADA_MB": round(max_rss[0] / (1024 * 1024), 3) if psutil is not None else "",
        "REPETICIONES": repeticiones, "SEMILLA": semilla, "RESULTADO": str(ultimo),
    }


def seleccionar(casos, n, semilla):
    if n > len(casos):
        raise ValueError(f"Se solicitaron {n} cirugías, pero solo hay {len(casos)}")
    rng = random.Random(semilla)
    indices = sorted(rng.sample(range(len(casos)), n))
    return [casos[i] for i in indices]


def preparar_compatibilidad(aristas):
    ady = defaultdict(list)
    salas_caso = defaultdict(list)
    for a in aristas:
        relacion = a["RELACION"]
        if relacion.startswith("CANDIDATO_") or relacion in ("HOSPITAL_CANDIDATO", "SOLICITANTE_Y_CANDIDATO"):
            ady[a["ORIGEN_ID"]].append((a["DESTINO_ID"], relacion))
        if relacion == "CANDIDATO_SALA":
            salas_caso[a["ORIGEN_ID"]].append(a["DESTINO_ID"])
    return ady, salas_caso


def preparar_inverso(aristas, ids):
    ids = set(ids)
    inv = defaultdict(set)
    conteo = Counter()
    for a in aristas:
        if a["ORIGEN_ID"] in ids and a["RELACION"].startswith("CANDIDATO_"):
            destino, caso = a["DESTINO_ID"], a["ORIGEN_ID"]
            inv[destino].add(caso)
            conteo[destino] += 1
    return inv, [rid for rid, _ in conteo.most_common(10)]


def preparar_emparejamiento(casos, salas_caso):
    # Se utilizan salas compatibles del grafo y franjas de prueba de dos horas.
    # Este test mide SOLO emparejamiento; no valida disponibilidad clínica integral.
    horas = ("08:00", "10:00", "12:00", "14:00", "16:00", "18:00")
    return {c["CASO_ID"]: [(sid, t) for sid in sorted(set(salas_caso[c["CASO_ID"]]))[:3] for t in horas]
            for c in casos}


def subconjuntos_viales(arcos, tamanos):
    vecindad = defaultdict(set)
    for u, v, _, _ in arcos:
        vecindad[u].add(v)
        vecindad[v].add(u)
    todos = set(vecindad)
    if not todos:
        raise ValueError("Grafo vial vacío")
    origen = "H1" if "H1" in todos else sorted(todos)[0]
    orden = []
    cola = deque([origen])
    vistos = {origen}
    while cola:
        u = cola.popleft()
        orden.append(u)
        for v in sorted(vecindad[u]):
            if v not in vistos:
                vistos.add(v)
                cola.append(v)
    # Si hay componentes desconectados se incorporan al final sin inventar aristas.
    orden.extend(sorted(todos - vistos))
    for n in tamanos:
        if n > len(orden):
            raise ValueError(f"La red solo contiene {len(orden)} nodos: N={n} inválido")
        elegidos = set(orden[:n])
        yield n, [a for a in arcos if a[0] in elegidos and a[1] in elegidos], elegidos, origen


def prueba_backtracking(programador, muestra):
    resultados = 0
    fechas = [date.fromisoformat(x) for x in programador.fechas]
    for caso in muestra:
        fecha_min = date.fromisoformat(caso["FECHA_MINIMA_OPERABLE_SIM"])
        dia = next((d for d in fechas if d >= fecha_min), None)
        if dia is None:
            continue
        inicio = datetime.combine(dia, hora(8, 0))
        asignacion = backtracking_asignacion(
            programador, caso, caso["HOSPITAL_SOLICITANTE"], dia, inicio, max_intentos=150,
        )
        resultados += int(asignacion is not None)
    return resultados


def ejecutar(args):
    if args.repeticiones < 1:
        raise ValueError("Las repeticiones deben ser positivas")
    salida = Path(args.salida).resolve()
    if salida.exists() and not args.sobrescribir:
        raise FileExistsError(f"El archivo ya existe: {salida}. No se sobrescribirá sin --sobrescribir")
    datos = RAIZ / "3 Datos"
    grafos = RAIZ / "4 Grafos"
    geo = RAIZ / "geo" / "conexiones_red_real.csv"
    casos = leer_csv(datos / "cirugias_red.csv")
    aristas = leer_csv(grafos / "grafo_aristas_red.csv")
    red = leer_csv(geo, delimitador=",")
    arcos = construir_arcos(red)
    ady, salas = preparar_compatibilidad(aristas)
    total_nodos = len({x for u, v, _, _ in arcos for x in (u, v)})
    if total_nodos != 136:
        print(f"Nota: la red vial contiene {total_nodos} nodos según el archivo leído.")

    filas = []
    for n in args.n_list:
        muestra = seleccionar(casos, n, args.semilla)
        ids = [c["CASO_ID"] for c in muestra]
        print(f"Casos N={n}: BFS, DFS, programación dinámica y Ford-Fulkerson", flush=True)
        filas.append(medir("BFS", "solicitudes procesadas", n,
            lambda: sum(len(bfs_compatibilidades(ady, cid)[1]) for cid in ids), args.repeticiones, args.semilla))
        inv, recursos = preparar_inverso(aristas, ids)
        filas.append(medir("DFS", "casos en subgrafo inverso", n,
            lambda: sum(len(dfs_impacto(inv, rid, set(ids))) for rid in recursos), args.repeticiones, args.semilla))
        filas.append(medir("DINAMICA", "solicitudes candidatas", n,
            lambda: len(seleccionar_dinamica(muestra, capacidad=14*60, max_casos=15)), args.repeticiones, args.semilla))
        emparejamientos = preparar_emparejamiento(muestra, salas)
        filas.append(medir("FORD_FULKERSON", "solicitudes a emparejar", n,
            lambda: len(ford_fulkerson(emparejamientos)), args.repeticiones, args.semilla))

    print("Backtracking: pruebas acotadas sobre casos reales (sin registrar asignaciones)", flush=True)
    programador = Programador(RAIZ)
    for n in args.backtracking_n:
        candidatos = [c for c in seleccionar(casos, min(len(casos), max(100, n * 3)), args.semilla)
                      if c["PACIENTE_LISTO_SIM"] == "SI" and c["PACIENTE_PRESENTE_SIM"] == "SI"][:n]
        if not candidatos:
            continue
        filas.append(medir("BACKTRACKING", "solicitudes evaluadas sin reservar", len(candidatos),
            lambda: prueba_backtracking(programador, candidatos), args.repeticiones, args.semilla))

    print("Red vial real: Bellman-Ford y Prim", flush=True)
    tamaños_viales = sorted({max(12, int(total_nodos * f)) for f in (0.25, 0.50, 0.75)} | {total_nodos})
    for n, subred, nodos, origen in subconjuntos_viales(arcos, tamaños_viales):
        # Seleccionamos un destino realmente alcanzable por calles dirigidas.
        vecinos_dir = defaultdict(set)
        for u, v, _, _ in subred:
            vecinos_dir[u].add(v)
        alcanzables = {origen}
        por_ver = deque([origen])
        while por_ver:
            u = por_ver.popleft()
            for v in vecinos_dir[u]:
                if v not in alcanzables:
                    alcanzables.add(v)
                    por_ver.append(v)
        destino = sorted(alcanzables - {origen})[-1] if len(alcanzables) > 1 else origen
        filas.append(medir("BELLMAN_FORD", "nodos de subred vial", n,
            lambda: bool(bellman_ford(subred, origen, destino)), args.repeticiones, args.semilla))
        filas.append(medir("PRIM", "nodos de subred vial", n,
            lambda: prim(subred, nodos)["conexo"], args.repeticiones, args.semilla))

    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = salida.with_name(salida.name + ".temporal")
    try:
        with temporal.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNAS, delimiter=";")
            writer.writeheader()
            writer.writerows(filas)
        temporal.replace(salida)
    finally:
        if temporal.exists():
            temporal.unlink()
    print(f"Resultado guardado: {salida} ({len(filas)} filas)")
    print("Greedy: usar los resultados de Nicolás en benchmarks/RESULTADOS.csv (comparación con FCFS).")


def main():
    parser = argparse.ArgumentParser(description="Mide algoritmos individuales sin tocar PostgreSQL")
    parser.add_argument("--n-list", type=int, nargs="+", default=[100, 500, 1000, 1500])
    parser.add_argument("--backtracking-n", type=int, nargs="+", default=[5, 10, 20, 40])
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument("--repeticiones", type=int, default=2)
    parser.add_argument("--salida", default=str(RAIZ / "benchmarks" / "RESULTADOS_ALGORITMOS.csv"))
    parser.add_argument("--sobrescribir", action="store_true")
    args = parser.parse_args()
    ejecutar(args)


if __name__ == "__main__":
    main()
