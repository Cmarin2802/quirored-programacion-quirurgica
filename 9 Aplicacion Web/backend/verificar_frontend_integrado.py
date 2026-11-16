"""Verifica lectura HTTP y archivos del frontend integrado SIN alterar PostgreSQL.
"""
from __future__ import annotations
import json
from pathlib import Path
from app import app
from almacenamiento import resumen

BASE=Path(__file__).resolve().parent

def main():
    inicial=resumen(BASE)
    if not inicial.get('inicializada'):
        raise SystemExit('Falta inicializar la base de datos PostgreSQL')
    app.testing=True
    c=app.test_client()
    for url in ('/', '/static/estilos.css','/static/app.js','/api/estado','/api/fechas',
                '/api/pendientes/candidatos','/api/red','/api/eventos','/api/propuestas',
                '/api/incidencias/opciones?tipo=ausencia_cirujano'):
        r=c.get(url)
        assert r.status_code==200,(url,r.status_code,r.data[:250])
    html=c.get('/').get_data(as_text=True)
    assert 'Cronograma quirúrgico' in html and 'Programar cirugía' in html
    fechas=c.get('/api/fechas').get_json()
    assert fechas['primera']
    params=f'/api/programaciones?hospital=H1&fecha={fechas["primera"]}&limite=200'
    assert c.get(params).status_code==200
    candidatos=c.get('/api/pendientes/candidatos').get_json()
    assert 'total' in candidatos and 'filas' in candidatos
    r=c.post('/api/programaciones/pendiente',json={
        'caso_id':'ID_INEXISTENTE','fecha':'2026-11-27','hora':'08:00'})
    assert r.status_code==409,('Rechazo esperado',r.status_code)
    assert c.post('/api/incidencias', json={'tipo':'NO_EXISTE'}).status_code == 400
    assert c.post('/api/programaciones/jornada',json={'hospital':'H1','fecha':'fecha-invalida','cantidad':8}).status_code == 409
    final=resumen(BASE)
    assert inicial==final,'La verificación modificó la base de datos'
    print(json.dumps({'estado':'FRONTEND_INTEGRADO_CORRECTO',
       'casos':inicial['casos'],'programadas':inicial['programadas'],
       'pendientes':inicial['pendientes'],'vistas':['cronograma','programar'],
       'api_lectura':'OK','cambio_de_estado':'NO_REALIZADO',
       'observacion':'Las pruebas interactivas se realizan después desde el navegador.'},
       ensure_ascii=False,indent=2))

if __name__=='__main__':main()
