"""Propuestas y confirmaciones de derivaciones exclusivamente académicas.

Cada confirmación recalcula la factibilidad con el estado ACTUAL y persiste
cronograma, pendientes y evento en una única transacción PostgreSQL.
"""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta, time
from pathlib import Path

from psycopg.types.json import Jsonb

from almacenamiento import (bloquear_operaciones, cargar_fuente, cargar_pendientes,
    cargar_programaciones, cargar_propuestas, conectar, config, guardar_estado,
    instalada, poner_config, resumen)
from servicio_simulacion import _LOCK, exportar, motor_imports


def _validar_modelo(p, programadas, pendientes, bloqueos, canceladas, total):
    from generador_eventos_v2 import validar_estado
    validar_estado(p, programadas, pendientes, bloqueos, canceladas, total)


def _preparar(con, carpeta, base):
    Programador, _, _, reconstruir_reservas, *_ = motor_imports(base)
    exportar(con, carpeta, base)
    p = Programador(carpeta)
    programadas = cargar_programaciones(con)
    pendientes = cargar_pendientes(con)
    bloqueos = {tuple(x) for x in config(con, 'bloqueos_recursos', [])}
    canceladas = set(config(con, 'canceladas', []))
    reconstruir_reservas(p, programadas)
    for fecha, rid in bloqueos:
        for v in p.disp.get((fecha, rid), []):
            v['ESTADO_PLANIFICADO'] = 'NO_DISPONIBLE'
    for caso in p.casos:
        if caso['CASO_ID'] in canceladas:
            caso['ESTADO_PROGRAMACION'] = 'CANCELADA'
    _validar_modelo(p, programadas, pendientes, bloqueos, canceladas,
                    config(con, 'total_casos'))
    return p, programadas, pendientes, bloqueos, canceladas


def generar_propuestas(base: Path, max_evaluar: int = 20, max_derivaciones: int = 5):
    if not 1 <= max_evaluar <= 50 or not 1 <= max_derivaciones <= 10:
        raise ValueError('Límites de búsqueda inválidos')
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError('Hay otra operación en curso')
    try:
        con = conectar(base)
        try:
            bloquear_operaciones(con)
            if not instalada(con):
                raise RuntimeError('La base de datos no está inicializada')
            with tempfile.TemporaryDirectory(prefix='quirored_propuestas_') as tmp:
                carpeta = Path(tmp)
                _, programadas, pendientes, bloqueos, canceladas = _preparar(con, carpeta, base)
                Programador, escribir, leer, reconstruir_reservas, aplicar_evento, validar_estado, copiar_insumos, planificar = motor_imports(base)
                data, grafo = carpeta/'3 Datos', carpeta/'4 Grafos'
                salida_tmp = carpeta/'adaptador'
                copiar_insumos(carpeta, salida_tmp, data, grafo, bloqueos, canceladas,
                               programadas, pendientes)
                _, salida = planificar(salida_tmp, 'simulacion', max_evaluar,
                                     max_derivaciones, dias_busqueda=7, paso_min=60,
                                     preparacion_min=90,
                                     bloqueadas=config(con, 'bloqueos_rutas', []),
                                     autorizar_simulacion=False)
                propuestas = leer(salida/'propuestas_derivacion.csv')
            paso = int(config(con, 'paso', 0)) + 1
            detalle = {'tipo': 'propuestas_derivacion', 'estado': 'GENERADAS',
                       'paso': paso, 'propuestas': len(propuestas),
                       'afectadas': 0,
                       'instante_registro': datetime.now().isoformat(timespec='seconds')}
            con.execute('BEGIN')
            try:
                # Solo se actualizan las propuestas; no se reescribe el cronograma.
                con.execute('DELETE FROM propuestas')
                with con.cursor() as cur:
                    cur.executemany(
                        'INSERT INTO propuestas (caso_id, destino, fila_json) VALUES (%s,%s,%s)',
                        ((x['CASO_ID'], x['HOSPITAL_DESTINO'], Jsonb(x)) for x in propuestas))
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
        return {'estado': 'PROPUESTAS_GENERADAS', 'propuestas': len(propuestas),
                'resumen': resumen(base)}
    finally:
        _LOCK.release()


def confirmar_derivacion(base: Path, caso_id: str):
    if not isinstance(caso_id, str) or not caso_id.strip() or len(caso_id) > 80:
        raise ValueError('CASO_ID inválido')
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError('Hay otra operación en curso')
    try:
        con = conectar(base)
        try:
            bloquear_operaciones(con)
            if not instalada(con):
                raise RuntimeError('La base de datos no está inicializada')
            propuestas = {x['CASO_ID']: x for x in cargar_propuestas(con)}
            propuesta = propuestas.get(caso_id)
            if propuesta is None:
                raise ValueError('No hay una propuesta vigente para este caso')
            with tempfile.TemporaryDirectory(prefix='quirored_confirmacion_') as tmp:
                p, programadas, pendientes, bloqueos, canceladas = _preparar(con, Path(tmp), base)
                if caso_id not in {x['CASO_ID'] for x in pendientes} or caso_id in canceladas:
                    raise ValueError('El caso ya no está pendiente o fue cancelado')
                caso = next((c for c in p.casos if c['CASO_ID'] == caso_id), None)
                if caso is None or caso['ESTADO_PROGRAMACION'] != 'PENDIENTE':
                    raise ValueError('La solicitud no está habilitada')
                if caso['PACIENTE_LISTO_SIM'] != 'SI' or caso['PACIENTE_PRESENTE_SIM'] != 'SI':
                    raise ValueError('El paciente figura como no preparado en el modelo')
                origen = caso['UBICACION_OPERATIVA_SIM'] or caso['HOSPITAL_SOLICITANTE']
                destino = propuesta['HOSPITAL_DESTINO']
                if destino == origen or destino not in p.hospitales:
                    raise ValueError('El destino propuesto no corresponde a una derivación válida')
                if not (p.permitido(caso, 'HOSPITAL_CANDIDATO', destino) or
                        p.permitido(caso, 'SOLICITANTE_Y_CANDIDATO', destino)):
                    raise ValueError('La sede no es compatible con la cirugía')
                if p.hospitales[destino]['ESTADO_OPERATIVO'] != 'ACTIVO':
                    raise ValueError('La clínica de destino no está operativa')
                if str(p.hospitales[destino].get('TRASLADOS_PERMITIDOS', '')).upper() != 'SI':
                    raise ValueError('El destino no admite traslados en el modelo')
                from red_vial import bellman_ford, construir_arcos
                arcos = construir_arcos(cargar_fuente(con, 'conexiones_red.csv'),
                                       config(con, 'bloqueos_rutas', []))
                ruta = bellman_ford(arcos, origen, destino)
                if ruta is None:
                    raise ValueError('La derivación ya no tiene una ruta habilitada')
                propuesta_dt = datetime.combine(date.fromisoformat(propuesta['FECHA']),
                                                time.fromisoformat(propuesta['INICIO']))
                salida = datetime.combine(date.fromisoformat(caso['FECHA_MINIMA_OPERABLE_SIM']),
                                          time.fromisoformat(caso['HORA_PREFERIDA_SIM']))
                preparacion = int(propuesta.get('PREPARACION_MIN_SIM', 90))
                if not 0 <= preparacion <= 600:
                    raise ValueError('Preparación de traslado inválida')
                llegada = salida + timedelta(minutes=ruta['tiempo_min_sim'] + preparacion)
                if propuesta_dt < llegada:
                    raise ValueError('La hora propuesta no permite completar el traslado')
                if propuesta_dt.date() >= salida.date() + timedelta(days=7):
                    raise ValueError('La propuesta supera el horizonte de siete días')
                nueva = p.intentar(caso, destino, propuesta_dt.date(), propuesta_dt,
                                   forzar={'SALA': propuesta['SALA_ID']})
                if nueva is None:
                    raise ValueError('Los recursos propuestos ya no están disponibles. Genera nuevas propuestas.')
                nueva.update({'HOSPITAL_ORIGEN': origen,
                              'HOSPITAL_DESTINO': destino,
                              'RUTA_NODOS': ruta['camino'],
                              'TIEMPO_TRASLADO_MIN_SIM': ruta['tiempo_min_sim'],
                              'PREPARACION_MIN_SIM': preparacion,
                              'ESTADO_DERIVACION': 'CONFIRMADA_EN_MODELO_SIMULADO',
                              'METODO_ASIGNACION': nueva['METODO'],
                              'METODO': 'DERIVACION_CONFIRMADA_EN_MODELO'})
                programadas.append(nueva)
                pendientes = [x for x in pendientes if x['CASO_ID'] != caso_id]
                _validar_modelo(p, programadas, pendientes, bloqueos, canceladas,
                                config(con, 'total_casos'))
            paso = int(config(con, 'paso', 0)) + 1
            detalle = {'tipo': 'derivacion_confirmada', 'estado': 'APLICADO',
                       'paso': paso, 'caso_id': caso_id,
                       'hospital_origen': origen, 'hospital_destino': destino,
                       'fecha': nueva['FECHA'], 'inicio': nueva['INICIO'],
                       'ruta': ruta['camino'],
                       'tiempo_traslado_min_sim': ruta['tiempo_min_sim'],
                       'afectadas': 1,
                       'instante_registro': datetime.now().isoformat(timespec='seconds')}
            con.execute('BEGIN')
            try:
                # Las restantes propuestas deben recalcularse para evitar comprometer
                # recursos que la confirmación acaba de reservar.
                guardar_estado(con, programadas, pendientes, [])
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
        return {'estado': 'CONFIRMADA_EN_MODELO_SIMULADO',
                'programacion': nueva, 'evento': detalle,
                'mensaje': 'Derivación confirmada en la simulación y persistida en PostgreSQL.',
                'resumen': resumen(base)}
    finally:
        _LOCK.release()
