"""Servicio de incidencias y simulación conectado a PostgreSQL."""
from __future__ import annotations

import csv
import random
import sys
import tempfile
import threading
from datetime import datetime,timedelta
from pathlib import Path
from psycopg.types.json import Jsonb

from almacenamiento import (conectar, config, cargar_fuente, cargar_programaciones,
    cargar_pendientes, guardar_estado, poner_config, instalada, bloquear_operaciones, resumen)

_LOCK = threading.Lock()
NOMBRES_EVENTOS = ('cancelacion','ausencia_cirujano','limpieza_prolongada',
                   'urgencia_saturacion','falla_equipo','postoperatorio_saturado',
                   'hospital_inoperativo','bloqueo_ruta','sin_alternativa')


def exportar(con, destino: Path, base: Path):
    origen = destino/'3 Datos'
    origen.mkdir(parents=True,exist_ok=True)
    archivos = [r['archivo'] for r in con.execute('SELECT DISTINCT archivo FROM fuente_registro')]
    for archivo in archivos:
        filas = cargar_fuente(con,archivo)
        if not filas:
            continue
        with (origen/archivo).open('w',encoding='utf-8-sig',newline='') as f:
            wr=csv.DictWriter(f,fieldnames=list(filas[0]),delimiter=';')
            wr.writeheader();wr.writerows(filas)
    g = destino/'4 Grafos'
    g.mkdir(parents=True,exist_ok=True)
    with (g/'grafo_aristas_red.csv').open('w', encoding='utf-8-sig', newline='') as archivo:
        wr = csv.writer(archivo, delimiter=';')
        wr.writerow(('ORIGEN_ID', 'DESTINO_ID', 'RELACION', 'TIEMPO_MIN_SIM'))
        with con.cursor() as cur:
            for r in cur.stream('SELECT origen_id, destino_id, relacion, tiempo_min FROM grafo_aristas ORDER BY id_arista'):
                wr.writerow((r['origen_id'], r['destino_id'], r['relacion'],
                             '' if r['tiempo_min'] is None else str(r['tiempo_min'])))
    return origen,g


def motor_imports(base: Path):
    carpeta=str(base/'motores')
    if carpeta not in sys.path:
        sys.path.insert(0,carpeta)
    from motor_programacion_v1 import Programador, escribir, leer
    from motor_reprogramacion_v1 import reconstruir_reservas
    from generador_eventos_v2 import (aplicar_evento,validar_estado,copiar_insumos,
                                      ARCHIVOS_DATOS)
    from motor_derivacion_v1 import planificar
    return Programador,escribir,leer,reconstruir_reservas,aplicar_evento,validar_estado,copiar_insumos,planificar


def simular_paso(base: Path, tipo: str='automatico', max_evaluar: int=20, max_derivaciones: int=5,
                 parametros: dict | None = None):
    """Un solo evento, sin sobrescribir los insumos ni reiniciar el cronograma.

    La exclusión mutua protege el modo de desarrollo con proceso único; para
    producción multi-worker se requerirá bloqueo de tareas/cola externa.
    """
    if tipo != 'automatico' and tipo not in NOMBRES_EVENTOS and tipo != 'programacion_normal':
        raise ValueError('Tipo de evento no soportado')
    if parametros is not None:
        if tipo in ('automatico', 'sin_alternativa', 'programacion_normal'):
            raise ValueError('La incidencia indicada no se puede registrar manualmente')
        if not isinstance(parametros, dict):
            raise ValueError('Parámetros de incidencia inválidos')
        if tipo == 'bloqueo_ruta':
            if not parametros.get('recurso_id'):
                raise ValueError('Debes elegir la conexión afectada')
            if parametros.get('origen') not in ('H1','H2','H3') or parametros.get('destino') not in ('H1','H2','H3'):
                raise ValueError('Hospitales inválidos')
        elif tipo == 'cancelacion':
            if not parametros.get('caso_id'):
                raise ValueError('Debes elegir una cirugía programada')
        else:
            from datetime import date
            try:
                date.fromisoformat(parametros.get('fecha', ''))
            except (ValueError, TypeError):
                raise ValueError('Fecha de incidencia inválida')
            if parametros.get('hospital') not in ('H1', 'H2', 'H3'):
                raise ValueError('Hospital inválido')
            if tipo != 'hospital_inoperativo' and not parametros.get('recurso_id'):
                raise ValueError('Selecciona el recurso afectado')
    if max_evaluar < 1 or max_evaluar > 50 or max_derivaciones < 1 or max_derivaciones > 10:
        raise ValueError('Parámetros fuera del intervalo permitido')
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError('El simulador ya está procesando un evento')
    try:
        return _simular(base.resolve(), tipo, max_evaluar,max_derivaciones, parametros)
    finally:
        _LOCK.release()


def _simular(base, tipo, max_evaluar, max_derivaciones, parametros=None):
    (Programador,escribir,leer,reconstruir_reservas,aplicar_evento,
     validar_estado,copiar_insumos,planificar)=motor_imports(base)
    con=conectar(base)
    try:
        bloquear_operaciones(con)
        if not instalada(con):
            raise RuntimeError('Primero debes inicializar la base de datos')
        paso=config(con,'paso',0)+1
        semilla=config(con,'semilla',2026)
        rng=random.Random(semilla+paso*7919)
        seleccionado=rng.choice(NOMBRES_EVENTOS) if tipo=='automatico' else tipo
        bloqueos={tuple(x) for x in config(con,'bloqueos_recursos',[])}
        vias=set(config(con,'bloqueos_rutas',[]))
        canceladas=set(config(con,'canceladas',[]))
        programadas=cargar_programaciones(con)
        pendientes=cargar_pendientes(con)
        total=config(con,'total_casos')
        with tempfile.TemporaryDirectory(prefix='h2_db_evento_') as carpeta:
            temp=Path(carpeta)
            datos,grafos=exportar(con,temp,base)
            p=Programador(temp)
            reconstruir_reservas(p,programadas)
            for fecha,rid in bloqueos:
                for v in p.disp.get((fecha,rid),[]):
                    v['ESTADO_PLANIFICADO']='NO_DISPONIBLE'
            for caso in p.casos:
                if caso['CASO_ID'] in canceladas:
                    caso['ESTADO_PROGRAMACION']='CANCELADA'
            validar_estado(p,programadas,pendientes,bloqueos,canceladas,total)
            programadas, pendientes, info=aplicar_evento(
                p,programadas,pendientes,seleccionado,rng,bloqueos,vias,canceladas,datos,parametros)
            validar_estado(p,programadas,pendientes,bloqueos,canceladas,total)
            temp_der=temp/'adaptador_derivaciones'
            copiar_insumos(temp,temp_der,datos,grafos,bloqueos,canceladas,programadas,pendientes)
            resumen_der,salida=planificar(temp_der,'simulacion',max_evaluar,max_derivaciones,
                 dias_busqueda=7,paso_min=60,preparacion_min=90,
                 bloqueadas=sorted(vias),autorizar_simulacion=False)
            propuestas=leer(salida/'propuestas_derivacion.csv')
            if len(programadas)+len(pendientes)!=total:
                raise RuntimeError('Se perdió un caso en la simulación')
            instante=(datetime.now() if parametros is not None else
                      datetime(2026,11,1,8,0)+timedelta(minutes=paso*180)).isoformat(timespec='minutes')
            info.update({'paso':paso,'instante_registro' if parametros is not None else 'instante_simulado':instante,
                         'programadas_despues':len(programadas),
                         'pendientes_despues':len(pendientes),'propuestas':len(propuestas),
                         'modo_ejecucion':'registro_administrador' if parametros is not None else
                             'automatico' if tipo=='automatico' else 'evento_determinista'})
            con.execute('BEGIN')
            try:
                guardar_estado(con,programadas,pendientes,propuestas)
                con.execute('INSERT INTO eventos VALUES (%s,%s,%s,%s,%s)',
                            (paso,instante,seleccionado,info['estado'],Jsonb(info)))
                poner_config(con,'paso',paso)
                poner_config(con,'bloqueos_recursos',[list(x) for x in sorted(bloqueos)])
                poner_config(con,'bloqueos_rutas',sorted(vias))
                poner_config(con,'canceladas',sorted(canceladas))
                con.execute('COMMIT')
            except Exception:
                con.execute('ROLLBACK');raise
        return {'evento':info,'resumen':resumen(base),
                'precaucion':'Las derivaciones son propuestas, no autorizaciones clínicas'}
    finally:
        con.close()
