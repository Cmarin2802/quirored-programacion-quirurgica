"""Pruebas de selección de incidencias activas; no modifican PostgreSQL."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'9 Aplicacion Web'/'backend'))
from gestion_incidencias import _activos, _bloqueos_evento


class TestIncidenciasActivas(unittest.TestCase):
    def test_recurso_y_ruta(self):
        evento = {'paso': 1, 'tipo': 'ausencia_cirujano', 'estado': 'APLICADO',
                  'detalle_json': {'fecha': '2026-11-02', 'recursos_bloqueados': ['MED_001']}}
        ruta = {'paso': 2, 'tipo': 'bloqueo_ruta', 'estado': 'APLICADO',
                'detalle_json': {'rutas_bloqueadas': ['CON_01', 'CON_02']}}
        self.assertEqual(_bloqueos_evento(evento)[0], {('2026-11-02', 'MED_001')})
        self.assertEqual(_bloqueos_evento(ruta)[1], {'CON_01', 'CON_02'})
        self.assertEqual([x['paso'] for x in _activos([evento, ruta])], [1, 2])

    def test_resolucion_elimina_solo_de_lista_activa(self):
        original = {'paso': 1, 'tipo': 'falla_equipo', 'estado': 'APLICADO',
                    'detalle_json': {'fecha': '2026-11-02', 'recursos_bloqueados': ['EQ_1']}}
        resolucion = {'paso': 3, 'tipo': 'resolucion_incidencia', 'estado': 'RESUELTO',
                      'detalle_json': {'resuelve_paso': 1}}
        self.assertEqual(_activos([original, resolucion]), [])
        # Ambos permanecen en el historial, solo se excluye el original de activos.
        self.assertEqual(len([original, resolucion]), 2)

    def test_cancelacion_no_es_reversible(self):
        original = {'paso': 1, 'tipo': 'cancelacion', 'estado': 'APLICADO',
                    'detalle_json': {'caso_id': 'RED_CES_0001'}}
        self.assertEqual(_activos([original]), [])


if __name__ == '__main__':
    unittest.main()
