from __future__ import annotations
import argparse
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parent.parent
RUTA_MOTORES = RAIZ_REPO / "9 Aplicacion Web" / "backend" / "motores"
if str(RUTA_MOTORES) not in sys.path:
    sys.path.insert(0,str(RUTA_MOTORES))

from motor_programacion_v1 import( #noqa: E402 #type: ignore
    RELACIONES,
    Programador,
    minutos,
    si,
    verificar_asignaciones,
)

#Seccion de las posibles columnas para el orden de llegada (en caso existiesen en el archivo cirugias_red.csv)
COLUMNAS_LLEGADA = (
    "FECHA_SOLICITUD_SIM",
    "FECHA_SOLICITUD",
    "FECHA_REGISTRO",
    "TIMESTAMP_SOLICITUD",
    "ORDEN_LLEGADA",
)

def clave_llegada_fcfs(caso: dict, indice_original: int) -> tuple:
    """Importante, aqui se devuelve el ordenamiento FCFS/FIFO."""
    for col in COLUMNAS_LLEGADA:
        if col in caso and caso[col]:
            return (caso[col], indice_original, caso["CASO_ID"])
    # Si no existe timestamp explícito de registro, se usa el orden natural de llegada dentro del CSV
    return (indice_original, caso["CASO_ID"])

class ProgramadorFCFS(Programador):
    """En esta línea se define la  base FCFS/FIFO sobre las mismas restricciones físicas y del grafo."""

    def elegir(
        self,
        caso,
        hospital,
        rol,
        fecha,
        inicio,
        fin,
        escogidos,
        especialidad=None,
        subtipo=None,
        categoria=None,
        tiempo_extra=0,
        es_personal=False,
        obligatorio=None,
    ):
        """Mismas validaciones que Programador.elegir, pero sin balanceo por carga."""
        coleccion = (
            self.personal
            if rol in self.personal_roles
            else self.salas
            if rol == "SALA"
            else self.postop
            if rol == "POSTOP"
            else self.equipos
        )
        lista = []
        for rid in self.candidatos[caso["CASO_ID"]][RELACIONES[rol]]:
            if rid in escogidos or rid not in coleccion or (obligatorio and rid != obligatorio):
                continue
            r = coleccion[rid]
            if r["HOSPITAL_ID"] != hospital:
                continue
            if es_personal:
                if r["ROL"] != rol or (especialidad and r["ESPECIALIDAD"] != especialidad):
                    continue
            elif rol == "SALA":
                if not si(r["ACTIVA"]) or r["ESTADO_INICIAL"] != "DISPONIBLE":
                    continue
                tipos_validos = (
                    {"OBSTETRICA", "FLEXIBLE"}
                    if caso["TIPO_PROCEDIMIENTO"] == "CESAREA"
                    else {"ONCOLOGICA", "FLEXIBLE"}
                )
                if r["TIPO_SALA"] not in tipos_validos:
                    continue
            elif rol == "POSTOP":
                if r["TIPO"] != subtipo or not si(r["ACTIVO"]) or r["ESTADO_INICIAL"] != "DISPONIBLE":
                    continue
            else:
                if r["CATEGORIA"] != categoria or r["TIPO_COMPATIBILIDAD"] != subtipo or not si(r["ACTIVO"]):
                    continue
                if r["ESTADO_INICIAL"] not in ("DISPONIBLE", "ESTERIL"):
                    continue

            hasta = fin + timedelta(minutes=tiempo_extra)
            descanso = int(r["DESCANSO_MINIMO_MIN"]) if es_personal and rol not in ("LIMPIEZA",) else 0
            carga_min = (fin - inicio).seconds // 60 if es_personal and rol != "LIMPIEZA" else 0
            if self.libre(rid, fecha, inicio, hasta, descanso=descanso, carga_cirugia=carga_min):
                lista.append(rid)

        # Aqui se da la diferencia FCFS: se elige el primer recurso disponible por ID (sin ordenar por self.carga)
        lista.sort()
        return lista[0] if lista else None

    def ejecutar_sobre_muestra(self, casos_muestra: list[dict], dias_busqueda: int = 7, paso_min: int = 60):
        """Procesa una muestra exacta de casos en orden de llegada (FIFO)."""
        indexados = list(enumerate(casos_muestra))
        indexados.sort(key=lambda par: clave_llegada_fcfs(par[1], par[0]))

        for _, caso in indexados:
            if caso["ESTADO_PROGRAMACION"] != "PENDIENTE":
                self.pendientes.append({"CASO_ID": caso["CASO_ID"], "MOTIVO": "ESTADO_NO_PENDIENTE"})
                continue
            if caso["PACIENTE_LISTO_SIM"] != "SI" or caso["PACIENTE_PRESENTE_SIM"] != "SI":
                self.pendientes.append({"CASO_ID": caso["CASO_ID"], "MOTIVO": "PACIENTE_NO_LISTO_O_NO_PRESENTE"})
                continue

            hospital = caso["HOSPITAL_SOLICITANTE"]
            dia_min = date.fromisoformat(caso["FECHA_MINIMA_OPERABLE_SIM"])
            encontrado = None

            for texto_fecha in self.fechas:
                dia = date.fromisoformat(texto_fecha)
                if dia < dia_min:
                    continue
                if (dia - dia_min).days >= dias_busqueda:
                    break
                desde = minutos(caso["HORA_PREFERIDA_SIM"]) if dia == dia_min else 7 * 60
                desde = ((max(7 * 60, desde) + paso_min - 1) // paso_min) * paso_min
                for min_inicio in range(desde, 21 * 60, paso_min):
                    inicio = datetime.combine(dia, time(min_inicio // 60, min_inicio % 60))
                    encontrado = self.intentar(caso, hospital, dia, inicio)
                    if encontrado:
                        encontrado["METODO"] = "FCFS_FIFO_BASE"
                        break
                if encontrado:
                    break

            if encontrado:
                self.registros.append(encontrado)
            else:
                self.pendientes.append({"CASO_ID": caso["CASO_ID"], "MOTIVO": "NO_ASIGNADA_POR_FCFS_EN_HORIZONTE"})

        return self.registros, self.pendientes


def seleccionar_muestra(casos: list[dict], n: int, semilla: int) -> list[dict]:
    """Se toma una muestra reproducible de *N* casos conservando su orden original de llegada."""
    if n >= len(casos):
        return list(casos)
    rng = random.Random(semilla)
    indices = sorted(rng.sample(range(len(casos)), n))
    return [casos[i] for i in indices]


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Prueba unitaria del programador base FCFS/FIFO")
    cli.add_argument("--base", default=str(RAIZ_REPO))
    cli.add_argument("--n", type=int, default=100, help="Cantidad de solicitudes a evaluar")
    cli.add_argument("--semilla", type=int, default=42, help="Semilla para muestreo reproducible")
    cli.add_argument("--dias-busqueda", type=int, default=7)
    cli.add_argument("--paso-min", type=int, choices=(30, 60), default=60)
    args = cli.parse_args()

    prog = ProgramadorFCFS(args.base)
    muestra = seleccionar_muestra(prog.casos, args.n, args.semilla)
    programadas, pendientes = prog.ejecutar_sobre_muestra(muestra, args.dias_busqueda, args.paso_min)
    errores = verificar_asignaciones(programadas)

    print(
        f"[FCFS] N={len(muestra)} | Semilla={args.semilla} | "
        f"Programadas={len(programadas)} | Pendientes={len(pendientes)} | Solapamientos={len(errores)}"
    )
    if errores:
        raise RuntimeError(f"Se han detectado {len(errores)} solapamientos en FCFS: {errores[:5]}")