"""Panel técnico de lectura: resultados experimentales independientes de PostgreSQL."""
from __future__ import annotations

import csv
import hmac
import os
from datetime import timedelta
from pathlib import Path

from flask import jsonify, redirect, render_template, request, session, url_for


ALGORITMOS = [
    {
        "id": "BFS", "nombre": "BFS", "uso": "Consulta de recursos compatibles de una cirugía",
        "complejidad": "O(grado del caso) en la implementación de un nivel",
        "fuente": "motores/algoritmos_integrados.py · bfs_compatibilidades",
        "entrada": "Casos y relaciones de compatibilidad",
    },
    {
        "id": "DFS", "nombre": "DFS", "uso": "Identificar cirugías impactadas por una incidencia",
        "complejidad": "O(V + E)",
        "fuente": "motores/algoritmos_integrados.py · dfs_impacto",
        "entrada": "Subgrafo de dependencias de recursos",
    },
    {
        "id": "GREEDY", "nombre": "Greedy", "uso": "Programar cirugías priorizadas y distribuir recursos",
        "complejidad": "O(N · D · S · R · log R) estimada en lote",
        "fuente": "motores/motor_programacion_v1.py · Programador",
        "entrada": "Solicitudes quirúrgicas",
    },
    {
        "id": "DINAMICA", "nombre": "Programación dinámica", "uso": "Seleccionar cirugías según capacidad y prioridad",
        "complejidad": "O(N · K · C) tiempo / O(K · C) espacio",
        "fuente": "motores/algoritmos_integrados.py · seleccionar_dinamica",
        "entrada": "Cirugías candidatas y bloques de 30 minutos",
    },
    {
        "id": "FORD_FULKERSON", "nombre": "Ford-Fulkerson", "uso": "Emparejar cirugías con pares sala-horario",
        "complejidad": "O(F · E) para flujo unitario; depende de la red residual",
        "fuente": "motores/algoritmos_integrados.py · ford_fulkerson",
        "entrada": "Casos y bloques candidatos",
    },
    {
        "id": "BACKTRACKING", "nombre": "Backtracking", "uso": "Explorar combinaciones alternativas de recursos",
        "complejidad": "Exponencial en el peor caso, con límite de intentos",
        "fuente": "motores/algoritmos_integrados.py · backtracking_asignacion",
        "entrada": "Casos y alternativas de asignación",
    },
    {
        "id": "BELLMAN_FORD", "nombre": "Bellman-Ford", "uso": "Calcular el trayecto mínimo entre clínicas",
        "complejidad": "O(V · E) tiempo / O(V) espacio",
        "fuente": "motores/red_vial.py · bellman_ford",
        "entrada": "Nodos y tramos de la red vial",
    },
    {
        "id": "PRIM", "nombre": "Prim", "uso": "Comprobar conectividad estructural de la red vial",
        "complejidad": "O(E · log V) tiempo / O(V + E) espacio",
        "fuente": "motores/red_vial.py · prim",
        "entrada": "Nodos y tramos de la red vial",
    },
]


def _cargar_csv(ruta: Path):
    """Los archivos de benchmark son resultados de solo lectura, no operaciones clínicas."""
    if not ruta.is_file():
        return []
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def registrar_area_tecnica(app, base: Path):
    """Incorpora cuatro rutas aisladas; no modifica las rutas quirúrgicas existentes."""
    raiz = Path(base).resolve().parents[1]
    resultados = raiz / "benchmarks"
    clave = os.getenv("QUIRORED_TECNICA_CLAVE", "")
    secreto = os.getenv("QUIRORED_SESSION_SECRET", "")
    configurado = bool(clave and secreto and len(secreto) >= 24)
    if configurado:
        app.secret_key = secreto
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=45),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("QUIRORED_SECURE_COOKIE", "0") == "1",
    )

    def autorizado():
        return configurado and session.get("quirored_tecnica") is True

    def sin_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/tecnica", endpoint="area_tecnica_inicio")
    def area_tecnica_inicio():
        respuesta = app.make_response(render_template(
            "area_tecnica.html", autorizado=autorizado(), configurado=configurado,
            error=False,
        ))
        if not configurado:
            respuesta.status_code = 503
        return sin_cache(respuesta)

    @app.post("/tecnica/acceso", endpoint="area_tecnica_acceso")
    def area_tecnica_acceso():
        if not configurado:
            return sin_cache(app.make_response(("Área técnica no configurada", 503)))
        ingresada = request.form.get("clave", "")[:256]
        if hmac.compare_digest(ingresada.encode("utf-8"), clave.encode("utf-8")):
            session.clear()
            session.permanent = True
            session["quirored_tecnica"] = True
            return sin_cache(redirect(url_for("area_tecnica_inicio"), code=303))
        return sin_cache(app.make_response((render_template(
            "area_tecnica.html", autorizado=False, configurado=True, error=True,
        ), 401)))

    @app.post("/tecnica/salir", endpoint="area_tecnica_salir")
    def area_tecnica_salir():
        if configurado:
            session.pop("quirored_tecnica", None)
        return sin_cache(redirect(url_for("area_tecnica_inicio"), code=303))

    @app.get("/api/tecnica/resultados", endpoint="area_tecnica_resultados")
    def area_tecnica_resultados():
        if not configurado:
            return sin_cache(jsonify(error="Área técnica no configurada")), 503
        if not autorizado():
            return sin_cache(jsonify(error="Acceso técnico requerido")), 401
        payload = {
            "fcfs_greedy": _cargar_csv(resultados / "RESULTADOS.csv"),
            "algoritmos": ALGORITMOS,
            "individuales": _cargar_csv(resultados / "RESULTADOS_ALGORITMOS.csv"),
            "metodologia": "Resultados independientes de PostgreSQL. Tiempos y memoria del equipo de medición.",
        }
        return sin_cache(jsonify(payload))
