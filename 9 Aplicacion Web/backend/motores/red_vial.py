"""Rutas de la red hospitalaria simulada. Bellman-Ford y Prim sin dependencias externas.

Bellman-Ford calcula camino mínimo de origen a destino.
Prim calcula árbol de expansión mínima de la proyección no dirigida (análisis estructural).
Todos los pesos son minutos simulados, no viajes reales.
"""
from __future__ import annotations
from collections import defaultdict
from math import inf


def construir_arcos(filas, bloqueados=()):
    bloqueados = set(bloqueados)
    arcos = []
    for r in filas:
        if r['ESTADO'] != 'HABILITADA' or r['CONEXION_ID'] in bloqueados:
            continue
        peso = float(r['TIEMPO_MIN_SIM'])
        if peso < 0:
            raise ValueError('No se admiten tiempos negativos')
        arcos.append((r['ORIGEN_NODO'], r['DESTINO_NODO'], peso, r['CONEXION_ID']))
    return arcos


def bellman_ford(arcos, origen, destino):
    nodos = {origen, destino}
    for u, v, _, _ in arcos:
        nodos.add(u)
        nodos.add(v)
    dist = {n: inf for n in nodos}
    padre = {}
    dist[origen] = 0
    for _ in range(len(nodos)-1):
        cambio = False
        for u, v, peso, _ in arcos:
            if dist[u] + peso < dist[v]:
                dist[v] = dist[u]+peso
                padre[v] = u
                cambio = True
        if not cambio:
            break
    if dist[destino] == inf:
        return None
    camino = [destino]
    while camino[-1] != origen:
        camino.append(padre[camino[-1]])
    camino.reverse()
    return {'origen':origen,'destino':destino,'camino':camino,'tiempo_min_sim':dist[destino]}


def prim(arcos, nodos=None):
    """MST sobre conexiones bidireccionales proyectadas; no sirve como camino mínimo."""
    import heapq
    grafo = defaultdict(dict)
    if nodos is not None:
        for nodo in nodos:
            grafo[nodo]
    for u, v, costo, _ in arcos:
        
        grafo[u][v] = min(grafo[u].get(v, inf), costo)
        grafo[v][u] = min(grafo[v].get(u, inf), costo)
    if not grafo:
        return {'aristas':[], 'costo_total_min_sim':0, 'conexo':False}
    inicio = min(grafo)
    visitados = {inicio}
    cola = [(peso, inicio, destino) for destino, peso in grafo[inicio].items()]
    heapq.heapify(cola)
    mst = []
    total = 0
    while cola:
        costo, u, v = heapq.heappop(cola)
        if v in visitados:
            continue
        mst.append((u, v, costo))
        total += costo
        visitados.add(v)
        for w, peso in grafo[v].items():
            if w not in visitados:
                heapq.heappush(cola, (peso, v, w))
    return {'aristas':mst,'costo_total_min_sim':total,'conexo':len(visitados)==len(grafo)}
