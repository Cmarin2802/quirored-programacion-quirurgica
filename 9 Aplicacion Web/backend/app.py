"""API Flask del sistema de coordinación hospitalaria."""
from __future__ import annotations
import os
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
            opciones = [{'recurso_id': c['CONEXION_ID'], 'hospital': '', 'fecha': '',
                         'caso_id': '', 'descripcion': f"{c['ORIGEN_NODO']} → {c['DESTINO_NODO']}"}
                        for c in cargar_fuente(con, 'conexiones_red.csv')
                        if c['ESTADO'] == 'HABILITADA' and c['CONEXION_ID'] not in bloqueadas]
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
    con=conectar(BASE)
    try:
        if not instalada(con):return jsonify(nodos=[],conexiones=[])
        hospital=cargar_fuente(con,'hospitales_red.csv')
        vias=cargar_fuente(con,'puntos_viales_red.csv')
        bloqueadas=set(config(con,'bloqueos_rutas',[]))
        conexiones=cargar_fuente(con,'conexiones_red.csv')
        return jsonify(nodos=[{'id':h['HOSPITAL_ID'],'nombre':nombre_sede(h['HOSPITAL_ID']),'tipo':'HOSPITAL'} for h in hospital]
            + [{'id':v['NODO_VIAL_ID'],'nombre':v['NOMBRE'],'tipo':'INTERSECCION'} for v in vias],
            conexiones=[{'id':x['CONEXION_ID'],'desde':x['ORIGEN_NODO'],'hasta':x['DESTINO_NODO'],
                'peso_min':int(x['TIEMPO_MIN_SIM']),
                'bloqueada':x['CONEXION_ID'] in bloqueadas or x['ESTADO']!='HABILITADA'} for x in conexiones])
    finally:con.close()

@app.get('/api/ruta')
def ruta():
    origen=request.args.get('origen','H1');destino=request.args.get('destino','H3')
    if origen not in ('H1','H2','H3') or destino not in ('H1','H2','H3') or origen==destino:
        return jsonify(error='Origen y destino deben ser hospitales diferentes'),400
    con=conectar(BASE)
    try:
        if not instalada(con):return jsonify(error='Sin inicializar'),409
        filas=cargar_fuente(con,'conexiones_red.csv')
        bloqueadas=config(con,'bloqueos_rutas',[])
    finally:con.close()
    from red_vial import construir_arcos,bellman_ford
    resultado=bellman_ford(construir_arcos(filas,bloqueadas),origen,destino)
    return jsonify(resultado or {'origen':origen,'destino':destino,'sin_ruta':True})

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
