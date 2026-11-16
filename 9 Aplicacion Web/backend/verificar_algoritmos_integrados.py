from __future__ import annotations

import json
import tempfile
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

from almacenamiento import conectar, cargar_fuente, cargar_pendientes, cargar_programaciones, config, instalada
from servicio_simulacion import exportar, motor_imports


def ejecutar():
    base = Path(__file__).resolve().parent
    Programador, *_ = motor_imports(base)

    from algoritmos_integrados import (bfs_compatibilidades, dfs_impacto,
                                      seleccionar_dinamica, ford_fulkerson,
                                      backtracking_asignacion)
    from motor_reprogramacion_v1 import reconstruir_reservas
    from motor_programacion_v1 import verificar_asignaciones
    from red_vial import construir_arcos, bellman_ford, prim

    with conectar(base) as con:
        if not instalada(con):
            raise RuntimeError('No se encontraron los datos de PostgreSQL')
        programadas = cargar_programaciones(con)
        pendientes = {r['CASO_ID'] for r in cargar_pendientes(con)}
        bloqueos = {tuple(x) for x in config(con, 'bloqueos_recursos', [])}
        vias = set(config(con, 'bloqueos_rutas', []))
        conexiones = cargar_fuente(con, 'conexiones_red.csv')
        with tempfile.TemporaryDirectory(prefix='verificador_alg_') as temp:
            exportar(con, Path(temp), base)
            p = Programador(temp)
            reconstruir_reservas(p, programadas)
            for fecha, recurso in bloqueos:
                for v in p.disp.get((fecha, recurso), []):
                    v['ESTADO_PLANIFICADO'] = 'NO_DISPONIBLE'
            caso = p.casos[0]
            relaciones, visitados = bfs_compatibilidades(p.grafo_adyacencia, caso['CASO_ID'])
            if not relaciones.get('CANDIDATO_SALA'):
                raise RuntimeError('BFS no encontró salas del grafo')
            rid = next(iter(relaciones['CANDIDATO_SALA']))
            impacto = dfs_impacto(p.grafo_inverso, rid, {r['CASO_ID'] for r in p.casos})
            if caso['CASO_ID'] not in impacto:
                raise RuntimeError('DFS no alcanzó el caso relacionado')
            disponibles = [r for r in p.casos if r['CASO_ID'] in pendientes
                          and r['PACIENTE_LISTO_SIM'] == 'SI' and r['PACIENTE_PRESENTE_SIM'] == 'SI']
            if not disponibles:
                raise RuntimeError('No hay casos pendientes elegibles para prueba')
            elegidos = seleccionar_dinamica(disponibles[:40], 1800, 10)
            if not elegidos:
                raise RuntimeError('Programación Dinámica no seleccionó casos')
            emparejamientos = {}
            dia_flujo = date.fromisoformat(p.fechas[-14])
            for r in disponibles[:15]:
                duracion = int(r['DURACION_ESTIMADA_MIN'])
                hospital = r['HOSPITAL_SOLICITANTE']
                opciones = []
                for sid in p.candidatos[r['CASO_ID']]['CANDIDATO_SALA']:
                    sala = p.salas.get(sid)
                    if not sala or sala['HOSPITAL_ID'] != hospital:
                        continue
                    tipo = ('OBSTETRICA', 'FLEXIBLE') if r['TIPO_PROCEDIMIENTO'] == 'CESAREA' else ('ONCOLOGICA', 'FLEXIBLE')
                    if sala['TIPO_SALA'] not in tipo:
                        continue
                    for minuto in range(7*60, 21*60, 60):
                        inicio = datetime.combine(dia_flujo, time(minuto//60, minuto%60))
                        fin = inicio + timedelta(minutes=duracion + int(sala['TIEMPO_LIMPIEZA_MIN']))
                        if fin.date() == dia_flujo and p.libre(sid, dia_flujo, inicio, fin):
                            opciones.append((sid, inicio.strftime('%H:%M')))
                emparejamientos[r['CASO_ID']] = opciones
            flujo = ford_fulkerson(emparejamientos)
            if not flujo:
                raise RuntimeError('Ford-Fulkerson no obtuvo asignaciones compatibles')
            arcos = construir_arcos(conexiones, vias)
            origenes = {r['ORIGEN_NODO'] for r in conexiones} | {r['DESTINO_NODO'] for r in conexiones}
            arbol = prim(arcos, origenes)
            ruta = bellman_ford(arcos, 'H1', 'H3')
            if not arbol['aristas'] or not ruta:
                raise RuntimeError('Los algoritmos de red no produjeron resultado')
            prueba = None
            for dia_txt in reversed(p.fechas):
                dia = date.fromisoformat(dia_txt)
                for candidato in disponibles[:30]:
                    if candidato['FECHA_MINIMA_OPERABLE_SIM'] > dia_txt:
                        continue
                    hospital = candidato['HOSPITAL_SOLICITANTE']
                    for minuto in range(7*60, 21*60, 60):
                        inicio = datetime.combine(dia, time(minuto//60, minuto%60))
                        prueba = p.intentar(candidato, hospital, dia, inicio)
                        if prueba:
                            reconstruir_reservas(p, programadas)
                            for fecha, recurso in bloqueos:
                                for v in p.disp.get((fecha, recurso), []):
                                    v['ESTADO_PLANIFICADO'] = 'NO_DISPONIBLE'
                            alternativa = backtracking_asignacion(p, candidato, hospital, dia, inicio, max_intentos=1000)
                            if not alternativa:
                                raise RuntimeError('Backtracking falló en una asignación factible')
                            if verificar_asignaciones(programadas + [alternativa]):
                                raise RuntimeError('Backtracking generó solapamientos')
                            break
                    if prueba:
                        break
                if prueba:
                    break
            if not prueba:
                raise RuntimeError('No hay ningún horario válido para probar Greedy y Backtracking')
            return {'estado': 'ALGORITMOS_INTEGRADOS_VERIFICADOS',
                    'casos': len(p.casos), 'programadas_originales': len(programadas),
                    'BFS': len(visitados), 'DFS': len(impacto),
                    'PROGRAMACION_DINAMICA': len(elegidos),
                    'FORD_FULKERSON': len(flujo),
                    'GREEDY': prueba['CASO_ID'],
                    'BACKTRACKING': alternativa['CASO_ID'],
                    'BELLMAN_FORD': ruta['camino'],
                    'PRIM': {'conexo': arbol['conexo'], 'aristas': len(arbol['aristas'])},
                    'datos_modificados': False}


if __name__ == '__main__':
    print(json.dumps(ejecutar(), ensure_ascii=False, indent=2))
