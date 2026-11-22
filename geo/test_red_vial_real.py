"""
Pruebas automatizables de rutas Bellman-Ford y bloqueos viales sobre la red real de San Isidro.
Ejecutar con: python geo/test_red_vial_real.py
"""
from __future__ import annotations

import json
from pathlib import Path

from adaptador_red_vial import (
    calcular_ruta_real,
    obtener_conexiones_adaptadas,
    obtener_payload_api_red,
)

BASE_GEO = Path(__file__).resolve().parent


def ejecutar_pruebas():
    print("=== 1. VERIFICACIÓN DE CONTRATO /api/red ===")
    red = obtener_payload_api_red()
    assert len(red["nodos"]) > 3, "Debe haber nodos hospitalarios e intersecciones reales."
    assert len(red["conexiones"]) > 0, "Debe haber aristas dirigidas."
    print(f"OK -> {len(red['nodos'])} nodos y {len(red['conexiones'])} conexiones dirigidas cargadas.\n")

    print("=== 2. DEMOSTRACIÓN BELLMAN-FORD EN LAS 6 DIRECCIONES ===")
    pares = [
        ("H1", "H2"),
        ("H1", "H3"),
        ("H2", "H1"),
        ("H2", "H3"),
        ("H3", "H1"),
        ("H3", "H2"),
    ]
    resultados_base = {}
    for origen, destino in pares:
        res = calcular_ruta_real(origen, destino)
        assert "sin_ruta" not in res, f"Fallo inesperado: sin ruta entre {origen} y {destino}"
        resultados_base[(origen, destino)] = res
        print(
            f"{origen} -> {destino} | Tiempo: {res['tiempo_min_sim']} min | "
            f"Distancia: {res['distancia_total_m']} m | Nodos: {len(res['camino'])} | "
            f"Vías: {' -> '.join(res['calles'])}"
        )

    print("\n=== 3. PRUEBA DE BLOQUEO VIAL CON RUTA ALTERNATIVA ===")
    ruta_h1_h2 = resultados_base[("H1", "H2")]
    conexiones = obtener_conexiones_adaptadas()
    indice_id = {(c["ORIGEN_NODO"], c["DESTINO_NODO"]): c["CONEXION_ID"] for c in conexiones}
    idx_medio = len(ruta_h1_h2["camino"]) // 2
    tramo_bloqueado = indice_id[(ruta_h1_h2["camino"][idx_medio], ruta_h1_h2["camino"][idx_medio + 1])]

    res_alternativa = calcular_ruta_real("H1", "H2", bloqueadas=[tramo_bloqueado])
    print(f"Tramo bloqueado: {tramo_bloqueado} ({ruta_h1_h2['camino'][idx_medio]} -> {ruta_h1_h2['camino'][idx_medio + 1]})")
    if "sin_ruta" in res_alternativa:
        print("Resultado: SIN RUTA (el acceso de salida de H1 es un cuello de botella único en sentido vial).")
    else:
        assert res_alternativa["camino"] != ruta_h1_h2["camino"], "La ruta alternativa debe diferir de la original."
        assert res_alternativa["tiempo_min_sim"] >= ruta_h1_h2["tiempo_min_sim"], "El desvío no puede ser más rápido."
        print(
            f"Ruta alternativa encontrada -> Tiempo: {res_alternativa['tiempo_min_sim']} min "
            f"(antes {ruta_h1_h2['tiempo_min_sim']} min) | Vías: {' -> '.join(res_alternativa['calles'])}"
        )

    print("\n=== 4. PRUEBA DE BLOQUEO TOTAL DE ACCESO (EXPLICACIÓN 'SIN RUTA') ===")
    salidas_h1 = [c["CONEXION_ID"] for c in conexiones if c["ORIGEN_NODO"] == "H1"]
    res_sin_ruta = calcular_ruta_real("H1", "H3", bloqueadas=salidas_h1)
    assert res_sin_ruta.get("sin_ruta") is True, "Debió retornar sin_ruta=True al bloquear todas las salidas de H1."
    print(f"Salidas bloqueadas de H1: {salidas_h1} -> Resultado confirmado: {res_sin_ruta}")

    evidencia = {
        "rutas_6_direcciones": {f"{o}_a_{d}": v for (o, d), v in resultados_base.items()},
        "prueba_bloqueo_parcial": {"tramo_bloqueado": tramo_bloqueado, "resultado": res_alternativa},
        "prueba_bloqueo_total": {"tramos_bloqueados": salidas_h1, "resultado": res_sin_ruta},
    }
    ruta_evidencia = BASE_GEO / "evidencia_pruebas_rutas.json"
    ruta_evidencia.write_text(json.dumps(evidencia, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nEvidencia guardada en: {ruta_evidencia}")


def test_bellman_ford_y_bloqueos():
    ejecutar_pruebas()


if __name__ == "__main__":
    ejecutar_pruebas()