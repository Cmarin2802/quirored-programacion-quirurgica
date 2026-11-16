"""Derivaciones simuladas de solicitudes pendientes, red H1/H2/H3.

Este módulo propone asignaciones en otro hospital, nunca traslados reales.
Usa el estado generado por Greedy V1 o por el simulador de eventos.
La confirmación es exclusivamente experimental y requiere --autorizar-simulacion.
No modifica los CSV de origen ni las salidas de módulos anteriores.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta, time
import json
from pathlib import Path
from typing import Any

from motor_programacion_v1 import Programador, leer, escribir, verificar_asignaciones
from motor_reprogramacion_v1 import reconstruir_reservas, validar_reservas
from red_vial import construir_arcos, bellman_ford


def carpeta_datos(base: Path) -> Path:
    for nombre in ('3 Datos', '03_Datos', '01_Datos', '3_Datos', 'Datos'):
        d = base / nombre
        if (d / 'conexiones_red.csv').is_file():
            return d
    raise FileNotFoundError('No se encontró conexiones_red.csv en la carpeta de datos')


def cargar_estado(base: Path, origen: str):
    raiz = base / '8 Motores'
    if origen == 'simulacion':
        carpeta, prog, pend = raiz/'Simulacion_Automatica', 'programaciones_finales.csv', 'pendientes_finales.csv'
    else:
        carpeta, prog, pend = raiz/'Pruebas', 'programaciones_prueba.csv', 'pendientes_prueba.csv'
    if not (carpeta/prog).exists() or not (carpeta/pend).exists():
        raise FileNotFoundError(f'Faltan salidas de {origen} en {carpeta}. Ejecuta primero ese módulo.')
    programadas, pendientes = leer(carpeta/prog), leer(carpeta/pend)
    if not programadas:
        raise ValueError('El cronograma de entrada no contiene cirugías programadas')
    ids_prog = [r['CASO_ID'] for r in programadas]
    ids_pend = [r['CASO_ID'] for r in pendientes]
    if len(set(ids_prog)) != len(ids_prog) or len(set(ids_pend)) != len(ids_pend):
        raise ValueError('Los CSV de entrada tienen identificadores duplicados')
    if set(ids_prog) & set(ids_pend):
        raise ValueError('Hay cirugías simultáneamente pendientes y programadas')
    return programadas, pendientes


def horizonte(caso, dias_busqueda: int):
    dia_min = date.fromisoformat(caso['FECHA_MINIMA_OPERABLE_SIM'])
    hora_pre = time.fromisoformat(caso['HORA_PREFERIDA_SIM'])
    salida_ref = datetime.combine(dia_min, hora_pre)
    return dia_min, salida_ref, dia_min + timedelta(days=dias_busqueda)


def buscar_en_hospital(p: Programador, caso: dict, hospital: str,
                       llegada_minima: datetime, fecha_fin: date, paso_min: int):
    """Busca la primera asignación temporal posible. `intentar` reserva si tiene éxito."""
    for texto_fecha in p.fechas:
        dia = date.fromisoformat(texto_fecha)
        if dia < llegada_minima.date():
            continue
        if dia >= fecha_fin:
            break
        for minuto in range(7*60, 21*60, paso_min):
            inicio = datetime.combine(dia, time(minuto // 60, minuto % 60))
            if inicio < llegada_minima:
                continue
            resultado = p.intentar(caso, hospital, dia, inicio)
            if resultado:
                return resultado
    return None


def planificar(base: Path, origen: str, max_evaluar: int, max_derivaciones: int,
               dias_busqueda: int, paso_min: int, preparacion_min: int,
               bloqueadas: list[str], autorizar_simulacion: bool) -> tuple[dict, Path]:
    if not (max_evaluar > 0 and max_derivaciones > 0 and dias_busqueda > 0 and preparacion_min >= 0):
        raise ValueError('Los límites de evaluación deben ser positivos y la preparación no negativa')
    p = Programador(base)
    base_programadas, base_pendientes = cargar_estado(base, origen)
    if verificar_asignaciones(base_programadas):
        raise ValueError('El cronograma de entrada ya contiene conflictos de solapamiento')
    reconstruir_reservas(p, base_programadas)
    if validar_reservas(p):
        raise ValueError('Las reservas iniciales contienen conflictos')

    arcos = construir_arcos(leer(carpeta_datos(base)/'conexiones_red.csv'), bloqueadas)
    casos = {r['CASO_ID']:r for r in p.casos}
    pendientes_candidatas = []
    for fila in base_pendientes:
        caso = casos.get(fila['CASO_ID'])
        if not caso or caso['ESTADO_PROGRAMACION'] != 'PENDIENTE':
            continue
        if caso['PACIENTE_LISTO_SIM'] != 'SI' or caso['PACIENTE_PRESENTE_SIM'] != 'SI':
            continue
        pendientes_candidatas.append(caso)
    pendientes_candidatas.sort(key=lambda c:(int(c['PRIORIDAD_SIM']), c['FECHA_MINIMA_OPERABLE_SIM'], c['CASO_ID']))

    propuestas = []
    reservadas_virtualmente = []
    conteo_rechazos = Counter()
    for caso in pendientes_candidatas[:max_evaluar]:
        if len(propuestas) >= max_derivaciones:
            break
        origen_h = caso['UBICACION_OPERATIVA_SIM'] or caso['HOSPITAL_SOLICITANTE']
        dia_min, salida_ref, fecha_fin = horizonte(caso, dias_busqueda)
        opciones=[]
        hospitales = sorted(p.hospitales)
        for destino in hospitales:
            if destino == origen_h:
                continue
            if p.hospitales[destino]['ESTADO_OPERATIVO'] != 'ACTIVO':
                conteo_rechazos['HOSPITAL_NO_OPERATIVO'] += 1
                continue
            if not (p.permitido(caso, 'HOSPITAL_CANDIDATO', destino) or
                    p.permitido(caso, 'SOLICITANTE_Y_CANDIDATO', destino)):
                conteo_rechazos['INCOMPATIBLE_ESTRUCTURAL'] += 1
                continue
            ruta = bellman_ford(arcos, origen_h, destino)
            if ruta is None:
                conteo_rechazos['SIN_RUTA_HABILITADA'] += 1
                continue
            # Inicio posible >= fecha/hora mínima + traslado + preparación preoperatoria simulados.
            llegada = salida_ref + timedelta(minutes=ruta['tiempo_min_sim'] + preparacion_min)
            snap_reservas, snap_carga = deepcopy(p.reservas), deepcopy(p.carga)
            prueba = buscar_en_hospital(p, caso, destino, llegada, fecha_fin, paso_min)
            p.reservas, p.carga = snap_reservas, snap_carga
            if prueba is None:
                conteo_rechazos['SIN_RECURSOS_O_HORARIO'] += 1
                continue
            inicio = datetime.fromisoformat(prueba['FECHA']+'T'+prueba['INICIO'])
            opciones.append((inicio, ruta['tiempo_min_sim'], destino, ruta, llegada))
        if not opciones:
            conteo_rechazos['CASOS_SIN_ALTERNATIVA'] += 1
            continue
        _, tiempo, elegido_h, ruta, llegada = min(opciones, key=lambda x:(x[0],x[1],x[2]))
        # Al reservar virtualmente, las siguientes propuestas no pueden ocupar los mismos recursos.
        seleccionado = buscar_en_hospital(p, caso, elegido_h, llegada, fecha_fin, paso_min)
        if seleccionado is None:
            raise RuntimeError('Una propuesta factible dejó de estar disponible al confirmarla virtualmente')
        seleccionado['METODO'] = 'DERIVACION_GREEDY_BELLMAN_FORD_V1'
        reservado = {**seleccionado}
        reservadas_virtualmente.append(reservado)
        propuestas.append({
            'CASO_ID': caso['CASO_ID'],
            'HOSPITAL_SOLICITANTE': caso['HOSPITAL_SOLICITANTE'],
            'UBICACION_ORIGEN': origen_h,
            'HOSPITAL_DESTINO': elegido_h,
            'FECHA': seleccionado['FECHA'],
            'INICIO': seleccionado['INICIO'],
            'SALA_ID': seleccionado['SALA_ID'],
            'RUTA_NODOS': ' -> '.join(ruta['camino']),
            'TIEMPO_TRASLADO_MIN_SIM': int(tiempo),
            'PREPARACION_MIN_SIM': preparacion_min,
            'HORA_MINIMA_ADMISIBLE_SIM': llegada.isoformat(timespec='minutes'),
            'ESTADO_DERIVACION': ('APROBADA_SOLO_EN_SIMULACION' if autorizar_simulacion else
                                  'PROPUESTA_PENDIENTE_DE_AUTORIZACION'),
            'ACLARACION': 'Traslado hipotético; no incluye evaluación médica, ambulancias ni tráfico real'
        })
    # Salida distinta según permiso explícito: en modo propuesta NO alteramos el cronograma base.
    # Verificar también la factibilidad conjunta de propuestas aún no autorizadas.
    reconstruir_reservas(p, base_programadas + reservadas_virtualmente)
    if validar_reservas(p) or verificar_asignaciones(base_programadas + reservadas_virtualmente):
        raise RuntimeError('Existen conflictos entre propuestas virtuales o con el cronograma base')
    resultados = base_programadas + reservadas_virtualmente if autorizar_simulacion else base_programadas
    pendientes_finales = ([r for r in base_pendientes if r['CASO_ID'] not in {x['CASO_ID'] for x in propuestas}]
                         if autorizar_simulacion else base_pendientes)
    reconstruir_reservas(p, resultados)
    errores = verificar_asignaciones(resultados)
    errores_res = validar_reservas(p)
    if errores or errores_res:
        raise RuntimeError(f'Conflictos en derivación: {errores[:3]}, reservas: {errores_res[:3]}')
    if len({r['CASO_ID'] for r in resultados}) != len(resultados):
        raise RuntimeError('Se programó una cirugía más de una vez')
    if {r['CASO_ID'] for r in resultados} & {r['CASO_ID'] for r in pendientes_finales}:
        raise RuntimeError('La misma cirugía figura programada y pendiente')
    salida = base/'8 Motores'/'Pruebas_Derivacion'
    salida.mkdir(parents=True,exist_ok=True)
    columnas_prop = ['CASO_ID','HOSPITAL_SOLICITANTE','UBICACION_ORIGEN','HOSPITAL_DESTINO',
       'FECHA','INICIO','SALA_ID','RUTA_NODOS','TIEMPO_TRASLADO_MIN_SIM',
       'PREPARACION_MIN_SIM','HORA_MINIMA_ADMISIBLE_SIM','ESTADO_DERIVACION','ACLARACION']
    escribir(salida/'propuestas_derivacion.csv', propuestas, columnas_prop)
    escribir(salida/'asignaciones_virtuales.csv', reservadas_virtualmente, list(base_programadas[0]))
    escribir(salida/'programaciones_resultado.csv', sorted(resultados,
             key=lambda x:(x['FECHA'],x['INICIO'],x['CASO_ID'])),list(base_programadas[0]))
    escribir(salida/'pendientes_resultado.csv', pendientes_finales, ['CASO_ID','MOTIVO'])
    resumen = {'origen_programacion':origen,'casos_pendientes_iniciales':len(base_pendientes),
       'pendientes_listos_considerados':min(max_evaluar,len(pendientes_candidatas)),
       'propuestas_viables':len(propuestas),
       'derivaciones_confirmadas_en_simulacion':len(propuestas) if autorizar_simulacion else 0,
       'modo':'AUTORIZACION_EXPERIMENTAL' if autorizar_simulacion else 'SOLO_PROPUESTAS',
       'programaciones_iniciales':len(base_programadas),'programaciones_resultado':len(resultados),
       'pendientes_resultado':len(pendientes_finales), 'solapamientos_detectados':0,
       'bloqueos_viales_aplicados_en_memoria':bloqueadas,'rechazos_en_busqueda':dict(conteo_rechazos),
       'originales_modificados':False,
       'limitacion':'Sin validación médica real, transporte físico, ambulancias ni tiempos geográficos reales'}
    (salida/'resumen_derivacion.json').write_text(json.dumps(resumen,ensure_ascii=False,indent=2),encoding='utf-8')
    return resumen,salida


def main():
    parser=argparse.ArgumentParser(description='Busca alternativas en otros hospitales para cirugías pendientes')
    parser.add_argument('--base',default='.')
    parser.add_argument('--origen',choices=['simulacion','greedy'],default='simulacion')
    parser.add_argument('--max-evaluar',type=int,default=20)
    parser.add_argument('--max-derivaciones',type=int,default=5)
    parser.add_argument('--dias-busqueda',type=int,default=7)
    parser.add_argument('--paso-min',type=int,choices=[30,60],default=60)
    parser.add_argument('--preparacion-min',type=int,default=90)
    parser.add_argument('--bloquear',default='',help='IDs de conexiones separados por comas')
    parser.add_argument('--autorizar-simulacion',action='store_true',
                        help='Confirma propuestas en resultados simulados; NO constituye autorización clínica')
    args=parser.parse_args()
    resumen, salida=planificar(Path(args.base),args.origen,args.max_evaluar,args.max_derivaciones,
               args.dias_busqueda,args.paso_min,args.preparacion_min,
               [v.strip() for v in args.bloquear.split(',') if v.strip()], args.autorizar_simulacion)
    print(json.dumps(resumen,ensure_ascii=False,indent=2))
    print('Resultados:',salida)

if __name__=='__main__':
    main()
