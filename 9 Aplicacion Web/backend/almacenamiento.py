"""Persistencia PostgreSQL de la coordinación hospitalaria."""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


BLOQUEO_OPERACIONES = 210260184


def conectar(base: Path | None = None):
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise RuntimeError('Falta DATABASE_URL. Configura la conexión a PostgreSQL.')
    return psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=10)


def bloquear_operaciones(con):
    fila = con.execute('SELECT pg_try_advisory_lock(%s) AS adquirido', (BLOQUEO_OPERACIONES,)).fetchone()
    if not fila['adquirido']:
        raise RuntimeError('Otra operación está actualizando la programación. Vuelve a intentarlo.')


def poner_config(con, clave, valor):
    con.execute('''
        INSERT INTO configuracion (clave, valor_json) VALUES (%s, %s)
        ON CONFLICT (clave) DO UPDATE SET valor_json = EXCLUDED.valor_json
    ''', (clave, Jsonb(valor)))


def config(con, clave, default=None):
    fila = con.execute('SELECT valor_json FROM configuracion WHERE clave = %s', (clave,)).fetchone()
    return fila['valor_json'] if fila else default


def instalada(con):
    return config(con, 'inicializada', False)


def cargar_fuente(con, archivo: str):
    # Carreteras reales desde geo/, sin sobrescribir las fuentes históricas de la BD.
    from red_operativa import cargar_fuente_red
    calles = cargar_fuente_red(archivo)
    if calles is not None:
        return calles
    return [r['fila_json'] for r in con.execute(
        'SELECT fila_json FROM fuente_registro WHERE archivo = %s ORDER BY ordinal', (archivo,))]


def cargar_programaciones(con):
    return [r['fila_json'] for r in con.execute(
        'SELECT fila_json FROM programaciones ORDER BY fecha, inicio, caso_id')]


def cargar_pendientes(con):
    return [{'CASO_ID': r['caso_id'], 'MOTIVO': r['motivo']} for r in
            con.execute('SELECT caso_id, motivo FROM pendientes ORDER BY caso_id')]


def cargar_propuestas(con):
    return [r['fila_json'] for r in con.execute(
        'SELECT fila_json FROM propuestas ORDER BY caso_id')]


def guardar_estado(con, programadas: list[dict], pendientes: list[dict], propuestas: list[dict]):
    ids_prog = [p['CASO_ID'] for p in programadas]
    ids_pend = [p['CASO_ID'] for p in pendientes]
    if (len(ids_prog) != len(set(ids_prog)) or len(ids_pend) != len(set(ids_pend))
            or set(ids_prog) & set(ids_pend)):
        raise RuntimeError('La programación contiene identificadores repetidos o incompatibles')
    con.execute('DELETE FROM programaciones')
    con.execute('DELETE FROM pendientes')
    con.execute('DELETE FROM propuestas')
    with con.cursor() as cur:
        cur.executemany('''
            INSERT INTO programaciones (caso_id, hospital, fecha, inicio, fila_json)
            VALUES (%s, %s, %s, %s, %s)
        ''', ((r['CASO_ID'], r['HOSPITAL'], r['FECHA'], r['INICIO'], Jsonb(r)) for r in programadas))
        cur.executemany('INSERT INTO pendientes (caso_id, motivo) VALUES (%s, %s)',
                        ((r['CASO_ID'], r['MOTIVO']) for r in pendientes))
        cur.executemany('''
            INSERT INTO propuestas (caso_id, destino, fila_json) VALUES (%s, %s, %s)
        ''', ((r['CASO_ID'], r['HOSPITAL_DESTINO'], Jsonb(r)) for r in propuestas))


def reiniciar_estado(base: Path) -> dict:
    with conectar(base) as con:
        bloquear_operaciones(con)
        if not instalada(con):
            raise RuntimeError('PostgreSQL no contiene los datos iniciales')
        with con.transaction():
            con.execute('DELETE FROM programaciones')
            con.execute('DELETE FROM pendientes')
            con.execute('DELETE FROM propuestas')
            con.execute('DELETE FROM eventos')
            con.execute('INSERT INTO programaciones SELECT * FROM programaciones_base')
            con.execute('INSERT INTO pendientes SELECT * FROM pendientes_base')
            for clave, valor in {'paso': 0, 'bloqueos_recursos': [],
                                 'bloqueos_rutas': [], 'canceladas': []}.items():
                poner_config(con, clave, valor)
    return resumen(base)


def resumen(base: Path):
    with conectar(base) as con:
        if not instalada(con):
            return {'inicializada': False, 'mensaje': 'PostgreSQL no contiene datos iniciales.'}
        grupos = {r['hospital']: r['n'] for r in con.execute(
            'SELECT hospital, COUNT(*) AS n FROM programaciones GROUP BY hospital')}
        def contar(tabla):
            return con.execute(f'SELECT COUNT(*) AS n FROM {tabla}').fetchone()['n']
        return {'inicializada': True, 'casos': config(con, 'total_casos'),
                'programadas': contar('programaciones'),
                'pendientes': contar('pendientes'),
                'propuestas': contar('propuestas'),
                'eventos': contar('eventos'),
                'paso': config(con, 'paso', 0), 'por_hospital': grupos,
                'bloqueos_viales': config(con, 'bloqueos_rutas', []),
                'modo': 'SISTEMA_ACTIVO'}
