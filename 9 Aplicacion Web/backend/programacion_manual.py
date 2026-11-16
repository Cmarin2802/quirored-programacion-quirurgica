"""Servicio de programación de solicitudes pendientes mediante Greedy."""
from __future__ import annotations

import tempfile
from datetime import date, datetime, time
from pathlib import Path
from psycopg.types.json import Jsonb

from almacenamiento import (conectar,config,cargar_fuente,cargar_pendientes,cargar_programaciones,
                            guardar_estado,cargar_propuestas,poner_config,instalada,resumen,bloquear_operaciones)
from servicio_simulacion import _LOCK,exportar,motor_imports


def solicitudes_pendientes(base: Path, hospital='TODOS', buscar='', limite=35):
    con=conectar(base)
    try:
        if not instalada(con):
            return {'total':0,'filas':[]}
        pendientes={x['CASO_ID']:x['MOTIVO'] for x in cargar_pendientes(con)}
        candidatos=[]
        for c in cargar_fuente(con,'cirugias_red.csv'):
            if c['CASO_ID'] not in pendientes or c['ESTADO_PROGRAMACION'] != 'PENDIENTE':
                continue
            if hospital!='TODOS' and c['HOSPITAL_SOLICITANTE']!=hospital:
                continue
            if buscar and buscar.lower() not in c['CASO_ID'].lower():
                continue
            candidatos.append({
                'caso_id':c['CASO_ID'], 'hospital':c['HOSPITAL_SOLICITANTE'],
                'procedimiento':c['TIPO_PROCEDIMIENTO'],
                'prioridad':c['CATEGORIA_PRIORIDAD_SIM'],
                'fecha_minima':c['FECHA_MINIMA_OPERABLE_SIM'],
                'hora_preferida':c['HORA_PREFERIDA_SIM'],
                'listo':c['PACIENTE_LISTO_SIM']=='SI' and c['PACIENTE_PRESENTE_SIM']=='SI',
                'motivo_pendiente':pendientes[c['CASO_ID']],
            })
        candidatos.sort(key=lambda x:(not x['listo'],x['fecha_minima'],x['caso_id']))
        return {'total':len(candidatos),'filas':candidatos[:limite]}
    finally:
        con.close()


def intentar_pendiente(base:Path,caso_id:str,fecha_texto:str,hora_texto:str):
    if not isinstance(caso_id,str) or not caso_id or len(caso_id)>80:
        raise ValueError('CASO_ID inválido')
    try:
        dia=date.fromisoformat(fecha_texto)
        hora=time.fromisoformat(hora_texto)
    except (TypeError,ValueError):
        raise ValueError('Fecha u hora inválida (AAAA-MM-DD, HH:MM)')
    if not (7<=hora.hour<=20) or hora.minute not in (0,30):
        raise ValueError('Selecciona una hora entre 07:00 y 20:30 en intervalos de 30 minutos')
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError('El sistema está procesando otro evento; vuelve a intentarlo')
    try:
        return _intentar(base.resolve(),caso_id,dia,hora)
    finally:
        _LOCK.release()


def _intentar(base,caso_id,dia,hora):
    (Programador, _escribir,_leer,reconstruir_reservas,_aplicar_evento,
      validar_estado,_copiar_insumos,_planificar)=motor_imports(base)
    from motor_programacion_v1 import verificar_asignaciones
    from motor_interhospitalario import buscar_asignacion
    con=conectar(base)
    try:
        bloquear_operaciones(con)
        if not instalada(con):
            raise RuntimeError('PostgreSQL no contiene los datos iniciales')
        pendientes=cargar_pendientes(con)
        if caso_id not in {x['CASO_ID'] for x in pendientes}:
            raise ValueError('El caso ya no está pendiente o no existe')
        canceladas=set(config(con,'canceladas',[]))
        if caso_id in canceladas:
            raise ValueError('El caso fue cancelado; no puede programarse')
        fuente={r['CASO_ID']:r for r in cargar_fuente(con,'cirugias_red.csv')}
        caso=fuente.get(caso_id)
        if not caso or caso['ESTADO_PROGRAMACION']!='PENDIENTE':
            raise ValueError('La solicitud no está habilitada para programación')
        if caso['PACIENTE_LISTO_SIM']!='SI' or caso['PACIENTE_PRESENTE_SIM']!='SI':
            raise ValueError('El paciente figura como no listo/no presente en el dataset simulado')
        minimo=date.fromisoformat(caso['FECHA_MINIMA_OPERABLE_SIM'])
        if dia<minimo:
            raise ValueError('La fecha seleccionada es anterior a la fecha mínima operable')
        programadas=cargar_programaciones(con)
        bloqueos={tuple(x) for x in config(con,'bloqueos_recursos',[])}
        with tempfile.TemporaryDirectory(prefix='h2_manual_') as t:
            temporal=Path(t)
            exportar(con,temporal,base)
            p=Programador(temporal)
            reconstruir_reservas(p,programadas)
            for fecha,rid in bloqueos:
                for v in p.disp.get((fecha,rid),[]):
                    v['ESTADO_PLANIFICADO']='NO_DISPONIBLE'
            for fila in p.casos:
                if fila['CASO_ID'] in canceladas:
                    fila['ESTADO_PROGRAMACION']='CANCELADA'
            validar_estado(p,programadas,pendientes,bloqueos,canceladas,config(con,'total_casos'))
            elegido=buscar_asignacion(p,caso,caso['HOSPITAL_SOLICITANTE'],
                                     datetime.combine(dia,hora),
                                     cargar_fuente(con,'conexiones_red.csv'),
                                     config(con,'bloqueos_rutas',[]))
            if elegido is None:
                return {'estado':'SIN_CUPO','caso_id':caso_id,
                        'mensaje':'No se encontró una asignación compatible en los próximos 7 días del modelo.',
                        'resumen':resumen(base)}
            nuevas=programadas+[elegido]
            otros=[x for x in pendientes if x['CASO_ID']!=caso_id]
            validar_estado(p,nuevas,otros,bloqueos,canceladas,config(con,'total_casos'))
            errores=verificar_asignaciones(nuevas)
            if errores:
                raise RuntimeError('La nueva asignación genera conflictos; no se guardó')
        paso=int(config(con,'paso',0))+1
        detalle={'tipo':'programacion_manual_existente','estado':'APLICADO',
                 'caso_id':caso_id,'hospital':elegido['HOSPITAL'],
                 'fecha':elegido['FECHA'],'inicio':elegido['INICIO'],
                 'paso':paso,'instante_simulado':f'{elegido["FECHA"]}T{elegido["INICIO"]}',
                 'afectadas':1,'programadas_despues':len(nuevas),
                 'metodo': elegido['METODO'],
                 'hospital_origen': caso['HOSPITAL_SOLICITANTE'],
                 'hospital_destino': elegido['HOSPITAL'],
                 'ruta': elegido.get('RUTA_NODOS'),
                 'tiempo_traslado_min_sim': elegido.get('TIEMPO_TRASLADO_MIN_SIM')}
        con.execute('BEGIN')
        try:
            guardar_estado(con,nuevas,otros,[p for p in cargar_propuestas(con) if p['CASO_ID'] != caso_id])
            con.execute('INSERT INTO eventos VALUES (%s,%s,%s,%s,%s)',(
                paso,detalle['instante_simulado'],detalle['tipo'],detalle['estado'],Jsonb(detalle)))
            poner_config(con,'paso',paso)
            con.execute('COMMIT')
        except Exception:
            con.execute('ROLLBACK')
            raise
        return {'estado':'PROGRAMADA','programacion':elegido,'resumen':resumen(base),
                'mensaje':'Solicitud programada con recursos y horarios compatibles.'}
    finally:
        con.close()
