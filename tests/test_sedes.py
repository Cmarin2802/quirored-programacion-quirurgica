import unittest
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '9 Aplicacion Web/backend'))
from catalogo_sedes import SEDES, nombre_sede, catalogo_publico

class TestCatalogo(unittest.TestCase):
    def test_sedes(self):
        self.assertEqual(set(SEDES), {'H1','H2','H3'})
        self.assertEqual(nombre_sede('H3'), 'Clínica Limatambo')
        self.assertEqual(len(catalogo_publico()), 3)
        for s in catalogo_publico():
            self.assertEqual(s['tipo'], 'CLINICA_PRIVADA')
            self.assertEqual(s['datos_operativos'], 'SIMULADOS')
    def test_recursos(self):
        p = ROOT/'9 Aplicacion Web/frontend/static/recursos_visibles.json'
        r = json.loads(p.read_text(encoding='utf-8'))
        self.assertEqual(len(r), 191)
        self.assertEqual(r['SALA_OBS_01'], 'Sala Obstétrica 1')
        self.assertIn('Dr.', r['MED_001'])
    def test_rutas_csv_no_modificadas(self):
        csv = ROOT/'3 Datos/conexiones_red.csv'
        self.assertIn('VIA_01', csv.read_text(encoding='utf-8-sig'))

if __name__ == '__main__':
    unittest.main()
