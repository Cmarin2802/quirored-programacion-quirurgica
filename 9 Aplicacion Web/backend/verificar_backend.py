"""Verifica la integridad de PostgreSQL sin modificar sus registros."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from almacenamiento import conectar, instalada, config, cargar_programaciones, cargar_pendientes, resumen

BASE = Path(__file__).resolve().parent


def main():
    sys.path.insert(0, str(BASE / 'motores'))
    from motor_programacion_v1 import verificar_asignaciones

    with conectar(BASE) as con:
        if not instalada(con):
            raise RuntimeError('PostgreSQL no contiene los datos iniciales')
        progs = cargar_programaciones(con)
        pend = cargar_pendientes(con)
        count = config(con, 'total_casos')
        total_orig = con.execute('''
            SELECT COUNT(*) AS n FROM fuente_registro WHERE archivo = %s
        ''', ('cirugias_red.csv',)).fetchone()['n']
        eventos = con.execute('SELECT COUNT(*) AS n FROM eventos').fetchone()['n']
        nodos = con.execute('SELECT COUNT(*) AS n FROM grafo_nodos').fetchone()['n']
        aristas = con.execute('SELECT COUNT(*) AS n FROM grafo_aristas').fetchone()['n']
        casos = [r['CASO_ID'] for r in progs] + [r['CASO_ID'] for r in pend]
        errores = verificar_asignaciones(progs)
        assert count == total_orig == len(casos) == len(set(casos)) == 1500, 'Casos inconsistentes'
        assert eventos == config(con, 'paso', 0), 'Historial de eventos inconsistente'
        assert nodos == 1704 and aristas == 180502, 'Grafo incompleto'
        assert not errores, 'Conflictos de recursos o horarios'
    print(json.dumps({**resumen(BASE), 'verificacion': 'VERIFICACION_POSTGRESQL_CORRECTA',
                      'nodos': nodos, 'aristas': aristas,
                      'errores_solapamiento': len(errores)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
