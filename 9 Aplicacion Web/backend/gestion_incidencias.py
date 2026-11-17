"""Cierre auditable de bloqueos del modelo experimental.

Resolver una incidencia restaura la disponibilidad para operaciones futuras.
NO restaura automáticamente las cirugías que ya fueron reprogramadas.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from psycopg.types.json import Jsonb

from almacenamiento import (bloquear_operaciones, conectar, config, instalada,
                             poner_config, resumen)
from servicio_simulacion import _LOCK


def _eventos(con):
    return [dict(f) for f in con.execute(
        'SELECT paso, tipo, estado, detalle_json FROM eventos ORDER BY paso')]


def _bloqueos_evento(evento):
    detalle = evento['detalle_json'] or {}
    fecha = detalle.get('fecha')
    recursos = {(fecha, r) for r in detalle.get('recursos_bloqueados', []) if fecha and r}
    rutas = set(detalle.get('rutas_bloqueadas', []))
    return recursos, rutas


def _activos(eventos):
    resueltos = {int(e['detalle_json']['resuelve_paso']) for e in eventos
                 if e['tipo'] == 'resolucion_incidencia'
                 and (e['detalle_json'] or {}).get('resuelve_paso') is not None}
    return [e for e in eventos
            if e['paso'] not in resueltos and e['estado'] == 'APLICADO'
            and e['tipo'] not in ('cancelacion', 'programacion_manual_existente',
                                  'planificacion_jornada', 'propuestas_derivacion',
                                  'derivacion_confirmada', 'resolucion_incidencia')
            and any(_bloqueos_evento(e))]


def listar_incidencias_activas(base: Path):
    with conectar(base) as con:
        if not instalada(con):
            return []
        resultados = []
        for e in reversed(_activos(_eventos(con))):
            detalle = e['detalle_json'] or {}
            resultados.append({
                'paso': e['paso'], 'tipo': e['tipo'],
                'fecha': detalle.get('fecha', ''),
                'hospital': detalle.get('hospital', ''),
                'recursos_bloqueados': detalle.get('recursos_bloqueados', []),
                'rutas_bloqueadas': detalle.get('rutas_bloqueadas', []),
                'afectadas': detalle.get('afectadas', 0),
            })
        return resultados


def resolver_incidencia(base: Path, paso_incidencia: int) -> dict:
    if isinstance(paso_incidencia, bool) or not isinstance(paso_incidencia, int) or paso_incidencia < 1:
        raise ValueError('Indica el identificador válido de la incidencia')
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError('Hay otra operación en curso')
    try:
        con = conectar(base)
        try:
            bloquear_operaciones(con)
            if not instalada(con):
                raise RuntimeError('La base de datos no está inicializada')
            activos = _activos(_eventos(con))
            objetivo = next((x for x in activos if x['paso'] == paso_incidencia), None)
            if objetivo is None:
                raise ValueError('La incidencia no está activa o ya fue resuelta')
            b_obj, v_obj = _bloqueos_evento(objetivo)
            otros_b, otros_v = set(), set()
            for e in activos:
                if e['paso'] != paso_incidencia:
                    b, v = _bloqueos_evento(e)
                    otros_b.update(b)
                    otros_v.update(v)
            bloqueos = {tuple(x) for x in config(con, 'bloqueos_recursos', [])}
            vias = set(config(con, 'bloqueos_rutas', []))
            liberar_b = (b_obj - otros_b) & bloqueos
            liberar_v = (v_obj - otros_v) & vias
            restantes_b = bloqueos - liberar_b
            restantes_v = vias - liberar_v
            paso = int(config(con, 'paso', 0)) + 1
            detalle = {
                'tipo': 'resolucion_incidencia', 'estado': 'RESUELTO',
                'paso': paso, 'resuelve_paso': paso_incidencia,
                'tipo_original': objetivo['tipo'],
                'fecha': (objetivo['detalle_json'] or {}).get('fecha', ''),
                'hospital': (objetivo['detalle_json'] or {}).get('hospital', ''),
                'recursos_liberados': [list(x) for x in sorted(liberar_b)],
                'rutas_habilitadas': sorted(liberar_v),
                'afectadas': 0, 'reprogramadas': 0,
                'nota': ('Se habilitan recursos y rutas para decisiones posteriores; '
                         'no se revierten las reprogramaciones ni se elimina el historial.'),
                'instante_registro': datetime.now().isoformat(timespec='seconds'),
            }
            con.execute('BEGIN')
            try:
                poner_config(con, 'bloqueos_recursos', [list(x) for x in sorted(restantes_b)])
                poner_config(con, 'bloqueos_rutas', sorted(restantes_v))
                # Las propuestas anteriores dependían de una disponibilidad diferente.
                con.execute('DELETE FROM propuestas')
                con.execute('INSERT INTO eventos VALUES (%s,%s,%s,%s,%s)',
                            (paso, detalle['instante_registro'], detalle['tipo'],
                             detalle['estado'], Jsonb(detalle)))
                poner_config(con, 'paso', paso)
                con.execute('COMMIT')
            except Exception:
                con.execute('ROLLBACK')
                raise
        finally:
            con.close()
        return {'estado': 'RESUELTO', 'evento': detalle, 'resumen': resumen(base)}
    finally:
        _LOCK.release()
