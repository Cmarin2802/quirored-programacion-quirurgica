"""Fuentes de calles reales sin modificar los CSV originales ni PostgreSQL.

Los datos experimentales de programación permanecen en la base local; la red
vial operativa se lee de geo/ (trabajo geográfico del equipo).
"""
from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
CARPETA_GEO = RAIZ_REPOSITORIO / 'geo'
ARCHIVOS_RED = {
    'conexiones_red.csv': 'conexiones_red_real.csv',
    'puntos_viales_red.csv': 'puntos_viales_red_real.csv',
}


def habilitada() -> bool:
    return os.environ.get('QUIRORED_RED_REAL', '1').strip().lower() not in ('0', 'false', 'no')


@lru_cache(maxsize=4)
def _leer_geo(nombre: str) -> tuple[dict, ...]:
    ruta = CARPETA_GEO / nombre
    if not ruta.is_file():
        raise FileNotFoundError(f'Faltan los datos de calles reales: {ruta}')
    with ruta.open('r', encoding='utf-8-sig', newline='') as archivo:
        return tuple(dict(fila) for fila in csv.DictReader(archivo))


def leer_geo(nombre: str) -> list[dict]:
    """Devuelve copias: los motores pueden transformar filas sin alterar el cache."""
    return [dict(fila) for fila in _leer_geo(nombre)]


def cargar_fuente_red(nombre: str) -> list[dict] | None:
    if not habilitada() or nombre not in ARCHIVOS_RED:
        return None
    filas = leer_geo(ARCHIVOS_RED[nombre])
    if nombre == 'conexiones_red.csv':
        for fila in filas:
            # La ruta y el programador deben usar el mismo peso (minutos exactos).
            fila['TIEMPO_MIN_SIM'] = fila['TIEMPO_MIN_EXACTO']
    return filas


def coordenadas_sedes() -> dict[str, dict]:
    if not habilitada():
        return {}
    return {r['HOSPITAL_ID']: r for r in leer_geo('hospitales_red_real.csv')}


def enriquecer_ruta(ruta: dict | None, conexiones: list[dict]) -> dict | None:
    if ruta is None:
        return None
    # Entre un mismo par dirigido puede haber varios tramos: conservar el menor.
    tramos = {}
    for fila in conexiones:
        clave = (fila['ORIGEN_NODO'], fila['DESTINO_NODO'])
        peso = float(fila['TIEMPO_MIN_SIM'])
        if clave not in tramos or peso < float(tramos[clave]['TIEMPO_MIN_SIM']):
            tramos[clave] = fila
    distancia, calles = 0.0, []
    camino = ruta['camino']
    for origen, destino in zip(camino, camino[1:]):
        tramo = tramos.get((origen, destino))
        if not tramo:
            continue
        distancia += float(tramo.get('DISTANCIA_M', 0) or 0)
        nombre = tramo.get('NOMBRE_VIA', 'Calle sin nombre')
        if not calles or calles[-1] != nombre:
            calles.append(nombre)
    return {
        **ruta,
        'tiempo_min_sim': round(ruta['tiempo_min_sim'], 2),
        'distancia_total_m': round(distancia, 1),
        'calles': calles,
        'modelo': 'RED_VIAL_OSM_ESTIMADA' if habilitada() else 'RED_VIAL_SIMULADA',
    }
