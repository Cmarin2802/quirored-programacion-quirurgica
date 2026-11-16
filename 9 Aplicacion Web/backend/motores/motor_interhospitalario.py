from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from red_vial import bellman_ford, construir_arcos

URGENCIAS = frozenset(('EMERGENCIA', 'URGENCIA'))


def buscar_asignacion(p, caso, origen, referencia, conexiones, vias_bloqueadas=(),
                      dias_busqueda=7, paso_min=60, preparacion_min=90):
    from motor_reprogramacion_v1 import buscar_espacio

    if origen not in p.hospitales:
        raise ValueError('Hospital de origen inválido')
    if not isinstance(referencia, datetime):
        raise ValueError('Referencia temporal inválida')
    if caso['PACIENTE_LISTO_SIM'] != 'SI' or caso['PACIENTE_PRESENTE_SIM'] != 'SI':
        return None

    minimo = datetime.fromisoformat(caso['FECHA_MINIMA_OPERABLE_SIM'] + 'T07:00')
    referencia = max(referencia, minimo)
    arcos = construir_arcos(conexiones, vias_bloqueadas)
    urgente = caso['CATEGORIA_PRIORIDAD_SIM'] in URGENCIAS
    opciones = []

    for hospital in [origen] + [h for h in sorted(p.hospitales) if h != origen]:
        if p.hospitales[hospital]['ESTADO_OPERATIVO'] != 'ACTIVO':
            continue
        if not (p.permitido(caso, 'HOSPITAL_CANDIDATO', hospital) or
                p.permitido(caso, 'SOLICITANTE_Y_CANDIDATO', hospital)):
            continue
        ruta = None if hospital == origen else bellman_ford(arcos, origen, hospital)
        if hospital != origen and ruta is None:
            continue
        if hospital != origen and str(p.hospitales[hospital].get('TRASLADOS_PERMITIDOS', '')).upper() != 'SI':
            continue
        llegada = referencia if hospital == origen else referencia + timedelta(
            minutes=ruta['tiempo_min_sim'] + preparacion_min)
        if hospital != origen and llegada.minute:
            llegada += timedelta(minutes=60 - llegada.minute)
            llegada = llegada.replace(second=0, microsecond=0)

        reservas = defaultdict(list, {rid: list(intervalos) for rid, intervalos in p.reservas.items()})
        carga = defaultdict(int, p.carga)
        try:
            asignacion = buscar_espacio(p, caso, hospital, llegada.date(),
                                       dias_busqueda=dias_busqueda, paso_min=paso_min,
                                       preferido=llegada)
        finally:
            p.reservas = reservas
            p.carga = carga
        if asignacion is not None:
            inicio = datetime.fromisoformat(asignacion['FECHA'] + 'T' + asignacion['INICIO'])
            opciones.append((inicio, 0 if hospital == origen else ruta['tiempo_min_sim'],
                             hospital, ruta, llegada))

    if not opciones:
        return None
    locales = [o for o in opciones if o[2] == origen]
    if not urgente and locales:
        elegido = locales[0]
    else:
        elegido = min(opciones, key=lambda o: (o[0], o[1], o[2]))

    _, traslado, destino, ruta, llegada = elegido
    definitiva = buscar_espacio(p, caso, destino, llegada.date(),
                               dias_busqueda=dias_busqueda, paso_min=paso_min,
                               preferido=llegada)
    if definitiva is None:
        raise RuntimeError('La asignación propuesta dejó de estar disponible')
    if destino != origen:
        metodo_base = definitiva['METODO']
        definitiva.update({
            'METODO_ASIGNACION': metodo_base,
            'HOSPITAL_ORIGEN': origen,
            'HOSPITAL_DESTINO': destino,
            'RUTA_NODOS': ruta['camino'],
            'TIEMPO_TRASLADO_MIN_SIM': traslado,
            'PREPARACION_MIN_SIM': preparacion_min,
            'ESTADO_DERIVACION': 'CONFIRMADA_EN_MODELO_SIMULADO',
            'METODO': 'ASIGNACION_INTERHOSPITALARIA',
        })
    return definitiva
