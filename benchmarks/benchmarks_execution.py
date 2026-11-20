from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time as time_mod
import tracemalloc
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parent.parent
RUTA_MOTORES = RAIZ_REPO / "9 Aplicacion Web" / "backend" / "motores"
RUTA_BENCH = Path(__file__).resolve().parent

for ruta in (RUTA_MOTORES, RUTA_BENCH):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

from motor_programacion_v1 import (  # noqa: E402  # type: ignore
    Programador,
    minutos,
    si,
    verificar_asignaciones,
)
from programador_fcfs import ProgramadorFCFS, seleccionar_muestra  # noqa: E402  # type: ignore


def ejecutar_optimizado_sobre_muestra(
    prog: Programador,
    casos_muestra: list[dict],
    dias_busqueda: int = 7,
    paso_min: int = 60,
):
    """Ejecuta la lógica exacta de Programador.ejecutar sobre una muestra específica."""
    casos = sorted(
        casos_muestra,
        key=lambda c: (int(c["PRIORIDAD_SIM"]), c["FECHA_MINIMA_OPERABLE_SIM"], c["CASO_ID"]),
    )
    for caso in casos:
        if caso["ESTADO_PROGRAMACION"] != "PENDIENTE":
            prog.pendientes.append({"CASO_ID": caso["CASO_ID"], "MOTIVO": "ESTADO_NO_PENDIENTE"})
            continue
        if caso["PACIENTE_LISTO_SIM"] != "SI" or caso["PACIENTE_PRESENTE_SIM"] != "SI":
            prog.pendientes.append({"CASO_ID": caso["CASO_ID"], "MOTIVO": "PACIENTE_NO_LISTO_O_NO_PRESENTE"})
            continue

        hospital = caso["HOSPITAL_SOLICITANTE"]
        dia_min = date.fromisoformat(caso["FECHA_MINIMA_OPERABLE_SIM"])
        encontrado = None

        for texto_fecha in prog.fechas:
            dia = date.fromisoformat(texto_fecha)
            if dia < dia_min:
                continue
            if (dia - dia_min).days >= dias_busqueda:
                break
            desde = minutos(caso["HORA_PREFERIDA_SIM"]) if dia == dia_min else 7 * 60
            desde = ((max(7 * 60, desde) + paso_min - 1) // paso_min) * paso_min
            for min_inicio in range(desde, 21 * 60, paso_min):
                inicio = datetime.combine(dia, time(min_inicio // 60, min_inicio % 60))
                encontrado = prog.intentar(caso, hospital, dia, inicio)
                if encontrado:
                    break
            if encontrado:
                break

        if encontrado:
            prog.registros.append(encontrado)
        else:
            prog.pendientes.append({"CASO_ID": caso["CASO_ID"], "MOTIVO": "NO_ASIGNADA_POR_GREEDY_EN_HORIZONTE"})

    return prog.registros, prog.pendientes


def calcular_ocupabilidad(prog: Programador, programadas: list[dict]) -> tuple[dict, list[dict]]:
    """Aqui se calcula ocupabilidad global y por quirófano.

    Denominador: minutos totales en ventanas DISPONIBLE de cada sala activa
    durante el horizonte de fechas activas (entre la primera y última fecha
    programada; si no hay programadas, todo el calendario).
    """
    fechas_usadas = sorted({r["FECHA"] for r in programadas})
    if fechas_usadas:
        f_min, f_max = fechas_usadas[0], fechas_usadas[-1]
        fechas_horizonte = [f for f in prog.fechas if f_min <= f <= f_max]
    else:
        fechas_horizonte = list(prog.fechas)

    disp_por_sala = defaultdict(int)
    for sid, sala in prog.salas.items():
        if not si(sala["ACTIVA"]) or sala["ESTADO_INICIAL"] != "DISPONIBLE":
            continue
        for dia in fechas_horizonte:
            for v in prog.disp.get((dia, sid), []):
                if v["ESTADO_PLANIFICADO"] == "DISPONIBLE":
                    ini = max(7 * 60, minutos(v["HORA_INICIO"]))
                    fin = min(21 * 60, minutos(v["HORA_FIN"]))
                    if fin > ini:
                        disp_por_sala[sid] += fin - ini

    uso_cirugia = defaultdict(int)
    uso_con_limpieza = defaultdict(int)
    conteo_sala = defaultdict(int)

    for r in programadas:
        sid = r["SALA_ID"]
        ini = minutos(r["INICIO"])
        fin_cir = minutos(r["FIN_CIRUGIA"])
        fin_limp = minutos(r["FIN_LIMPIEZA"])
        uso_cirugia[sid] += max(0, fin_cir - ini)
        uso_con_limpieza[sid] += max(0, fin_limp - ini)
        conteo_sala[sid] += 1

    detalle_salas = []
    tot_disp = 0
    tot_cir = 0
    tot_limp = 0

    for sid in sorted(disp_por_sala):
        d_min = disp_por_sala[sid]
        c_min = uso_cirugia[sid]
        l_min = uso_con_limpieza[sid]
        tot_disp += d_min
        tot_cir += c_min
        tot_limp += l_min
        detalle_salas.append(
            {
                "SALA_ID": sid,
                "HOSPITAL": prog.salas[sid]["HOSPITAL_ID"],
                "CIRUGIAS": conteo_sala[sid],
                "MIN_DISPONIBLES": d_min,
                "MIN_CIRUGIA": c_min,
                "MIN_CON_LIMPIEZA": l_min,
                "OCUP_CIRUGIA_PCT": round((c_min / d_min) * 100, 2) if d_min else 0.0,
                "OCUP_CON_LIMPIEZA_PCT": round((l_min / d_min) * 100, 2) if d_min else 0.0,
            }
        )

    resumen = {
        "dias_horizonte": len(fechas_horizonte),
        "min_disponibles_totales": tot_disp,
        "min_cirugia_totales": tot_cir,
        "min_con_limpieza_totales": tot_limp,
        "ocup_cirugia_pct": round((tot_cir / tot_disp) * 100, 2) if tot_disp else 0.0,
        "ocup_con_limpieza_pct": round((tot_limp / tot_disp) * 100, 2) if tot_disp else 0.0,
    }
    return resumen, detalle_salas


def medir_corrida(
    metodo: str,
    base: str,
    n: int,
    semilla: int,
    dias_busqueda: int,
    paso_min: int,
    medir_ram: bool = False,
):
    """Ejecuta una corrida aislada midiendo tiempo real y opcionalmente RAM pico."""
    if medir_ram:
        tracemalloc.start()
    t0 = time_mod.perf_counter()

    if metodo == "FCFS_FIFO_BASE":
        prog = ProgramadorFCFS(base)
        muestra = seleccionar_muestra(prog.casos, n, semilla)
        programadas, pendientes = prog.ejecutar_sobre_muestra(muestra, dias_busqueda, paso_min)
    else:
        prog = Programador(base)
        muestra = seleccionar_muestra(prog.casos, n, semilla)
        programadas, pendientes = ejecutar_optimizado_sobre_muestra(prog, muestra, dias_busqueda, paso_min)

    duracion_s = time_mod.perf_counter() - t0
    pico_bytes = 0
    if medir_ram:
        _, pico_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    errores = verificar_asignaciones(programadas)
    if errores:
        raise RuntimeError(f"Solapamientos detectados en {metodo} (N={n}): {errores[:3]}")

    ocup_resumen, detalle_salas = calcular_ocupabilidad(prog, programadas)
    return {
        "n_real": len(muestra),
        "programadas": len(programadas),
        "pendientes": len(pendientes),
        "solapamientos": len(errores),
        "tiempo_s": duracion_s,
        "ram_pico_mb": pico_bytes / (1024 * 1024),
        "ocup_resumen": ocup_resumen,
        "detalle_salas": detalle_salas,
    }


def main():
    cli = argparse.ArgumentParser(description="Benchmark reproducible FCFS vs. Optimizado")
    cli.add_argument("--base", default=str(RAIZ_REPO))
    cli.add_argument("--n-list", type=int, nargs="+", default=[100, 500, 1000, 1500])
    cli.add_argument("--semilla", type=int, default=42)
    cli.add_argument("--repeticiones", type=int, default=3)
    cli.add_argument("--dias-busqueda", type=int, default=7)
    cli.add_argument("--paso-min", type=int, choices=(30, 60), default=60)
    args = cli.parse_args()

    filas_resultados = []
    filas_salas = []

    print(
        f"Iniciando benchmark | Semilla={args.semilla} | Repeticiones={args.repeticiones} | "
        f"Horizonte={args.dias_busqueda}d | Paso={args.paso_min}min\n"
    )

    for n in args.n_list:
        for metodo in ("FCFS_FIFO_BASE", "OPTIMIZADO_GREEDY_V1"):
            tiempos = []
            ultimo = None
            for rep in range(args.repeticiones):
                print(f"  -> Ejecutando N={n} | {metodo} | rep {rep + 1}/{args.repeticiones}...", flush=True)
                ultimo = medir_corrida(
                    metodo, args.base, n, args.semilla, args.dias_busqueda, args.paso_min, medir_ram=False
                )
                tiempos.append(ultimo["tiempo_s"])

            print(f"  -> Midiendo RAM pico N={n} | {metodo}...", flush=True)
            corrida_ram = medir_corrida(
                metodo, args.base, n, args.semilla, args.dias_busqueda, args.paso_min, medir_ram=True
            )

            t_prom = statistics.mean(tiempos)
            t_desv = statistics.stdev(tiempos) if len(tiempos) > 1 else 0.0
            ram_max = corrida_ram["ram_pico_mb"]
            ocup = ultimo["ocup_resumen"]

            fila = {
                "N_SOLICITUDES": ultimo["n_real"],
                "SEMILLA": args.semilla,
                "METODO": metodo,
                "PROGRAMADAS": ultimo["programadas"],
                "PENDIENTES": ultimo["pendientes"],
                "TASA_PROGRAMACION_PCT": round((ultimo["programadas"] / ultimo["n_real"]) * 100, 2),
                "OCUPABILIDAD_CIRUGIA_PCT": ocup["ocup_cirugia_pct"],
                "OCUPABILIDAD_CON_LIMPIEZA_PCT": ocup["ocup_con_limpieza_pct"],
                "TIEMPO_PROMEDIO_S": round(t_prom, 4),
                "TIEMPO_DESV_S": round(t_desv, 4),
                "RAM_PICO_MB": round(ram_max, 2),
                "SOLAPAMIENTOS": ultimo["solapamientos"],
                "REPETICIONES": args.repeticiones,
            }
            filas_resultados.append(fila)

            for s in ultimo["detalle_salas"]:
                filas_salas.append({"N_SOLICITUDES": ultimo["n_real"], "METODO": metodo, **s})

            print(
                f"N={fila['N_SOLICITUDES']:4d} | {metodo:20s} | Prog={fila['PROGRAMADAS']:4d} | "
                f"Pend={fila['PENDIENTES']:4d} | Ocup(cir/limp)={fila['OCUPABILIDAD_CIRUGIA_PCT']:5.2f}% / "
                f"{fila['OCUPABILIDAD_CON_LIMPIEZA_PCT']:5.2f}% | "
                f"Tiempo={fila['TIEMPO_PROMEDIO_S']:.3f}s (±{fila['TIEMPO_DESV_S']:.3f}s) | "
                f"RAM={fila['RAM_PICO_MB']:.2f}MB | Solap={fila['SOLAPAMIENTOS']}"
            )

    ruta_res = RUTA_BENCH / "RESULTADOS.csv"
    with open(ruta_res, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(filas_resultados[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(filas_resultados)

    ruta_salas = RUTA_BENCH / "OCUPABILIDAD_QUIROFANOS.csv"
    with open(ruta_salas, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(filas_salas[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(filas_salas)

    print(f"\nArchivos generados:\n - {ruta_res}\n - {ruta_salas}")


if __name__ == "__main__":
    main()