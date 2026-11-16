"""Reprogramación de cirugías con Greedy y Backtracking."""
from __future__ import annotations
import argparse
import csv
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from motor_programacion_v1 import Programador, leer, escribir, verificar_asignaciones
from red_vial import construir_arcos, bellman_ford, prim
from algoritmos_integrados import backtracking_asignacion

PERSONAL = ('CIRUJANO_ID','ANESTESIOLOGO_ID','INSTRUMENTISTA_ID','CIRCULANTE_ID',
            'NEONATOLOGO_ID','INTENSIVISTA_ID')
CAMPO_RECURSO = {
    'ausencia_cirujano':'CIRUJANO_ID',
}


def ruta_archivo(base, carpeta, nombre):
    c = next((base/x for x in carpeta if (base/x/nombre).exists()), None)
    if c is None:
        raise FileNotFoundError(f'No se encontró {nombre} en {carpeta}')
    return c/nombre


def cargar_programaciones(base):
    carpeta = ('8 Motores/Pruebas', '03_Pruebas')
    p = ruta_archivo(base, carpeta, 'programaciones_prueba.csv')
    q = ruta_archivo(base, carpeta, 'pendientes_prueba.csv')
    prog, pendientes = leer(p), leer(q)
    if not prog:
        raise ValueError('Faltan programaciones: ejecuta primero el motor Greedy V1')
    if verificar_asignaciones(prog):
        raise ValueError('La programación base tiene conflictos y no debe reprogramarse')
    return prog, pendientes


def comienzo(r):
    return datetime.fromisoformat(r['FECHA']+'T'+r['INICIO'])


def fin_cirugia(r):
    return datetime.fromisoformat(r['FECHA']+'T'+r['FIN_CIRUGIA'])


def fin_limpieza(r):
    return datetime.fromisoformat(r['FECHA']+'T'+r['FIN_LIMPIEZA'])


def intervalos_asignacion(p, r):
    """Reconstituye todas las reservas persistidas, incluso reprocesamiento de instrumental."""
    a = comienzo(r)
    b = fin_cirugia(r)
    c = fin_limpieza(r)
    post = datetime.fromisoformat(r['POSTOP_FIN'])
    out = [(r['SALA_ID'], a, c, False),
           (r['LIMPIEZA_ID'], b, c, False),
           (r['POSTOP_ID'], b, post, False),
           (r['EQUIPO_ANESTESIA_ID'],a,b,False),
           (r['EQUIPO_ESPECIALIZADO_ID'],a,b,False)]
    for campo in PERSONAL:
        if r.get(campo):
            out.append((r[campo],a,b,True))
    rid = r['INSTRUMENTAL_ID']
    instr = p.equipos[rid]
    extra = int(instr['TIEMPO_REPROCESAMIENTO_MIN']) if instr['REQUIERE_REPROCESAMIENTO'] == 'SI' else 0
    out.append((rid,a,b+timedelta(minutes=extra),False))
    return out


def reconstruir_reservas(p, programadas):
    p.reservas = defaultdict(list)
    p.carga = defaultdict(int)
    for r in programadas:
        a = comienzo(r)
        b = fin_cirugia(r)
        duracion = int((b-a).total_seconds()/60)
        for rid, inicio, fin, es_personal in intervalos_asignacion(p,r):
            if not rid:
                continue
            p.reservas[rid].append((inicio, fin))
            if es_personal:
                p.carga[(r['FECHA'], rid)] += duracion


def validar_reservas(p):
    errores = []
    for rid, intervalos in p.reservas.items():
        valores = sorted(intervalos)
        for a,b in zip(valores,valores[1:]):
            if a[1] > b[0]:
                errores.append(rid)
    return errores


def buscar_espacio(p, caso, hospital, primer_dia, dias_busqueda=7, paso_min=60, preferido=None):
    minimo = date.fromisoformat(caso['FECHA_MINIMA_OPERABLE_SIM'])
    desde_dia = max(primer_dia,minimo)
    fechas = [date.fromisoformat(f) for f in p.fechas]
    for d in fechas:
        if d < desde_dia or d >= desde_dia + timedelta(days=dias_busqueda):
            continue
        if preferido and d == preferido.date():
            opciones = [preferido.hour*60+preferido.minute]
        else:
            opciones = []
        opciones += list(range(7*60, 21*60, paso_min))
        for minutos in dict.fromkeys(opciones):
            if minutos % paso_min != 0 and (not preferido or minutos != preferido.hour*60+preferido.minute):
                continue
            
            inicio = datetime.combine(d,time(minutos//60,minutos%60))
            if preferido and inicio < preferido:
                continue
            resultado = p.intentar(caso, hospital, d, inicio)
            if resultado:
                return resultado
    intentos = 0
    for d in fechas:
        if d < desde_dia or d >= desde_dia + timedelta(days=dias_busqueda):
            continue
        alternativas = list(range(7*60, 21*60, paso_min))
        if preferido and d == preferido.date():
            alternativas.insert(0, preferido.hour*60 + preferido.minute)
        for minuto in dict.fromkeys(alternativas):
            inicio = datetime.combine(d, time(minuto//60, minuto%60))
            if preferido and inicio < preferido:
                continue
            resultado = backtracking_asignacion(p, caso, hospital, d, inicio, max_intentos=300)
            if resultado:
                return resultado
            intentos += 1
            if intentos >= 10:
                return None
    return None


def elegir_cancelacion(programadas, caso_id=None):
    if caso_id:
        candidatos = [r for r in programadas if r['CASO_ID'] == caso_id]
    else:
        candidatos = [r for r in programadas if r['PRIORIDAD'] == 'ELECTIVA']
        if not candidatos:
            
            
            
            candidatos = list(programadas)
    if not candidatos:
        raise ValueError('No hay cirugía programada para el evento de prueba')
    return sorted(candidatos,key=lambda r:(comienzo(r),r['CASO_ID']))[0]


def evento_cancelacion(p, programadas, pendientes, caso_id=None):
    cancelada = elegir_cancelacion(programadas,caso_id)
    restantes = [r for r in programadas if r['CASO_ID'] != cancelada['CASO_ID']]
    reconstruir_reservas(p,restantes)
    
    reservas_pend = {r['CASO_ID']:r for r in pendientes}
    candidatos = [p_caso for p_caso in p.casos
          if p_caso['CASO_ID'] in reservas_pend
          and p_caso['HOSPITAL_SOLICITANTE'] == cancelada['HOSPITAL']
          and p_caso['TIPO_PROCEDIMIENTO'] == cancelada['TIPO_PROCEDIMIENTO']
          and p_caso['PACIENTE_LISTO_SIM'] == 'SI'
          and p_caso['PACIENTE_PRESENTE_SIM'] == 'SI'
          and p_caso['ESTADO_PROGRAMACION'] == 'PENDIENTE'
          and date.fromisoformat(p_caso['FECHA_MINIMA_OPERABLE_SIM']) <= comienzo(cancelada).date()]
    candidatos.sort(key=lambda c:(int(c['PRIORIDAD_SIM']),c['FECHA_MINIMA_OPERABLE_SIM'],c['CASO_ID']))
    sustituta = None
    for c in candidatos[:50]:
        sustituta = p.intentar(c,cancelada['HOSPITAL'],comienzo(cancelada).date(),comienzo(cancelada))
        if sustituta:
            break
    if sustituta:
        restantes.append(sustituta)
        pendientes = [r for r in pendientes if r['CASO_ID'] != sustituta['CASO_ID']]
    nuevo = {'CASO_ID':cancelada['CASO_ID'],'MOTIVO':'CANCELADA_POR_EVENTO_SIMULADO'}
    pendientes = [r for r in pendientes if r['CASO_ID'] != cancelada['CASO_ID']] + [nuevo]
    return restantes, pendientes, {
        'evento':'CANCELACION_SOLICITUD_SIMULADA','casos_afectados':1,
        'caso_cancelado':cancelada['CASO_ID'],
        'hueco_reasignado_a':sustituta['CASO_ID'] if sustituta else None,
        'programaciones_preservadas':len(programadas)-1,
        'derivaciones_automaticas':0
    }


def evento_ausencia(p,programadas,pendientes,caso_id=None,dias_busqueda=7):
    elegibles = [r for r in programadas if r['CASO_ID'] == caso_id] if caso_id else list(programadas)
    if not elegibles:
        raise ValueError('La cirugía indicada no está programada')
    elegido = sorted(elegibles,key=lambda r:(comienzo(r),r['CASO_ID']))[0]
    rid = elegido['CIRUJANO_ID']
    dia = elegido['FECHA']
    afectados = [r for r in programadas if r['CIRUJANO_ID'] == rid and r['FECHA'] == dia]
    no_afectados = [r for r in programadas if r not in afectados]
    
    for ventana in p.disp.get((dia,rid),[]):
        ventana['ESTADO_PLANIFICADO'] = 'NO_DISPONIBLE'
    reconstruir_reservas(p,no_afectados)
    casos = {r['CASO_ID']:r for r in p.casos}
    recuperadas = []
    no_reprogramadas = []
    for r in sorted(afectados,key=lambda r:(comienzo(r),r['CASO_ID'])):
        caso = casos[r['CASO_ID']]
        nueva = buscar_espacio(p,caso,r['HOSPITAL'],comienzo(r).date(),
                              dias_busqueda=dias_busqueda,preferido=comienzo(r))
        if nueva:
            nueva['METODO'] = 'GREEDY_REPROGRAMACION_LOCAL_V1'
            recuperadas.append(nueva)
        else:
            no_reprogramadas.append({'CASO_ID':r['CASO_ID'],
                      'MOTIVO':'PENDIENTE_POR_AUSENCIA_CIRUJANO'})
    pendientes = [r for r in pendientes if r['CASO_ID'] not in {x['CASO_ID'] for x in afectados}]
    pendientes += no_reprogramadas
    return no_afectados+recuperadas, pendientes, {
        'evento':'AUSENCIA_CIRUJANO_SIMULADA','recurso_bloqueado':rid,'fecha_bloqueada':dia,
        'casos_afectados':len(afectados),'reprogramadas':len(recuperadas),
        'nuevas_pendientes':len(no_reprogramadas),
        'programaciones_preservadas':len(no_afectados),'derivaciones_automaticas':0
    }


def evento_ruta(base, origen='H1', destino='H3'):
    ruta = ruta_archivo(base,('3 Datos','03_Datos','01_Datos','Datos'), 'conexiones_red.csv')
    conexiones = leer(ruta)
    antes_arcos = construir_arcos(conexiones)
    antes = bellman_ford(antes_arcos,origen,destino)
    if not antes or len(antes['camino']) < 2:
        raise ValueError('No existe una ruta inicial verificable entre hospitales')
    a,b=antes['camino'][:2]
    bloqueados = {c['CONEXION_ID'] for c in conexiones
        if {c['ORIGEN_NODO'],c['DESTINO_NODO']}=={a,b}}
    despues_arcos = construir_arcos(conexiones,bloqueados)
    despues = bellman_ford(despues_arcos,origen,destino)
    mst = prim(despues_arcos)
    return {'evento':'BLOQUEO_RUTA_SIMULADO','origen':origen,'destino':destino,
           'camino_antes':antes['camino'],'minutos_antes':antes['tiempo_min_sim'],
           'conexiones_bloqueadas':sorted(bloqueados),
           'camino_despues':despues['camino'] if despues else None,
           'minutos_despues':despues['tiempo_min_sim'] if despues else None,
           'arbol_prim_conexo':mst['conexo'],
           'costo_mst_simulado':mst['costo_total_min_sim'],
           'observacion':'Sin cambios de cirugía porque V1 no tiene derivaciones programadas'}


def principal():
    cli = argparse.ArgumentParser()
    cli.add_argument('--base',default='.')
    cli.add_argument('--evento',choices=['cancelacion','ausencia_cirujano','bloqueo_ruta'],
                     default='cancelacion')
    cli.add_argument('--caso',default=None,help='ID programado del caso de referencia')
    cli.add_argument('--dias-busqueda',type=int,default=7)
    args=cli.parse_args()
    base=Path(args.base)
    p=Programador(base)
    prog,pend=cargar_programaciones(base)
    original={r['CASO_ID']:dict(r) for r in prog}
    if args.evento=='cancelacion':
        prog_nuevo,pend_nuevo,info=evento_cancelacion(p,prog,pend,args.caso)
    elif args.evento=='ausencia_cirujano':
        prog_nuevo,pend_nuevo,info=evento_ausencia(p,prog,pend,args.caso,args.dias_busqueda)
    else:
        prog_nuevo,pend_nuevo=prog,pend
        info=evento_ruta(base)
        reconstruir_reservas(p,prog_nuevo)
    ids=[r['CASO_ID'] for r in prog_nuevo]
    if len(set(ids))!=len(ids):
        raise RuntimeError('Una cirugía fue programada dos veces')
    conflictos=verificar_asignaciones(prog_nuevo)
    conflictos_reservas=validar_reservas(p)
    if conflictos or conflictos_reservas:
        raise RuntimeError(f'Solapamientos detectados: {conflictos[:3]} {conflictos_reservas[:3]}')
    if args.evento=='cancelacion' and info['caso_cancelado'] in ids:
        raise RuntimeError('La cirugía cancelada sigue programada')
    
    salidas=base/'8 Motores'/'Pruebas_Reprogramacion'
    if not (base/'3 Datos').exists():
        salidas=base/'03_Pruebas_Reprogramacion'
    salidas.mkdir(parents=True,exist_ok=True)
    escribir(salidas/'programaciones_actualizadas.csv',sorted(prog_nuevo,key=lambda r:(r['FECHA'],r['INICIO'],r['CASO_ID'])),list(prog[0]))
    escribir(salidas/'pendientes_actualizados.csv',pend_nuevo,['CASO_ID','MOTIVO'])
    info['programaciones_antes']=len(prog)
    info['programaciones_despues']=len(prog_nuevo)
    info['pendientes_antes']=len(pend)
    info['pendientes_despues']=len(pend_nuevo)
    info['solapamientos_detectados']=0
    info['origen_evento']='SIMULADOR_CONTROLADO'
    info['registros_originales_modificados']=False
    (salidas/'resultado_evento.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(info,ensure_ascii=False,indent=2))
    print('Resultados:',salidas)

if __name__=='__main__':
    principal()
