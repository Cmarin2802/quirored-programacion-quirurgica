"""
Adaptador entre el grafo vial real (geo/) y el motor Bellman-Ford existente
en '9 Aplicacion Web/backend/motores/red_vial.py'.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

BASE_GEO = Path(__file__).resolve().parent
RAIZ_REPO = BASE_GEO.parent
sys.path.insert(0, str(RAIZ_REPO / "9 Aplicacion Web" / "backend" / "motores"))

from red_vial import bellman_ford, construir_arcos  # noqa: E402


def cargar_csv(nombre_archivo: str) -> list[dict[str, str]]:
    ruta = BASE_GEO / nombre_archivo
    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encontró {ruta}. Ejecuta primero 'python geo/generar_red_real.py'."
        )
    with ruta.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def obtener_conexiones_adaptadas() -> list[dict[str, str]]:
    """Devuelve filas compatibles 1:1 con el esquema esperado por red_vial.py y app.py."""
    filas_reales = cargar_csv("conexiones_red_real.csv")
    adaptadas = []
    for r in filas_reales:
        adaptadas.append({
            "CONEXION_ID": r["CONEXION_ID"],
            "ORIGEN_NODO": r["ORIGEN_NODO"],
            "DESTINO_NODO": r["DESTINO_NODO"],
            "TIEMPO_MIN_SIM": r["TIEMPO_MIN_EXACTO"],
            "TIEMPO_MIN_ENTERO": r["TIEMPO_MIN_SIM"],
            "ESTADO": r["ESTADO"],
            "NOMBRE_VIA": r["NOMBRE_VIA"],
            "DISTANCIA_M": r["DISTANCIA_M"],
        })
    return adaptadas


def obtener_payload_api_red(bloqueadas: list[str] | set[str] = ()) -> dict:
    """Simula la respuesta exacta del endpoint GET /api/red usando la red real."""
    bloqueadas_set = set(bloqueadas)
    hospitales = cargar_csv("hospitales_red_real.csv")
    vias = cargar_csv("puntos_viales_red_real.csv")
    conexiones = cargar_csv("conexiones_red_real.csv")

    nodos = [
        {
            "id": h["HOSPITAL_ID"],
            "nombre": h["NOMBRE"],
            "tipo": "HOSPITAL",
            "lat": float(h["LATITUD"]),
            "lon": float(h["LONGITUD"]),
        }
        for h in hospitales
    ] + [
        {
            "id": v["NODO_VIAL_ID"],
            "nombre": v["NOMBRE"],
            "tipo": "INTERSECCION",
            "lat": float(v["LATITUD"]),
            "lon": float(v["LONGITUD"]),
        }
        for v in vias
    ]

    aristas = [
        {
            "id": x["CONEXION_ID"],
            "desde": x["ORIGEN_NODO"],
            "hasta": x["DESTINO_NODO"],
            "peso_min": int(x["TIEMPO_MIN_SIM"]),
            "via": x["NOMBRE_VIA"],
            "bloqueada": x["CONEXION_ID"] in bloqueadas_set or x["ESTADO"] != "HABILITADA",
        }
        for x in conexiones
    ]
    return {"nodos": nodos, "conexiones": aristas}


def calcular_ruta_real(origen: str, destino: str, bloqueadas: list[str] | set[str] = ()) -> dict:
    """Ejecuta el motor Bellman-Ford del proyecto sobre la red real de San Isidro."""
    filas = obtener_conexiones_adaptadas()
    arcos = construir_arcos(filas, bloqueados=bloqueadas)
    resultado = bellman_ford(arcos, origen, destino)
    if resultado is None:
        return {"origen": origen, "destino": destino, "sin_ruta": True}

    indice_tramos = {(r["ORIGEN_NODO"], r["DESTINO_NODO"]): r for r in filas}
    calles_recorridas = []
    distancia_total_m = 0.0
    camino = resultado["camino"]
    for i in range(len(camino) - 1):
        tramo = indice_tramos.get((camino[i], camino[i + 1]))
        if tramo:
            distancia_total_m += float(tramo["DISTANCIA_M"])
            if not calles_recorridas or calles_recorridas[-1] != tramo["NOMBRE_VIA"]:
                calles_recorridas.append(tramo["NOMBRE_VIA"])

    resultado["tiempo_min_sim"] = round(resultado["tiempo_min_sim"], 2)
    resultado["distancia_total_m"] = round(distancia_total_m, 1)
    resultado["calles"] = calles_recorridas
    return resultado