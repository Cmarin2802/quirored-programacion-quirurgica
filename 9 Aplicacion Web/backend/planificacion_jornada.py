from __future__ import annotations

import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

from psycopg.types.json import Jsonb

from almacenamiento import (conectar, instalada, config, cargar_programaciones,
                            cargar_pendientes, cargar_fuente, cargar_propuestas,
                            guardar_estado, poner_config, resumen, bloquear_operaciones)
from servicio_simulacion import _LOCK, exportar, motor_imports


def planificar_jornada(base: Path, hospital: str, fecha: str, cantidad: int):
    if hospital not in ('H1', 'H2', 'H3'):
        raise ValueError('Hospital inválido')
    try:
        dia = date.fromisoformat(fecha)
    except (TypeError, ValueError):
        raise ValueError('Fecha inválida')
    if not isinstance(cantidad, int) or not 1 <= cantidad <= 15:
        raise ValueError('Cantidad permitida: 1 a 15 cirugías')
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError('Se está procesando otra operación')
    try:
        return _planificar(base.resolve(), hospital, dia, cantidad)
    finally:
        _LOCK.release()


def _planificar(base, hospital, dia, cantidad):
    from algoritmos_integrados import seleccionar_dinamica, ford_fulkerson, backtracking_asignacion
    from motor_reprogramacion_v1 import reconstruir_reservas
    from generador_eventos_v2 import validar_estado
    from motor_interhospitalario import buscar_asignacion, URGENCIAS
    Programador, *_ = motor_imports(base)
    con = conectar(base)
    try:
        bloquear_operaciones(con)
        if not instalada(con):
            raise RuntimeError('Falta inicializar PostgreSQL')
        programadas = cargar_programaciones(con)
        pendientes = cargar_pendientes(con)
        casos_pendientes = {r['CASO_ID'] for r in pendientes}
        canceladas = set(config(con, 'canceladas', []))
        bloqueos = {tuple(r) for r in config(con, 'bloqueos_recursos', [])}
        candidatos = [r for r in cargar_fuente(con, 'cirugias_red.csv')
                     if r['CASO_ID'] in casos_pendientes and r['CASO_ID'] not in canceladas
                     and r['ESTADO_PROGRAMACION'] == 'PENDIENTE'
                     and r['PACIENTE_LISTO_SIM'] == 'SI' and r['PACIENTE_PRESENTE_SIM'] == 'SI'
                     and r['HOSPITAL_SOLICITANTE'] == hospital
                     and r['FECHA_MINIMA_OPERABLE_SIM'] <= dia.isoformat()]
        candidatos.sort(key=lambda x: (int(x['PRIORIDAD_SIM']), x['FECHA_MINIMA_OPERABLE_SIM'], x['CASO_ID']))
        candidatos = candidatos[:70]
        if not candidatos:
            return {'estado': 'SIN_CANDIDATOS', 'evaluadas': 0, 'programadas': 0,
                    'resumen': resumen(base)}
        with tempfile.TemporaryDirectory(prefix='jornada_') as carpeta:
            temp = Path(carpeta)
            exportar(con, temp, base)
            p = Programador(temp)
            reconstruir_reservas(p, programadas)
            for fecha_bloq, rid in bloqueos:
                for ventana in p.disp.get((fecha_bloq, rid), []):
                    ventana['ESTADO_PLANIFICADO'] = 'NO_DISPONIBLE'
            validar_estado(p, programadas, pendientes, bloqueos, canceladas, config(con, 'total_casos'))
            salas = [r for r in p.salas.values() if r['HOSPITAL_ID'] == hospital and str(r['ACTIVA']).upper() in ('SI','TRUE','1')
                     and r['ESTADO_INICIAL'] == 'DISPONIBLE']
            capacidad = 0
            for sala in salas:
                rid = sala['ID_SALA']
                ventanas = p.disp.get((dia.isoformat(), rid), ())
                disponibles = sum(max(0, min(21 * 60, int(v['HORA_FIN'][:2]) * 60 + int(v['HORA_FIN'][3:5])) -
                                     max(7 * 60, int(v['HORA_INICIO'][:2]) * 60 + int(v['HORA_INICIO'][3:5])))
                                  for v in ventanas if v['ESTADO_PLANIFICADO'] == 'DISPONIBLE')
                reservas = sum(int((min(b, datetime.combine(dia, time(21))) -
                                    max(a, datetime.combine(dia, time(7)))).total_seconds() / 60)
                               for a, b in p.reservas[rid] if a.date() == dia)
                capacidad += max(0, disponibles - reservas)
            espacios = {}
            for caso in candidatos:
                cid = caso['CASO_ID']
                duracion = int(caso['DURACION_ESTIMADA_MIN'])
                compatibles = p.candidatos[cid]['CANDIDATO_SALA']
                posibles = []
                for sala in salas:
                    sid = sala['ID_SALA']
                    tipos = ('OBSTETRICA', 'FLEXIBLE') if caso['TIPO_PROCEDIMIENTO'] == 'CESAREA' else ('ONCOLOGICA', 'FLEXIBLE')
                    if sid not in compatibles or sala['TIPO_SALA'] not in tipos:
                        continue
                    for minuto in range(7 * 60, 21 * 60, 60):
                        inicio = datetime.combine(dia, time(minuto // 60, minuto % 60))
                        fin = inicio + timedelta(minutes=duracion + int(sala['TIEMPO_LIMPIEZA_MIN']))
                        if fin.date() == dia and p.libre(sid, dia, inicio, fin):
                            posibles.append((sid, inicio.strftime('%H:%M')))
                espacios[cid] = posibles
            elegibles = [c for c in candidatos if espacios[c['CASO_ID']]]
            seleccionadas = seleccionar_dinamica(elegibles, capacidad, cantidad)
            casos = {r['CASO_ID']: r for r in elegibles}
            opciones = {cid: espacios[cid] for cid in seleccionadas}
            coincidencias = ford_fulkerson(opciones)
            nuevos = []
            metodos = {'GREEDY': 0, 'BACKTRACKING': 0}
            for cid in seleccionadas:
                caso = casos[cid]
                encontrado = None
                if cid in coincidencias:
                    sid, hhmm = coincidencias[cid]
                    h, m = map(int, hhmm.split(':'))
                    encontrado = p.intentar(caso, hospital, dia, datetime.combine(dia, time(h, m)), forzar={'SALA': sid})
                if encontrado is None:
                    for minuto in range(7 * 60, 21 * 60, 60):
                        encontrado = p.intentar(caso, hospital, dia,
                                               datetime.combine(dia, time(minuto // 60, minuto % 60)))
                        if encontrado:
                            break
                if encontrado is None:
                    for minuto in range(7 * 60, 21 * 60, 60):
                        encontrado = backtracking_asignacion(p, caso, hospital, dia,
                                                datetime.combine(dia, time(minuto // 60, minuto % 60)))
                        if encontrado:
                            break
                if encontrado:
                    metodos['BACKTRACKING' if encontrado['METODO'] == 'BACKTRACKING_ASIGNACION' else 'GREEDY'] += 1
                    nuevos.append(encontrado)
            for caso in candidatos:
                if len(nuevos) >= cantidad:
                    break
                if caso['CASO_ID'] in {x['CASO_ID'] for x in nuevos}:
                    continue
                if caso['CATEGORIA_PRIORIDAD_SIM'] not in URGENCIAS:
                    continue
                nueva = buscar_asignacion(
                    p, caso, hospital,
                    max(datetime.combine(dia, time(7)), datetime.fromisoformat(
                        caso['FECHA_MINIMA_OPERABLE_SIM']+'T'+caso['HORA_PREFERIDA_SIM'])),
                    cargar_fuente(con, 'conexiones_red.csv'), config(con,'bloqueos_rutas',[]),
                    dias_busqueda=1)
                if nueva is not None:
                    nuevos.append(nueva)
            if not nuevos:
                return {'estado': 'SIN_CUPO', 'evaluadas': len(candidatos),
                        'seleccionadas_dp': len(seleccionadas),
                        'flujo_maximo': len(coincidencias), 'programadas': 0,
                        'resumen': resumen(base)}
            ids = {r['CASO_ID'] for r in nuevos}
            prog_final = programadas + nuevos
            pend_final = [r for r in pendientes if r['CASO_ID'] not in ids]
            validar_estado(p, prog_final, pend_final, bloqueos, canceladas, config(con, 'total_casos'))
        paso = int(config(con, 'paso', 0)) + 1
        detalle = {'tipo': 'planificacion_jornada', 'estado': 'APLICADO',
                   'hospital': hospital, 'fecha': dia.isoformat(),
                   'evaluadas': len(candidatos), 'seleccionadas_dp': len(seleccionadas),
                   'flujo_maximo': len(coincidencias), 'programadas': len(nuevos),
                   'casos_programados': sorted(ids), 'metodos_asignacion': metodos,
                   'derivaciones_confirmadas_modelo': [
                       {'caso_id': r['CASO_ID'], 'origen': r['HOSPITAL_ORIGEN'],
                        'destino': r['HOSPITAL'], 'ruta': r['RUTA_NODOS'],
                        'tiempo_traslado_min_sim': r['TIEMPO_TRASLADO_MIN_SIM']}
                       for r in nuevos if r.get('HOSPITAL_ORIGEN')],
                   'algoritmos': ['BFS', 'PROGRAMACION_DINAMICA', 'FORD_FULKERSON',
                                  'GREEDY', 'BACKTRACKING'], 'paso': paso}
        instante = datetime.now().isoformat(timespec='seconds')
        detalle['instante_registro'] = instante
        con.execute('BEGIN')
        try:
            guardar_estado(con, prog_final, pend_final,
                           [r for r in cargar_propuestas(con) if r['CASO_ID'] not in ids])
            con.execute('INSERT INTO eventos VALUES (%s, %s, %s, %s, %s)',
                        (paso, instante, 'planificacion_jornada', 'APLICADO', Jsonb(detalle)))
            poner_config(con, 'paso', paso)
            con.execute('COMMIT')
        except Exception:
            con.execute('ROLLBACK')
            raise
        return {'estado': 'APLICADO', 'detalle': detalle, 'resumen': resumen(base)}
    finally:
        con.close()
