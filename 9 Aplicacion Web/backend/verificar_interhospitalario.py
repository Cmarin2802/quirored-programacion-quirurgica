from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

from almacenamiento import conectar, cargar_fuente, config, instalada, cargar_programaciones
from servicio_simulacion import exportar, motor_imports


def ejecutar():
    base = Path(__file__).resolve().parent
    Programador, *_ = motor_imports(base)
    from motor_interhospitalario import buscar_asignacion
    from motor_reprogramacion_v1 import reconstruir_reservas

    with conectar(base) as con:
        if not instalada(con):
            raise RuntimeError('PostgreSQL no contiene datos iniciales')
        total = len(cargar_programaciones(con))
        conexiones = cargar_fuente(con, 'conexiones_red.csv')
        with tempfile.TemporaryDirectory(prefix='verificar_traslados_') as carpeta:
            exportar(con, Path(carpeta), base)
            p = Programador(Path(carpeta))
            resultados = []
            for origen in ('H1', 'H2', 'H3'):
                for destino in ('H1', 'H2', 'H3'):
                    if origen == destino:
                        continue
                    estados = {h: v['ESTADO_OPERATIVO'] for h,v in p.hospitales.items()}
                    for h in p.hospitales:
                        if h != destino:
                            p.hospitales[h]['ESTADO_OPERATIVO'] = 'INOPERATIVO'
                    encontrado = None
                    for caso in p.casos:
                        if caso['HOSPITAL_SOLICITANTE'] != origen:
                            continue
                        if caso['CATEGORIA_PRIORIDAD_SIM'] not in ('EMERGENCIA','URGENCIA'):
                            continue
                        if caso['PACIENTE_LISTO_SIM'] != 'SI' or caso['PACIENTE_PRESENTE_SIM'] != 'SI':
                            continue
                        if caso['FECHA_MINIMA_OPERABLE_SIM'] > p.fechas[-2]:
                            continue
                        if not (p.permitido(caso,'HOSPITAL_CANDIDATO',destino) or
                                p.permitido(caso,'SOLICITANTE_Y_CANDIDATO',destino)):
                            continue
                        resultado = buscar_asignacion(p, caso, origen,
                            datetime.fromisoformat(caso['FECHA_MINIMA_OPERABLE_SIM']+'T'+caso['HORA_PREFERIDA_SIM']),
                            conexiones)
                        if resultado:
                            encontrado = resultado
                            break
                    for h, estado in estados.items():
                        p.hospitales[h]['ESTADO_OPERATIVO'] = estado
                    reconstruir_reservas(p, [])
                    if not encontrado or encontrado['HOSPITAL'] != destino:
                        raise RuntimeError(f'No se validó una derivación {origen} → {destino}')
                    if (encontrado['RUTA_NODOS'][0] != origen or
                            encontrado['RUTA_NODOS'][-1] != destino):
                        raise RuntimeError('Ruta incoherente con el hospital asignado')
                    resultados.append({'origen': origen,'destino': destino,
                        'caso': encontrado['CASO_ID'], 'fecha': encontrado['FECHA'],
                        'hora': encontrado['INICIO'], 'ruta': encontrado['RUTA_NODOS']})
    return {'estado': 'DERIVACIONES_INTERHOSPITALARIAS_VERIFICADAS',
            'direcciones': resultados, 'programadas_existentes': total,
            'tipo_prueba': 'CONTROLADA_SIN_RESERVAS_REALES', 'datos_modificados': False}


if __name__ == '__main__':
    print(json.dumps(ejecutar(), ensure_ascii=False, indent=2))
