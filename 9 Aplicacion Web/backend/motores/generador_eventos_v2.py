"""Procesamiento de contingencias e incidencias del modelo hospitalario."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import tempfile
from collections import Counter
from itertools import permutations
from datetime import datetime, timedelta
from pathlib import Path

from motor_programacion_v1 import Programador, escribir, leer, verificar_asignaciones
from motor_reprogramacion_v1 import (
    cargar_programaciones, comienzo, evento_cancelacion,
    reconstruir_reservas, validar_reservas,
)
from motor_derivacion_v1 import planificar
from red_vial import construir_arcos, bellman_ford, prim
from algoritmos_integrados import dfs_impacto
from motor_interhospitalario import buscar_asignacion

EVENTOS = (
    'cancelacion', 'ausencia_cirujano', 'limpieza_prolongada',
    'urgencia_saturacion', 'falla_equipo', 'postoperatorio_saturado',
    'hospital_inoperativo', 'bloqueo_ruta', 'sin_alternativa',
)
ESCENARIOS = {
    'ESC_01': 'programacion_normal',
    'ESC_02': 'ausencia_cirujano',
    'ESC_03': 'limpieza_prolongada',
    'ESC_04': 'urgencia_saturacion',
    'ESC_05': 'falla_equipo',
    'ESC_06': 'postoperatorio_saturado',
    'ESC_07': 'hospital_inoperativo',
    'ESC_08': 'bloqueo_ruta',
    'ESC_09': 'sin_alternativa',
}


RECURSOS_EN_FILA = (
    'SALA_ID', 'CIRUJANO_ID', 'ANESTESIOLOGO_ID', 'INSTRUMENTISTA_ID',
    'CIRCULANTE_ID', 'NEONATOLOGO_ID', 'INTENSIVISTA_ID', 'LIMPIEZA_ID',
    'EQUIPO_ANESTESIA_ID', 'EQUIPO_ESPECIALIZADO_ID', 'INSTRUMENTAL_ID',
    'POSTOP_ID',
)
ARCHIVOS_DATOS = (
    'cirugias_red.csv', 'personal_red.csv', 'salas_red.csv',
    'equipos_instrumental_red.csv', 'postoperatorio_red.csv',
    'hospitales_red.csv', 'disponibilidad_red.csv', 'conexiones_red.csv'
)


def carpeta(base: Path, nombres: tuple[str, ...], archivo: str) -> Path:
    for nombre in nombres:
        p = base / nombre
        if (p / archivo).is_file():
            return p
    raise FileNotFoundError(f'No se encontró {archivo} junto al proyecto: {base}')


def hash_file(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as fp:
        for parte in iter(lambda: fp.read(1048576), b''):
            h.update(parte)
    return h.hexdigest()


def datos_iniciales(base: Path):
    datos = carpeta(base, ('3 Datos', '01_Datos', '03_Datos', 'Datos'), 'cirugias_red.csv')
    grafos = carpeta(base, ('4 Grafos', '02_Grafo', '04_Grafos', 'Grafo'), 'grafo_aristas_red.csv')
    base_pruebas = base / '8 Motores' / 'Pruebas'
    archivos = [datos / nombre for nombre in ARCHIVOS_DATOS] + [
        grafos / 'grafo_aristas_red.csv', base_pruebas / 'programaciones_prueba.csv',
        base_pruebas / 'pendientes_prueba.csv',
    ]
    for ruta in archivos:
        if not ruta.exists():
            raise FileNotFoundError(f'Falta archivo para ejecutar el motor: {ruta}')
    return datos, grafos, base_pruebas, archivos


def validar_estado(p: Programador, programadas: list[dict], pendientes: list[dict],
                   bloqueos: set[tuple[str, str]], canceladas: set[str], total: int):
    ids_prog = [r['CASO_ID'] for r in programadas]
    ids_pend = [r['CASO_ID'] for r in pendientes]
    if (len(ids_prog) != len(set(ids_prog)) or len(ids_pend) != len(set(ids_pend))
            or set(ids_prog) & set(ids_pend) or len(ids_prog) + len(ids_pend) != total):
        raise RuntimeError('Hay casos duplicados, omitidos o en dos estados a la vez')
    if canceladas & set(ids_prog):
        raise RuntimeError('Una cirugía cancelada fue programada posteriormente')
    conflictos = verificar_asignaciones(programadas)
    reconstruir_reservas(p, programadas)
    ocupacion = validar_reservas(p)
    programadas_en_bloqueo = [(r['CASO_ID'], r['FECHA'], rid) for r in programadas
        for rid in (r.get(k) for k in RECURSOS_EN_FILA)
        if rid and (r['FECHA'], rid) in bloqueos]
    if conflictos or ocupacion or programadas_en_bloqueo:
        raise RuntimeError(f'Conflictos: {conflictos[:2]} {ocupacion[:2]} {programadas_en_bloqueo[:2]}')


def elegir_fila(rng: random.Random, programadas: list[dict], campo: str = None,
                hospital: str = None, bloqueos: set[tuple[str, str]] = None):
    validas = [r for r in programadas if (not hospital or r['HOSPITAL'] == hospital)
               and (not campo or r.get(campo))
               and (not bloqueos or not campo or (r['FECHA'], r[campo]) not in bloqueos)]
    return rng.choice(sorted(validas, key=lambda r: (r['FECHA'], r['INICIO'], r['CASO_ID']))) if validas else None


def reprogramar(p: Programador, programadas: list[dict], pendientes: list[dict],
                afectadas: list[dict], motivo: str, conexiones, vias_bloqueadas):
    ids = {r['CASO_ID'] for r in afectadas}
    restantes = [r for r in programadas if r['CASO_ID'] not in ids]
    reconstruir_reservas(p, restantes)
    casos = {r['CASO_ID']: r for r in p.casos}
    recuperadas, nuevas_pendientes = [], []
    derivaciones = []
    prioridad = {'EMERGENCIA': 0, 'URGENCIA': 1, 'PRIORITARIA': 2, 'ELECTIVA': 3}
    orden = sorted(afectadas, key=lambda r:(prioridad.get(r['PRIORIDAD'], 5), comienzo(r), r['CASO_ID']))
    for anterior in orden:
        caso = casos[anterior['CASO_ID']]
        nueva = buscar_asignacion(p, caso, anterior['HOSPITAL'], comienzo(anterior),
                                 conexiones, vias_bloqueadas)
        if nueva is not None:
            if nueva['HOSPITAL'] != anterior['HOSPITAL']:
                derivaciones.append({'caso_id': nueva['CASO_ID'],
                                    'origen': anterior['HOSPITAL'],
                                    'destino': nueva['HOSPITAL'],
                                    'ruta': nueva['RUTA_NODOS'],
                                    'tiempo_traslado_min_sim': nueva['TIEMPO_TRASLADO_MIN_SIM']})
            else:
                nueva['METODO'] = 'GREEDY_REPROGRAMACION_EVENTOS_V2'
            recuperadas.append(nueva)
        else:
            nuevas_pendientes.append({'CASO_ID': anterior['CASO_ID'], 'MOTIVO': motivo})
    pendientes = [r for r in pendientes if r['CASO_ID'] not in ids] + nuevas_pendientes
    return restantes + recuperadas, pendientes, len(recuperadas), len(nuevas_pendientes), derivaciones


def marcar_bloqueo(p: Programador, fecha: str, ids: set[str], bloqueos: set):
    nuevos = set()
    for rid in ids:
        if not rid:
            continue
        bloqueos.add((fecha, rid))
        nuevos.add(rid)
        for v in p.disp.get((fecha, rid), []):
            v['ESTADO_PLANIFICADO'] = 'NO_DISPONIBLE'
    return nuevos


def aplicar_evento(p: Programador, programadas: list[dict], pendientes: list[dict],
                   tipo: str, rng: random.Random, bloqueos: set[tuple[str, str]],
                   vias_bloqueadas: set[str], canceladas: set[str],
                   datos: Path, parametros: dict | None = None) -> tuple[list[dict], list[dict], dict]:
    info = {'tipo': tipo, 'estado': 'APLICADO', 'afectadas': 0, 'reprogramadas': 0,
            'nuevas_pendientes': 0, 'recursos_bloqueados': [], 'rutas_bloqueadas': []}
    if parametros is not None:
        info['origen'] = 'REGISTRO_ADMINISTRADOR'
        info['parametros'] = parametros
    if tipo == 'programacion_normal':
        info['estado'] = 'VERIFICADO'; info['detalle'] = 'Validación del cronograma normal sin cambios'
        return programadas, pendientes, info
    if tipo == 'cancelacion':
        candidatos = [r for r in programadas if r['CASO_ID'] not in canceladas]
        if not candidatos:
            info['estado']='OMITIDO_SIN_CANDIDATO'; return programadas, pendientes, info
        if parametros is not None:
            ref = next((r for r in candidatos if r['CASO_ID'] == parametros.get('caso_id')), None)
            if ref is None:
                raise ValueError('La cirugía indicada no está programada')
        else:
            ref = elegir_fila(rng, candidatos)
        programadas, pendientes, detalle = evento_cancelacion(p, programadas, pendientes, ref['CASO_ID'])
        cid = detalle['caso_cancelado']
        canceladas.add(cid)
        for caso in p.casos:
            if caso['CASO_ID'] == cid:
                caso['ESTADO_PROGRAMACION'] = 'CANCELADA'
                break
        info.update({'afectadas': 1, 'caso_id': cid,
                     'hueco_reasignado_a': detalle.get('hueco_reasignado_a'),
                     'detalle':'Cancelación administrativa recibida desde simulación'})
        return programadas, pendientes, info
    if tipo == 'bloqueo_ruta':
        conexiones = leer(datos / 'conexiones_red.csv')
        arcos = construir_arcos(conexiones, list(vias_bloqueadas))
        opciones = [(origen, destino, bellman_ford(arcos, origen, destino))
                    for origen, destino in permutations(('H1','H2','H3'), 2)]
        rutas = [(a,b,r) for a,b,r in opciones if r and len(r['camino']) >= 2]
        if not rutas:
            info['estado']='OMITIDO_SIN_RUTA'; return programadas, pendientes, info
        if parametros is not None:
            seleccion = next((c for c in conexiones if c['CONEXION_ID'] == parametros.get('recurso_id')
                              and c['ESTADO'] == 'HABILITADA' and c['CONEXION_ID'] not in vias_bloqueadas), None)
            if seleccion is None:
                raise ValueError('La vía indicada no está disponible para bloquear')
            n1,n2 = seleccion['ORIGEN_NODO'], seleccion['DESTINO_NODO']
            a,b = parametros.get('origen','H1'), parametros.get('destino','H3')
            ruta = bellman_ford(arcos,a,b)
        else:
            a,b,ruta = rng.choice(rutas)
            n1,n2 = ruta['camino'][:2]
        nuevos = {c['CONEXION_ID'] for c in conexiones
                  if {c['ORIGEN_NODO'],c['DESTINO_NODO']} == {n1,n2}}
        nodos_red = {x['ORIGEN_NODO'] for x in conexiones} | {x['DESTINO_NODO'] for x in conexiones}
        antes_prim = prim(arcos, nodos_red)
        vias_bloqueadas.update(nuevos)
        nuevos_arcos = construir_arcos(conexiones,list(vias_bloqueadas))
        despues = bellman_ford(nuevos_arcos, a, b)
        despues_prim = prim(nuevos_arcos, nodos_red)
        info.update({'origen_hospital':a, 'destino_hospital':b,
                     'ruta_antes':ruta['camino'] if ruta else None,
                     'tiempo_antes_min_sim':ruta['tiempo_min_sim'] if ruta else None,
                     'ruta_despues':despues['camino'] if despues else None,
                     'tiempo_despues_min_sim':despues['tiempo_min_sim'] if despues else None,
                     'rutas_bloqueadas':sorted(nuevos),
                     'prim_conexa_antes':antes_prim['conexo'],
                     'prim_conexa_despues':despues_prim['conexo'],
                     'prim_costo_antes':antes_prim['costo_total_min_sim'],
                     'prim_costo_despues':despues_prim['costo_total_min_sim']})
        return programadas, pendientes, info
    if tipo == 'sin_alternativa':
        
        
        casos = {c['CASO_ID']: c for c in p.casos}
        disponibles = [r for r in pendientes if casos[r['CASO_ID']]['PACIENTE_LISTO_SIM'] == 'SI'
                        and casos[r['CASO_ID']]['PACIENTE_PRESENTE_SIM'] == 'SI'
                        and r['CASO_ID'] not in canceladas]
        if not disponibles:
            info['estado']='OMITIDO_SIN_PENDIENTE'; return programadas, pendientes, info
        elegido = rng.choice(sorted(disponibles,key=lambda x:x['CASO_ID']))
        caso = casos[elegido['CASO_ID']]
        
        
        
        inicio = datetime.fromisoformat(caso['FECHA_MINIMA_OPERABLE_SIM']+'T07:00')
        dias = {x for x in p.fechas if 0 <= (datetime.fromisoformat(x+'T07:00')-inicio).days < 7}
        salas = set(p.salas)
        originales = []
        intentos = 0
        try:
            for (fecha, rid), ventanas in p.disp.items():
                if fecha in dias and rid in salas:
                    for v in ventanas:
                        originales.append((v, v['ESTADO_PLANIFICADO']))
                        v['ESTADO_PLANIFICADO'] = 'NO_DISPONIBLE'
            for hospital in p.hospitales:
                if not (p.permitido(caso,'HOSPITAL_CANDIDATO',hospital) or
                        p.permitido(caso,'SOLICITANTE_Y_CANDIDATO',hospital)):
                    continue
                for fecha in sorted(dias):
                    for minuto in range(7*60,21*60,60):
                        fecha_dt = datetime.fromisoformat(fecha+'T00:00')
                        inicio_intento = fecha_dt + timedelta(minutes=minuto)
                        if inicio_intento < inicio:
                            continue
                        intentos += 1
                        if p.intentar(caso,hospital,fecha_dt.date(),inicio_intento):
                            raise RuntimeError('Una cirugía fue asignada pese al bloqueo total de salas')
        finally:
            for v,estado in originales:
                v['ESTADO_PLANIFICADO'] = estado
        info.update({'estado':'DIAGNOSTICO_CONTRAFACTUAL', 'caso_id':elegido['CASO_ID'],
                     'salas_virtualmente_inhabilitadas':len(salas),
                     'intentos_algoritmicos':intentos,
                     'resultado':'SIN_ALTERNATIVA_CON_TODAS_LAS_SALAS_BLOQUEADAS',
                     'nota':'Calendario restaurado: ningún caso real de simulación fue afectado'})
        return programadas, pendientes, info

    
    
    campo = {'ausencia_cirujano':'CIRUJANO_ID', 'limpieza_prolongada':'SALA_ID',
             'urgencia_saturacion':'SALA_ID', 'falla_equipo':'EQUIPO_ESPECIALIZADO_ID',
             'postoperatorio_saturado':'POSTOP_ID'}.get(tipo)
    hospital = None
    if parametros is not None:
        hospital = parametros.get('hospital')
        fecha_elegida = parametros.get('fecha')
        recurso = parametros.get('recurso_id')
        elegibles = [r for r in programadas if r['HOSPITAL'] == hospital and r['FECHA'] == fecha_elegida
                     and (tipo == 'hospital_inoperativo' or r.get(campo) == recurso)]
        if not elegibles:
            raise ValueError('No hay cirugías programadas para el recurso y fecha indicados')
        ref = sorted(elegibles, key=lambda x: (x['INICIO'], x['CASO_ID']))[0]
        if campo and (ref['FECHA'], ref[campo]) in bloqueos:
            raise ValueError('Ese recurso ya está bloqueado en la fecha indicada')
    else:
        ref = elegir_fila(rng, programadas, campo=campo, hospital=hospital, bloqueos=bloqueos)
    if ref is None:
        info['estado']='OMITIDO_SIN_CANDIDATO'; return programadas, pendientes, info
    fecha = ref['FECHA']
    if tipo == 'hospital_inoperativo':
        hospital_cerrado = ref['HOSPITAL']
        
        
        recursos = ({rid for rid, rr in p.salas.items() if rr['HOSPITAL_ID'] == hospital_cerrado}
                    | {rid for rid, rr in p.personal.items() if rr['HOSPITAL_ID'] == hospital_cerrado}
                    | {rid for rid, rr in p.equipos.items() if rr['HOSPITAL_ID'] == hospital_cerrado}
                    | {rid for rid, rr in p.postop.items() if rr['HOSPITAL_ID'] == hospital_cerrado})
        afectados = [r for r in programadas if r['HOSPITAL'] == hospital_cerrado and r['FECHA'] == fecha]
        
        info['alcance'] = f'Cierre temporal del hospital {ref["HOSPITAL"]} el {fecha}'
    else:
        recursos = {ref[campo]}
        vinculados = set()
        for rid in recursos:
            vinculados.update(dfs_impacto(p.grafo_inverso, rid, {r['CASO_ID'] for r in programadas}))
        asignados = [r for r in programadas if r['FECHA'] == fecha and r.get(campo) in recursos]
        faltantes = {r['CASO_ID'] for r in asignados} - vinculados
        if faltantes:
            raise RuntimeError('El grafo no coincide con las asignaciones de los recursos afectados')
        afectados = [r for r in asignados if r['CASO_ID'] in vinculados]
        info['relaciones_dfs'] = len(afectados)
        if tipo == 'limpieza_prolongada':
            info['alcance']='Bloqueo preventivo de sala por limpieza prolongada durante la jornada simulada'
        elif tipo == 'urgencia_saturacion':
            info['alcance']=f"Reducción de capacidad de sala {ref['HOSPITAL']} durante la jornada con urgencia simulada"
    nuevos = marcar_bloqueo(p,fecha,recursos,bloqueos)
    programadas, pendientes, recuperadas, nuevas_pend, derivaciones = reprogramar(
        p, programadas, pendientes, afectados, f'PENDIENTE_POR_{tipo.upper()}',
        leer(datos/'conexiones_red.csv'), vias_bloqueadas)
    info.update({'fecha':fecha,'hospital':ref['HOSPITAL'],'caso_referencia':ref['CASO_ID'],
                 'recursos_bloqueados':sorted(nuevos),'afectadas':len(afectados),
                 'reprogramadas':recuperadas,'nuevas_pendientes':nuevas_pend,
                 'derivaciones_confirmadas_modelo':derivaciones})
    if tipo == 'urgencia_saturacion':
        
        
        casos = {c['CASO_ID']:c for c in p.casos}
        urgentes = [casos[r['CASO_ID']] for r in pendientes
                    if casos[r['CASO_ID']]['HOSPITAL_SOLICITANTE'] == ref['HOSPITAL']
                    and casos[r['CASO_ID']]['CATEGORIA_PRIORIDAD_SIM'] in ('EMERGENCIA','URGENCIA')
                    and casos[r['CASO_ID']]['PACIENTE_LISTO_SIM']=='SI'
                    and casos[r['CASO_ID']]['PACIENTE_PRESENTE_SIM']=='SI']
        if urgentes:
            urgente = sorted(urgentes,key=lambda c:(int(c['PRIORIDAD_SIM']),c['CASO_ID']))[0]
            nueva = buscar_asignacion(p,urgente,ref['HOSPITAL'],max(comienzo(ref),
                datetime.fromisoformat(urgente['FECHA_MINIMA_OPERABLE_SIM']+'T'+urgente['HORA_PREFERIDA_SIM'])),
                leer(datos/'conexiones_red.csv'),vias_bloqueadas)
            info['urgencia_evaluada'] = urgente['CASO_ID']
            info['estado_urgencia'] = ('PROGRAMADA_DERIVADA' if nueva and nueva['HOSPITAL'] != ref['HOSPITAL']
                else 'PROGRAMADA_LOCAL' if nueva else 'PENDIENTE_PARA_DERIVACION')
            if nueva:
                if nueva['HOSPITAL'] != ref['HOSPITAL']:
                    info['derivaciones_confirmadas_modelo'].append({
                        'caso_id': nueva['CASO_ID'], 'origen': ref['HOSPITAL'],
                        'destino': nueva['HOSPITAL'], 'ruta': nueva['RUTA_NODOS'],
                        'tiempo_traslado_min_sim': nueva['TIEMPO_TRASLADO_MIN_SIM']})
                else:
                    nueva['METODO'] = 'GREEDY_URGENCIA_EVENTO_V2'
                programadas.append(nueva)
                pendientes=[r for r in pendientes if r['CASO_ID'] != urgente['CASO_ID']]
        else:
            info['estado_urgencia']='SIN_SOLICITUD_URGENTE_ELEGIBLE'
    return programadas, pendientes, info


def copiar_insumos(base: Path, temp: Path, datos: Path, grafos: Path,
                   bloqueos: set[tuple[str,str]], canceladas: set[str],
                   prog: list[dict], pend: list[dict]):
    for nombre in ARCHIVOS_DATOS:
        destino = temp / '3 Datos' / nombre
        destino.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(datos / nombre, destino)
    grafo_destino = temp / '4 Grafos' / 'grafo_aristas_red.csv'
    grafo_destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(grafos / 'grafo_aristas_red.csv', grafo_destino)
    
    ventanas = leer(temp / '3 Datos' / 'disponibilidad_red.csv')
    for fila in ventanas:
        if (fila['FECHA'],fila['ID_RECURSO']) in bloqueos:
            fila['ESTADO_PLANIFICADO'] = 'NO_DISPONIBLE'
    escribir(temp / '3 Datos' / 'disponibilidad_red.csv', ventanas, list(ventanas[0]))
    if canceladas:
        casos = leer(temp / '3 Datos' / 'cirugias_red.csv')
        for fila in casos:
            if fila['CASO_ID'] in canceladas:
                fila['ESTADO_PROGRAMACION'] = 'CANCELADA'
        escribir(temp / '3 Datos' / 'cirugias_red.csv', casos, list(casos[0]))
    carpeta_salida = temp / '8 Motores' / 'Simulacion_Automatica'
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    escribir(carpeta_salida / 'programaciones_finales.csv', prog, list(prog[0]))
    escribir(carpeta_salida / 'pendientes_finales.csv', pend, ['CASO_ID','MOTIVO'])


def ejecutar(base: Path, cantidad: int = 6, semilla: int = 2026,
            intervalo_min: int = 180, max_evaluar: int = 20,
            max_derivaciones: int = 5, modo: str = 'automatico') -> dict:
    base = base.resolve()
    if not (1 <= cantidad <= 30 and 1 <= intervalo_min <= 1440 and max_evaluar > 0 and max_derivaciones > 0):
        raise ValueError('Cantidad de eventos: 1..30; intervalo: 1..1440 minutos; límites positivos')
    datos, grafos, pruebas, archivos = datos_iniciales(base)
    huellas_antes = {str(x.relative_to(base)):hash_file(x) for x in archivos}
    p = Programador(base)
    prog, pend = cargar_programaciones(base)
    total = len(p.casos)
    if len(prog)+len(pend) != total:
        raise ValueError('Para ejecutar V2, regenera la prueba Greedy con --limite 1500')
    if total != 1500:
        raise ValueError(f'Este paquete fue validado para el dataset de 1500 casos, llegó {total}')
    rng = random.Random(semilla)
    if modo == 'escenarios':
        tipos = list(ESCENARIOS.values())
    else:
        
        tipos = [rng.choice(EVENTOS) for _ in range(cantidad)]
        
        
        if cantidad >= 3:
            tipos[:2] = ['cancelacion','bloqueo_ruta']
            rng.shuffle(tipos)
    bloqueos, vias_bloqueadas, canceladas = set(), set(), set()
    validar_estado(p,prog,pend,bloqueos,canceladas,total)
    inicio = datetime(2026,11,1,8,0)
    historial = []
    for idx, tipo in enumerate(tipos, start=1):
        antes = len(prog)
        prog,pend,info = aplicar_evento(p,prog,pend,tipo,rng,bloqueos,vias_bloqueadas,canceladas,datos)
        validar_estado(p,prog,pend,bloqueos,canceladas,total)
        info.update({'evento_id': f'EV_SIM_{idx:03d}', 'paso':idx,
                     'instante_simulado':(inicio+timedelta(minutes=idx*intervalo_min)).isoformat(timespec='minutes'),
                     'programadas_antes':antes,'programadas_despues':len(prog),
                     'pendientes_despues':len(pend),
                     'escenario_id': f'ESC_{idx:02d}' if modo == 'escenarios' else None})
        historial.append(info)
    
    
    with tempfile.TemporaryDirectory(prefix='hito2_dinamico_') as tmp:
        raiz_temporal = Path(tmp)
        copiar_insumos(base,raiz_temporal,datos,grafos,bloqueos,canceladas,prog,pend)
        resumen_der,carpeta_der = planificar(
            raiz_temporal,'simulacion',max_evaluar=max_evaluar,
            max_derivaciones=max_derivaciones,dias_busqueda=7,paso_min=60,
            preparacion_min=90,bloqueadas=sorted(vias_bloqueadas),autorizar_simulacion=False)
        carpeta_final=base/'8 Motores'/'Eventos_V2'
        carpeta_final.mkdir(parents=True,exist_ok=True)
        shutil.copy2(carpeta_der/'propuestas_derivacion.csv', carpeta_final/'propuestas_derivacion.csv')
        shutil.copy2(carpeta_der/'asignaciones_virtuales.csv',carpeta_final/'asignaciones_virtuales.csv')
        shutil.copy2(carpeta_der/'resumen_derivacion.json',carpeta_final/'resumen_derivacion.json')
        shutil.copy2(carpeta_der/'programaciones_resultado.csv',carpeta_final/'programaciones_finales.csv')
        shutil.copy2(carpeta_der/'pendientes_resultado.csv',carpeta_final/'pendientes_finales.csv')
    (carpeta_final/'historial_eventos.json').write_text(json.dumps(historial,ensure_ascii=False,indent=2),encoding='utf-8')
    campos = sorted({clave for evento in historial for clave in evento})
    filas = [{k:json.dumps(x.get(k),ensure_ascii=False) if isinstance(x.get(k),(dict,list)) else x.get(k,'') for k in campos}
             for x in historial]
    escribir(carpeta_final/'historial_eventos.csv',filas,campos)
    huellas_despues = {str(x.relative_to(base)):hash_file(x) for x in archivos}
    if huellas_antes != huellas_despues:
        raise RuntimeError('Se alteró un insumo original inesperadamente')
    resultados = leer(carpeta_final/'programaciones_finales.csv')
    pendientes = leer(carpeta_final/'pendientes_finales.csv')
    validar_estado(p,resultados,pendientes,bloqueos,canceladas,total)
    resumen = {
      'modulo':'GENERADOR_EVENTOS_AUTOMATICOS_V2',
      'modo':modo,'semilla':semilla, 'intervalo_virtual_min':intervalo_min,
      'casos_totales':total,'eventos_generados_y_procesados':len(historial),
      'eventos_aplicados':sum(e['estado']=='APLICADO' for e in historial),
      'eventos_diagnostico':sum(e['estado'] in ('DIAGNOSTICO_CONTRAFACTUAL','VERIFICADO') for e in historial),
      'eventos_omitidos':sum(e['estado'].startswith('OMITIDO') for e in historial),
      'programadas_antes':len(cargar_programaciones(base)[0]),
      'programadas_despues':len(resultados),
      'pendientes_despues':len(pendientes),
      'cancelaciones':len(canceladas),
      'reservas_de_recurso_bloqueadas':len(bloqueos),
      'conexiones_viales_bloqueadas':sorted(vias_bloqueadas),
      'propuestas_derivacion':resumen_der['propuestas_viables'],
      'derivaciones_confirmadas':0,
      'conflictos_detectados':0,'insumos_originales_intactos':True,
      'advertencia':'Simulación académica con reloj virtual; no genera ni ejecuta decisiones clínicas reales'
    }
    (carpeta_final/'resumen_eventos_v2.json').write_text(json.dumps(resumen,ensure_ascii=False,indent=2),encoding='utf-8')
    return resumen


def main():
    ap = argparse.ArgumentParser(description='Eventos automáticos y reprogramación H1/H2/H3: pruebas en reloj virtual')
    ap.add_argument('--base',default='.')
    ap.add_argument('--eventos',type=int,default=6, help='Cantidad de eventos automáticos (1..30)')
    ap.add_argument('--semilla',type=int,default=2026, help='Generación reproducible')
    ap.add_argument('--intervalo-min',type=int,default=180, help='Intervalo entre eventos en reloj virtual')
    ap.add_argument('--max-evaluar',type=int,default=20)
    ap.add_argument('--max-derivaciones',type=int,default=5)
    ap.add_argument('--modo',choices=('automatico','escenarios'),default='automatico',
                    help='escenarios: recorre los nueve casos ESC_01..ESC_09')
    args=ap.parse_args()
    resumen=ejecutar(Path(args.base),args.eventos,args.semilla,args.intervalo_min,
                     args.max_evaluar,args.max_derivaciones,args.modo)
    print(json.dumps(resumen,ensure_ascii=False,indent=2))
    print('Resultados: 8 Motores/Eventos_V2')

if __name__=='__main__':
    main()
