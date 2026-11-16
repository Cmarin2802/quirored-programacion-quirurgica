from collections import defaultdict, deque
from datetime import datetime, timedelta


def bfs_compatibilidades(adyacencia, origen):
    cola = deque([(origen, 0)])
    visitados = {origen}
    relaciones = defaultdict(set)
    while cola:
        actual, nivel = cola.popleft()
        if nivel >= 1:
            continue
        for destino, relacion in adyacencia.get(actual, ()):
            relaciones[relacion].add(destino)
            if destino not in visitados:
                visitados.add(destino)
                cola.append((destino, nivel + 1))
    return relaciones, visitados


def dfs_impacto(adyacencia_inversa, recurso, casos_validos):
    pendientes = [recurso]
    visitados = set()
    afectados = set()
    while pendientes:
        actual = pendientes.pop()
        if actual in visitados:
            continue
        visitados.add(actual)
        if actual in casos_validos:
            afectados.add(actual)
        for anterior in adyacencia_inversa.get(actual, ()):
            if anterior not in visitados:
                pendientes.append(anterior)
    return afectados


def seleccionar_dinamica(casos, capacidad, max_casos):
    capacidad = max(0, int(capacidad) // 30)
    max_casos = max(0, int(max_casos))
    estados = {(0, 0): (0, ())}
    for caso in casos:
        peso = (int(caso['DURACION_ESTIMADA_MIN']) + 29) // 30
        prioridad = int(caso['PRIORIDAD_SIM'])
        valor = 200 - 25 * prioridad + min(20, peso)
        nuevos = dict(estados)
        for (cantidad, uso), (puntaje, elegidos) in estados.items():
            clave = (cantidad + 1, uso + peso)
            if clave[0] > max_casos or clave[1] > capacidad:
                continue
            anterior = nuevos.get(clave)
            if anterior is None or puntaje + valor > anterior[0]:
                nuevos[clave] = (puntaje + valor, elegidos + (caso['CASO_ID'],))
        estados = nuevos
    if not estados:
        return []
    _, elegidos = max(estados.values(), key=lambda x: (x[0], len(x[1])))
    return list(elegidos)


def ford_fulkerson(emparejamientos):
    origen = ('S',)
    sumidero = ('T',)
    capacidad = defaultdict(dict)
    for caso, opciones in emparejamientos.items():
        caso_nodo = ('C', caso)
        capacidad[origen][caso_nodo] = 1
        capacidad[caso_nodo][origen] = 0
        for opcion in opciones:
            sala_nodo = ('R',) + tuple(opcion)
            capacidad[caso_nodo][sala_nodo] = 1
            capacidad[sala_nodo][caso_nodo] = 0
            capacidad[sala_nodo][sumidero] = 1
            capacidad[sumidero][sala_nodo] = 0
    while True:
        padres = {origen: None}
        cola = deque([origen])
        while cola and sumidero not in padres:
            u = cola.popleft()
            for v, valor in capacidad[u].items():
                if valor > 0 and v not in padres:
                    padres[v] = u
                    cola.append(v)
        if sumidero not in padres:
            break
        v = sumidero
        while padres[v] is not None:
            u = padres[v]
            capacidad[u][v] -= 1
            capacidad[v][u] = capacidad[v].get(u, 0) + 1
            v = u
    seleccion = {}
    for caso, opciones in emparejamientos.items():
        for opcion in opciones:
            nodo = ('R',) + tuple(opcion)
            if capacidad[nodo].get(('C', caso), 0) == 1:
                seleccion[caso] = opcion
                break
    return seleccion


def backtracking_asignacion(programador, caso, hospital, dia, inicio, max_intentos=2500):
    roles = ('SALA', 'CIRUJANO', 'ANESTESIOLOGO', 'POSTOP', 'INSTRUMENTAL',
             'EQUIPO_ANESTESIA', 'EQUIPO_ESPECIALIZADO', 'INSTRUMENTISTA',
             'CIRCULANTE', 'NEONATOLOGO', 'LIMPIEZA', 'INTENSIVISTA')
    relacion = {'SALA': 'CANDIDATO_SALA', 'CIRUJANO': 'CANDIDATO_CIRUJANO',
                'ANESTESIOLOGO': 'CANDIDATO_ANESTESIOLOGO', 'POSTOP': 'CANDIDATO_POSTOP',
                'INSTRUMENTAL': 'CANDIDATO_INSTRUMENTAL',
                'EQUIPO_ANESTESIA': 'CANDIDATO_EQUIPO',
                'EQUIPO_ESPECIALIZADO': 'CANDIDATO_EQUIPO',
                'INSTRUMENTISTA': 'CANDIDATO_INSTRUMENTISTA',
                'CIRCULANTE': 'CANDIDATO_CIRCULANTE',
                'NEONATOLOGO': 'CANDIDATO_NEONATOLOGO',
                'LIMPIEZA': 'CANDIDATO_LIMPIEZA'}
    obst = caso['TIPO_PROCEDIMIENTO'] == 'CESAREA'
    requeridos = set(roles) - ({'INTENSIVISTA'} if caso['POSTOP_REQUERIDO_SIM'] not in ('UCI_ONCO', 'UCIM') else set())
    if not obst:
        requeridos.discard('NEONATOLOGO')
    opciones = {}
    colecciones = (programador.salas, programador.personal, programador.equipos, programador.postop)
    duracion = int(caso['DURACION_ESTIMADA_MIN'])
    fin = inicio + timedelta(minutes=duracion)
    if fin.date() != dia:
        return None
    for rol in roles:
        if rol not in requeridos:
            continue
        if rol == 'INTENSIVISTA':
            ids = [rid for rid, r in programador.personal.items() if r['ROL'] == 'INTENSIVISTA']
        else:
            ids = programador.candidatos[caso['CASO_ID']][relacion[rol]]
        posibles = []
        for rid in sorted(ids):
            recurso = next((c[rid] for c in colecciones if rid in c), None)
            if recurso is None or recurso['HOSPITAL_ID'] != hospital:
                continue
            if rol == 'SALA':
                tipos = {'OBSTETRICA', 'FLEXIBLE'} if obst else {'ONCOLOGICA', 'FLEXIBLE'}
                if recurso['TIPO_SALA'] not in tipos or str(recurso['ACTIVA']).upper() not in ('SI','TRUE','1'):
                    continue
                hasta = fin + timedelta(minutes=int(recurso['TIEMPO_LIMPIEZA_MIN']))
                desde = inicio
            elif rol == 'POSTOP':
                if recurso['TIPO'] != caso['POSTOP_REQUERIDO_SIM']:
                    continue
                desde = fin
                hasta = fin + timedelta(minutes=int(caso['DURACION_POSTOP_ESTIMADA_MIN_SIM']))
            elif rol == 'INSTRUMENTAL':
                tipo = 'CESAREA' if obst else 'ONCO_ALTA_COMPLEJIDAD'
                if recurso['CATEGORIA'] != 'INSTRUMENTAL' or recurso['TIPO_COMPATIBILIDAD'] != tipo:
                    continue
                extra = int(recurso['TIEMPO_REPROCESAMIENTO_MIN']) if str(recurso['REQUIERE_REPROCESAMIENTO']).upper() in ('SI','TRUE','1') else 0
                desde, hasta = inicio, fin + timedelta(minutes=extra)
            elif rol.startswith('EQUIPO'):
                tipo = 'ANESTESIA' if rol == 'EQUIPO_ANESTESIA' else 'NEONATAL' if obst else 'ONCOLOGIA'
                if recurso['CATEGORIA'] != 'EQUIPO' or recurso['TIPO_COMPATIBILIDAD'] != tipo:
                    continue
                desde, hasta = inicio, fin
            elif rol == 'LIMPIEZA':
                if recurso['ROL'] != 'LIMPIEZA':
                    continue
                desde, hasta = fin, fin + timedelta(minutes=30)
            else:
                if recurso['ROL'] != rol:
                    continue
                if rol == 'CIRUJANO':
                    esp = 'GINECO_OBSTETRICIA' if obst else 'CIRUGIA_ONCOLOGICA'
                    if recurso['ESPECIALIDAD'] != esp:
                        continue
                desde, hasta = inicio, fin
            if desde.date() != hasta.date() or desde >= hasta:
                continue
            if programador.libre(rid, dia, desde, hasta,
                carga_cirugia=duracion if rid in programador.personal and rol != 'LIMPIEZA' else 0):
                posibles.append(rid)
        if not posibles:
            return None
        opciones[rol] = posibles
    orden = sorted(opciones, key=lambda x: len(opciones[x]))
    asignados = {}
    intentos = 0

    def resolver(indice):
        nonlocal intentos
        if intentos >= max_intentos:
            return None
        if indice == len(orden):
            intentos += 1
            resultado = programador.intentar(caso, hospital, dia, inicio, forzar=asignados)
            if resultado:
                resultado['METODO'] = 'BACKTRACKING_ASIGNACION'
            return resultado
        rol = orden[indice]
        for rid in opciones[rol]:
            if rid in asignados.values():
                continue
            asignados[rol] = rid
            resultado = resolver(indice + 1)
            if resultado is not None:
                return resultado
        asignados.pop(rol, None)
        return None

    return resolver(0)
