"""Comprueba los insumos del motor exportados desde PostgreSQL."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from almacenamiento import conectar, instalada
from servicio_simulacion import exportar, motor_imports

BASE = Path(__file__).resolve().parent


def main():
    with conectar(BASE) as con:
        if not instalada(con):
            raise RuntimeError('PostgreSQL no contiene los datos iniciales')
        with tempfile.TemporaryDirectory(prefix='hospital_pg_test_') as t:
            temporal = Path(t)
            exportar(con, temporal, BASE)
            Programador = motor_imports(BASE)[0]
            programador = Programador(temporal)
            assert len(programador.casos) == 1500
            assert len(programador.candidatos) == 1500
            print(json.dumps({'estado': 'MOTORES_POSTGRESQL_COMPATIBLES',
                              'casos': len(programador.casos),
                              'casos_en_grafo': len(programador.candidatos)},
                             ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
