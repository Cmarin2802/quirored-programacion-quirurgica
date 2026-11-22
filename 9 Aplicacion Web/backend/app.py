"""API Flask del sistema de coordinación hospitalaria."""
from __future__ import annotations
import os
from collections import Counter
from datetime import date
from catalogo_sedes import catalogo_publico, nombre_sede
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from almacenamiento import (conectar, config, cargar_fuente, cargar_programaciones,
                             cargar_propuestas, instalada, resumen, reiniciar_estado)
from servicio_simulacion import NOMBRES_EVENTOS,simular_paso,motor_imports
from programacion_manual import solicitudes_pendientes,intentar_pendiente
from planificacion_jornada import planificar_jornada
from gestion_derivaciones import generar_propuestas, confirmar_derivacion
from gestion_incidencias import listar_incidencias_activas, resolver_incidencia

BASE=Path(__file__).resolve().parent
import sys
sys.path.insert(0,str(BASE/'motores'))
app=Flask(__name__,template_folder=str(BASE.parent/'frontend'),static_folder=str(BASE.parent/'frontend'/'static'),static_url_path='/static')
app.config.update(JSON_AS_ASCII=False)
from area_tecnica import registrar_area_tecnica
registrar_area_tecnica(app, BASE)

@app.get('/')
def inicio():
    return render_template('index.html')

@app.get('/api/sedes')
def sedes():
    return jsonify(sedes=catalogo_publico())

@app.get('/api/estado')
def estado():
    return jsonify(resumen(BASE))

@app.get('/api/fechas')
def fechas():
    con=conectar(BASE)
    try:
        if not instalada(con):return jsonify(fechas=[],primera=None)
        filas=con.execute('SELECT fecha::text AS fecha, COUNT(*) AS n FROM programaciones GROUP BY fecha ORDER BY fecha').fetchall()
        return jsonify(fechas=[{'fecha':r['fecha'],'cantidad':r['n']} for r in filas],primera=filas[0]['fecha'] if filas else None,ultima=filas[-1]['fecha'] if filas else None)
    finally:con.close()

@app.get('/api/programaciones')
def programaciones():
    hospital=request.args.get('hospital','TODOS').upper()
    fecha=request.args.get('fecha','')
    if hospital not in ('TODOS','H1','H2','H3'):
        return jsonify(error='Hospital inválido'),400
    if fecha:
        try:date.fromisoformat(fecha)
        except ValueError:return jsonify(error='Fecha inválida'),400
    try:
        limite=min(200,max(1,int(request.args.get('limite','100'))))
        offset=max(0,int(request.args.get('offset','0')))
    except ValueError:
        return jsonify(error='Parámetros numéricos inválidos'),400
    con=conectar(BASE)
    try:
        if not instalada(con):return jsonify(error='Sin inicializar'),409
        clauses=[];params=[]
        if hospital!='TODOS':clauses.append('hospital=%s');params.append(hospital)
        if fecha:clauses.append('fecha=%s');params.append(fecha)
        cond=('WHERE '+' AND '.join(clauses)) if clauses else ''
        total=con.execute('SELECT COUNT(*) AS count FROM programaciones '+cond,params).fetchone()['count']
        filas=con.execute('SELECT fila_json FROM programaciones '+cond+
            ' ORDER BY fecha,inicio,caso_id LIMIT %s OFFSET %s',params+[limite,offset])
        return jsonify(total=total,filas=[r['fila_json'] for r in filas])
    finally:con.close()

@app.get('/api/pendientes/candidatos')
def candidatos():
    hospital=request.args.get('hospital','TODOS').upper()
    if hospital not in ('TODOS','H1','H2','H3'):
        return jsonify(error='Hospital inválido'),400
    buscar=request.args.get('buscar','').strip()[:80]
    return jsonify(solicitudes_pendientes(BASE,hospital,buscar,limite=40))

@app.post('/api/programaciones/pendiente')
def programar_pendiente():
    data=request.get_json(silent=True) or {}
    try:
        resultado=intentar_pendiente(BASE,data.get('caso_id'),data.get('fecha'),data.get('hora'))
        return jsonify(resultado)
    except (RuntimeError,ValueError,FileNotFoundError) as e:
        return jsonify(error=str(e)),409
    except Exception:
        app.logger.exception('Error programando solicitud pendiente')
        return jsonify(error='Error interno; no se confirmó la programación'),500

@app.post('/api/programaciones/jornada')
def jornada():
    data = request.get_json(silent=True) or {}
    try:
        cantidad = int(data.get('cantidad', 8))
        return jsonify(planificar_jornada(BASE, data.get('hospital'), data.get('fecha'), cantidad))
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        return jsonify(error=str(e)), 409
    except Exception:
        app.logger.exception('Error en planificación de jornada')
        return jsonify(error='Error interno; no se guardó la planificación'), 500


TIPOS_INCIDENCIAS = {
    'ausencia_cirujano': 'CIRUJANO_ID', 'limpieza_prolongada': 'SALA_ID',
    'urgencia_saturacion': 'SALA_ID', 'falla_equipo': 'EQUIPO_ESPECIALIZADO_ID',
    'postoperatorio_saturado': 'POSTOP_ID', 'hospital_inoperativo': None,
    'bloqueo_ruta': None, 'cancelacion': 'CASO_ID'
}


@app.get('/api/incidencias/opciones')
def opciones_incidencias():
    tipo = request.args.get('tipo', '')
    if tipo not in TIPOS_INCIDENCIAS:
        return jsonify(error='Tipo de incidencia inválido'), 400
    con = conectar(BASE)
    try:
        if tipo == 'bloqueo_ruta':
            bloqueadas = set(config(con, 'bloqueos_rutas', []))
            nodos = {h: nombre_sede(h) for h in ('H1', 'H2', 'H3')}
            nodos.update({p['NODO_VIAL_ID']: p['NOMBRE']
                          for p in cargar_fuente(con, 'puntos_viales_red.csv')})
            opciones = []
            for tramo in cargar_fuente(con, 'conexiones_red.csv'):
                if tramo['ESTADO'] != 'HABILITADA' or tramo['CONEXION_ID'] in bloqueadas:
                    continue
                calle = (tramo.get('NOMBRE_VIA') or '').strip()
                if not calle or 'sin nombre' in calle.lower():
                    calle = 'Conexión vial sin nombre registrado'
                origen = nodos.get(tramo['ORIGEN_NODO'], 'Intersección sin referencia')
                destino = nodos.get(tramo['DESTINO_NODO'], 'Intersección sin referencia')
                descripcion = f'{calle} · desde {origen} hacia {destino}'
                opciones.append({'recurso_id': tramo['CONEXION_ID'], 'hospital': '',
                                 'fecha': '', 'caso_id': '', 'descripcion': descripcion,
                                 'calle': calle, 'origen_nombre': origen, 'destino_nombre': destino,
                                 'distancia_m': round(float(tramo.get('DISTANCIA_M') or 0), 1)})
            repetidas = Counter(x['descripcion'] for x in opciones)
            secciones = Counter()
            for opcion in opciones:
                descripcion = opcion['descripcion']
                if repetidas[descripcion] > 1:
                    secciones[descripcion] += 1
                    opcion['descripcion'] += f' · sección {secciones[descripcion]}/{repetidas[descripcion]}'
            opciones.sort(key=lambda x: x['descripcion'].casefold())
        else:
            campo = TIPOS_INCIDENCIAS[tipo]
            vistas = set()
            opciones = []
            for r in cargar_programaciones(con):
                rid = r.get(campo) if campo else ''
                clave = (r['HOSPITAL'], r['FECHA'], rid if campo else '')
                if clave in vistas or (campo and not rid):
                    continue
                vistas.add(clave)
                opciones.append({'recurso_id': rid if campo != 'CASO_ID' else '',
                                 'caso_id': r['CASO_ID'] if campo == 'CASO_ID' else '',
                                 'hospital': r['HOSPITAL'], 'fecha': r['FECHA'],
                                 'descripcion': rid or f"Hospital {r['HOSPITAL']}"})
            opciones.sort(key=lambda x: (x['fecha'], x['hospital'], x['descripcion']))
        return jsonify(opciones=opciones)
    finally:
        con.close()


@app.post('/api/incidencias')
def registrar_incidencia():
    data = request.get_json(silent=True) or {}
    tipo = data.get('tipo')
    if tipo not in TIPOS_INCIDENCIAS:
        return jsonify(error='Tipo de incidencia no soportado'), 400
    try:
        return jsonify(simular_paso(BASE, tipo=tipo, parametros={
            'hospital': data.get('hospital'), 'fecha': data.get('fecha'),
            'recurso_id': data.get('recurso_id'), 'caso_id': data.get('caso_id'),
            'origen': data.get('origen', 'H1'), 'destino': data.get('destino', 'H3')}))
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        return jsonify(error=str(e)), 409
    except Exception:
        app.logger.exception('Error registrando incidencia')
        return jsonify(error='Error interno; no se confirmó la incidencia'), 500


@app.get('/api/incidencias/activas')
def incidencias_activas():
    return jsonify(listar_incidencias_activas(BASE))

@app.post('/api/incidencias/resolver')
def resolver_bloqueo():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(resolver_incidencia(BASE, data.get('paso')))
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        return jsonify(error=str(e)), 409
    except Exception:
        app.logger.exception('Error resolviendo incidencia')
        return jsonify(error='Error interno; no se resolvió la incidencia'), 500

@app.post('/api/derivaciones/proponer')
def proponer_derivaciones():
    try:
        return jsonify(generar_propuestas(BASE))
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        return jsonify(error=str(e)), 409
    except Exception:
        app.logger.exception('Error generando propuestas de derivación')
        return jsonify(error='Error interno; no se actualizaron las propuestas'), 500

@app.post('/api/derivaciones/confirmar')
def confirmar_propuesta():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(confirmar_derivacion(BASE, data.get('caso_id')))
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        return jsonify(error=str(e)), 409
    except Exception:
        app.logger.exception('Error confirmando derivación')
        return jsonify(error='Error interno; no se confirmó la derivación'), 500

@app.get('/api/eventos')
def eventos():
    con=conectar(BASE)
    try:
        if not instalada(con):return jsonify([])
        return jsonify([r['detalle_json'] for r in con.execute(
           'SELECT detalle_json FROM eventos ORDER BY paso DESC LIMIT 25')])
    finally:con.close()

@app.get('/api/propuestas')
def propuestas():
    con=conectar(BASE)
    try:return jsonify(cargar_propuestas(con) if instalada(con) else [])
    finally:con.close()

@app.get('/api/red')
def red():
    from red_operativa import coordenadas_sedes, habilitada
    con = conectar(BASE)
    try:
        if not instalada(con):
            return jsonify(nodos=[], conexiones=[])
        sedes = cargar_fuente(con, 'hospitales_red.csv')
        intersecciones = cargar_fuente(con, 'puntos_viales_red.csv')
        tramos = cargar_fuente(con, 'conexiones_red.csv')
        bloqueos = set(config(con, 'bloqueos_rutas', []))
        geo_sedes = coordenadas_sedes()
        nodos = []
        for sede in sedes:
            hid = sede['HOSPITAL_ID']
            item = {'id': hid, 'nombre': nombre_sede(hid), 'tipo': 'HOSPITAL'}
            if hid in geo_sedes:
                item.update(lat=float(geo_sedes[hid]['LATITUD']), lon=float(geo_sedes[hid]['LONGITUD']))
            nodos.append(item)
        for punto in intersecciones:
            item = {'id': punto['NODO_VIAL_ID'], 'nombre': punto['NOMBRE'], 'tipo': 'INTERSECCION'}
            if punto.get('LATITUD') and punto.get('LONGITUD'):
                item.update(lat=float(punto['LATITUD']), lon=float(punto['LONGITUD']))
            nodos.append(item)
        conexiones = [{
            'id': tramo['CONEXION_ID'], 'desde': tramo['ORIGEN_NODO'],
            'hasta': tramo['DESTINO_NODO'],
            'peso_min': round(float(tramo['TIEMPO_MIN_SIM']), 3),
            'via': tramo.get('NOMBRE_VIA', 'Vía sin nombre'),
            'bloqueada': tramo['CONEXION_ID'] in bloqueos or tramo['ESTADO'] != 'HABILITADA',
        } for tramo in tramos]
        return jsonify(nodos=nodos, conexiones=conexiones, red_real=habilitada())
    finally:
        con.close()


@app.get('/api/ruta')
def ruta():
    origen = request.args.get('origen', 'H1')
    destino = request.args.get('destino', 'H3')
    if origen not in ('H1', 'H2', 'H3') or destino not in ('H1', 'H2', 'H3') or origen == destino:
        return jsonify(error='Selecciona dos clínicas diferentes'), 400
    con = conectar(BASE)
    try:
        if not instalada(con):
            return jsonify(error='No se han cargado los datos'), 409
        tramos = cargar_fuente(con, 'conexiones_red.csv')
        bloqueos = config(con, 'bloqueos_rutas', [])
    finally:
        con.close()
    from red_vial import construir_arcos, bellman_ford
    from red_operativa import enriquecer_ruta
    resultado = bellman_ford(construir_arcos(tramos, bloqueos), origen, destino)
    return jsonify(enriquecer_ruta(resultado, tramos) or {
        'origen': origen, 'destino': destino, 'sin_ruta': True,
    })


@app.post('/api/simulacion/paso')
def avanzar():
    data=request.get_json(silent=True) or {}
    tipo=data.get('tipo','automatico')
    try:
        resultado=simular_paso(BASE,tipo=tipo)
        return jsonify(resultado)
    except (RuntimeError,ValueError,FileNotFoundError) as e:
        return jsonify(error=str(e)),409
    except Exception:
        app.logger.exception('Error procesando evento')
        return jsonify(error='Error interno al procesar el evento; no se confirmó el cambio'),500

@app.post('/api/simulacion/reiniciar')
def reiniciar():
    if os.environ.get('HOSPITAL_DEMO_MODE','0') != '1':
        return jsonify(error='Deshabilitado fuera del modo local de demostración'),403
    try:return jsonify(reiniciar_estado(BASE))
    except RuntimeError as e:return jsonify(error=str(e)),409

if __name__=='__main__':
    print('Abrir http://127.0.0.1:5000 — solo desarrollo local')
    app.run(host='127.0.0.1',port=5000,debug=False,threaded=True)
