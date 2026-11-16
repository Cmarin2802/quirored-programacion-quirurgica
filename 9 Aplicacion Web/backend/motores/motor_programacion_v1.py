"""Programación quirúrgica con búsqueda de compatibilidades y Greedy."""
from __future__ import annotations
import argparse
import csv
from collections import defaultdict, Counter
from datetime import datetime, date, time, timedelta
from pathlib import Path
from algoritmos_integrados import bfs_compatibilidades

RELACIONES = {
    "CIRUJANO": "CANDIDATO_CIRUJANO", "ANESTESIOLOGO": "CANDIDATO_ANESTESIOLOGO",
    "INSTRUMENTISTA": "CANDIDATO_INSTRUMENTISTA", "CIRCULANTE": "CANDIDATO_CIRCULANTE",
    "NEONATOLOGO": "CANDIDATO_NEONATOLOGO", "LIMPIEZA": "CANDIDATO_LIMPIEZA",
    "SALA": "CANDIDATO_SALA", "EQUIPO": "CANDIDATO_EQUIPO",
    "INSTRUMENTAL": "CANDIDATO_INSTRUMENTAL", "POSTOP": "CANDIDATO_POSTOP"
}


def leer(ruta):
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def escribir(ruta, filas, columnas):
    filas = list(filas)
    columnas = list(dict.fromkeys(list(columnas) + [k for fila in filas for k in fila]))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columnas, delimiter=";")
        writer.writeheader()
        writer.writerows(filas)


def minutos(hhmm):
    h, m = map(int, hhmm.split(":"))
    return 60 * h + m


def si(valor):
    return str(valor).strip().upper() in ("SI", "TRUE", "1")


class Programador:
    def __init__(self, base):
        self.base = Path(base)
        d = next((self.base / nombre for nombre in ("3 Datos", "03_Datos", "01_Datos", "3_Datos", "Datos")
                  if (self.base / nombre / "cirugias_red.csv").exists()), None)
        if d is None:
            raise FileNotFoundError("Falta cirugias_red.csv en la carpeta de datos del proyecto")
        g = next((self.base / nombre for nombre in ("4 Grafos", "04_Grafos", "02_Grafo", "4_Grafos", "Grafo")
                  if (self.base / nombre / "grafo_aristas_red.csv").exists()), None)
        if g is None:
            raise FileNotFoundError("Falta grafo_aristas_red.csv en la carpeta de grafos")
        self.casos = leer(d / "cirugias_red.csv")
        self.personal = {r["ID_PERSONAL"]: r for r in leer(d / "personal_red.csv")}
        self.salas = {r["ID_SALA"]: r for r in leer(d / "salas_red.csv")}
        self.equipos = {r["ID_RECURSO"]: r for r in leer(d / "equipos_instrumental_red.csv")}
        self.postop = {r["ID_RECURSO_POSTOP"]: r for r in leer(d / "postoperatorio_red.csv")}
        self.hospitales = {r["HOSPITAL_ID"]: r for r in leer(d / "hospitales_red.csv")}
        self.disp = defaultdict(list)
        for r in leer(d / "disponibilidad_red.csv"):
            self.disp[(r["FECHA"], r["ID_RECURSO"])].append(r)
        self.fechas = sorted({d for d, rid in self.disp})
        self.grafo_adyacencia = defaultdict(list)
        self.grafo_inverso = defaultdict(set)
        relevantes = set(RELACIONES.values()) | {"HOSPITAL_CANDIDATO", "SOLICITANTE_Y_CANDIDATO"}
        for e in leer(g / "grafo_aristas_red.csv"):
            if e["RELACION"] in relevantes:
                self.grafo_adyacencia[e["ORIGEN_ID"]].append((e["DESTINO_ID"], e["RELACION"]))
                self.grafo_inverso[e["DESTINO_ID"]].add(e["ORIGEN_ID"])
        self.candidatos = defaultdict(lambda: defaultdict(set))
        for caso in self.casos:
            relaciones, _ = bfs_compatibilidades(self.grafo_adyacencia, caso["CASO_ID"])
            self.candidatos[caso["CASO_ID"]].update(relaciones)
        
        self.reservas = defaultdict(list)  
        self.carga = defaultdict(int)       
        self.registros = []
        self.pendientes = []

    def permitido(self, caso, relacion, recurso_id):
        return recurso_id in self.candidatos[caso["CASO_ID"]][relacion]

    def libre(self, rid, fecha, inicio, fin, descanso=0, carga_cirugia=0):
        dia = fecha.isoformat()
        ventanas = self.disp.get((dia, rid), [])
        a = minutos(inicio.strftime("%H:%M"))
        b = minutos(fin.strftime("%H:%M"))
        if inicio.date() != fecha or fin.date() != fecha:
            return False  
        if not any(v["ESTADO_PLANIFICADO"] == "DISPONIBLE" and
                   minutos(v["HORA_INICIO"]) <= a and minutos(v["HORA_FIN"]) >= b
                   for v in ventanas):
            return False
        for ocupado_inicio, ocupado_fin in self.reservas[rid]:
            if inicio < ocupado_fin + timedelta(minutes=descanso) and fin + timedelta(minutes=descanso) > ocupado_inicio:
                return False
        if rid in self.personal:
            r = self.personal[rid]
            if not si(r["ACTIVO"]) or r["ESTADO_INICIAL"] != "DISPONIBLE":
                return False
            if self.carga[(dia, rid)] + carga_cirugia > int(r["MAX_CARGA_TURNO_MIN"]):
                return False
        return True

    def elegir(self, caso, hospital, rol, fecha, inicio, fin, escogidos, especialidad=None,
               subtipo=None, categoria=None, tiempo_extra=0, es_personal=False, obligatorio=None):
        coleccion = (self.personal if rol in self.personal_roles else
                     self.salas if rol == "SALA" else
                     self.postop if rol == "POSTOP" else self.equipos)
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
                if r["TIPO_SALA"] not in ({"OBSTETRICA", "FLEXIBLE"} if caso["TIPO_PROCEDIMIENTO"] == "CESAREA" else {"ONCOLOGICA", "FLEXIBLE"}):
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
            if self.libre(rid, fecha, inicio, hasta, descanso=descanso,
                          carga_cirugia=(fin-inicio).seconds // 60 if es_personal and rol != "LIMPIEZA" else 0):
                lista.append(rid)
        lista.sort(key=lambda rid: (self.carga[(fecha.isoformat(), rid)], rid))
        return lista[0] if lista else None

    personal_roles = {"CIRUJANO", "ANESTESIOLOGO", "INSTRUMENTISTA", "CIRCULANTE", "NEONATOLOGO", "LIMPIEZA"}

    def intentar(self, caso, hospital, fecha, inicio, forzar=None):
        forzar = forzar or {}
        duracion = int(caso["DURACION_ESTIMADA_MIN"])
        fin = inicio + timedelta(minutes=duracion)
        if fin.date() != fecha:
            return None
        if self.hospitales[hospital]["ESTADO_OPERATIVO"] != "ACTIVO":
            return None
        if not self.permitido(caso, "HOSPITAL_CANDIDATO", hospital) and not self.permitido(caso, "SOLICITANTE_Y_CANDIDATO", hospital):
            return None
        seleccionado = {}
        usados = set()

        def reservar_rol(rol, ini, termina, especialidad=None, subtipo=None, categoria=None, extra=0):
            clave = rol if not subtipo else f"{rol}_{subtipo}"
            obligado = forzar.get(rol) or forzar.get(clave)
            if rol == "EQUIPO" and subtipo == "ANESTESIA":
                obligado = forzar.get("EQUIPO_ANESTESIA", obligado)
            elif rol == "EQUIPO":
                obligado = forzar.get("EQUIPO_ESPECIALIZADO", obligado)
            rid = self.elegir(caso, hospital, rol, fecha, ini, termina, usados, especialidad,
                              subtipo, categoria, extra, rol in self.personal_roles, obligado)
            if rid is None:
                return False
            seleccionado[rol if not subtipo else f"{rol}_{subtipo}"] = (rid, ini, termina + timedelta(minutes=extra))
            usados.add(rid)
            return True

        obst = caso["TIPO_PROCEDIMIENTO"] == "CESAREA"
        
        salas_candidatas = []
        for sid in sorted(self.candidatos[caso["CASO_ID"]]["CANDIDATO_SALA"]):
            s = self.salas.get(sid)
            tipos = {"OBSTETRICA", "FLEXIBLE"} if obst else {"ONCOLOGICA", "FLEXIBLE"}
            if s and (not forzar.get("SALA") or sid == forzar["SALA"]) and s["HOSPITAL_ID"] == hospital and s["TIPO_SALA"] in tipos and si(s["ACTIVA"]) and s["ESTADO_INICIAL"] == "DISPONIBLE":
                l_min = int(s["TIEMPO_LIMPIEZA_MIN"])
                if self.libre(sid, fecha, inicio, fin + timedelta(minutes=l_min)):
                    salas_candidatas.append((sid, l_min))
        if not salas_candidatas:
            return None
        sala, limpieza_min = salas_candidatas[0]
        fin_limpieza = fin + timedelta(minutes=limpieza_min)
        seleccionado["SALA"] = (sala, inicio, fin_limpieza)
        usados.add(sala)
        especialidad = "GINECO_OBSTETRICIA" if obst else "CIRUGIA_ONCOLOGICA"
        for rol in ("CIRUJANO", "ANESTESIOLOGO", "INSTRUMENTISTA", "CIRCULANTE"):
            if not reservar_rol(rol, inicio, fin, especialidad if rol == "CIRUJANO" else None):
                return None
        if obst and not reservar_rol("NEONATOLOGO", inicio, fin):
            return None
        if not reservar_rol("LIMPIEZA", fin, fin_limpieza):
            return None
        requeridos_equipo = ("ANESTESIA", "NEONATAL") if obst else ("ANESTESIA", "ONCOLOGIA")
        for tipo in requeridos_equipo:
            if not reservar_rol("EQUIPO", inicio, fin, subtipo=tipo, categoria="EQUIPO"):
                return None
        tipo_instrumental = "CESAREA" if obst else "ONCO_ALTA_COMPLEJIDAD"
        
        
        instrumentos = []
        for rid in sorted(self.candidatos[caso["CASO_ID"]]["CANDIDATO_INSTRUMENTAL"]):
            r = self.equipos.get(rid)
            if r and (not forzar.get("INSTRUMENTAL") or rid == forzar["INSTRUMENTAL"]) and r["HOSPITAL_ID"] == hospital and r["CATEGORIA"] == "INSTRUMENTAL" and r["TIPO_COMPATIBILIDAD"] == tipo_instrumental and si(r["ACTIVO"]):
                tiempo_reproc = int(r["TIEMPO_REPROCESAMIENTO_MIN"]) if si(r["REQUIERE_REPROCESAMIENTO"]) else 0
                if self.libre(rid, fecha, inicio, fin + timedelta(minutes=tiempo_reproc)):
                    instrumentos.append((rid, tiempo_reproc))
        if not instrumentos:
            return None
        rid_instrumento, extra = instrumentos[0]
        seleccionado["INSTRUMENTAL"] = (rid_instrumento, inicio, fin + timedelta(minutes=extra))
        tipo_post = caso["POSTOP_REQUERIDO_SIM"]
        post_inicio = fin
        post_fin = fin + timedelta(minutes=int(caso["DURACION_POSTOP_ESTIMADA_MIN_SIM"]))
        if not reservar_rol("POSTOP", post_inicio, post_fin, subtipo=tipo_post):
            return None
        
        
        if tipo_post in ("UCI_ONCO", "UCIM"):
            intensivos = sorted((rid for rid, p in self.personal.items()
                if p["ROL"] == "INTENSIVISTA" and p["HOSPITAL_ID"] == hospital
                and (not forzar.get("INTENSIVISTA") or rid == forzar["INTENSIVISTA"])
                and self.libre(rid, fecha, inicio, fin,
                        descanso=int(p["DESCANSO_MINIMO_MIN"]), carga_cirugia=duracion)))
            if not intensivos:
                return None
            rid = intensivos[0]
            seleccionado["INTENSIVISTA"] = (rid, inicio, fin)
            usados.add(rid)
        
        for rol, (rid, ini, termina) in seleccionado.items():
            self.reservas[rid].append((ini, termina))
            if rid in self.personal and not rol.startswith("LIMPIEZA"):
                self.carga[(fecha.isoformat(), rid)] += duracion
        return {
            "CASO_ID": caso["CASO_ID"], "CASO_ID_TB1": caso["CASO_ID_TB1"],
            "HOSPITAL": hospital, "SALA_ID": seleccionado["SALA"][0],
            "FECHA": fecha.isoformat(), "INICIO": inicio.strftime("%H:%M"),
            "FIN_CIRUGIA": fin.strftime("%H:%M"), "FIN_LIMPIEZA": fin_limpieza.strftime("%H:%M"),
            "CIRUJANO_ID": seleccionado["CIRUJANO"][0],
            "ANESTESIOLOGO_ID": seleccionado["ANESTESIOLOGO"][0],
            "INSTRUMENTISTA_ID": seleccionado["INSTRUMENTISTA"][0],
            "CIRCULANTE_ID": seleccionado["CIRCULANTE"][0],
            "NEONATOLOGO_ID": seleccionado.get("NEONATOLOGO", ("",))[0],
            "LIMPIEZA_ID": seleccionado["LIMPIEZA"][0],
            "INTENSIVISTA_ID": seleccionado.get("INTENSIVISTA", ("",))[0],
            "EQUIPO_ANESTESIA_ID": seleccionado["EQUIPO_ANESTESIA"][0],
            "EQUIPO_ESPECIALIZADO_ID": seleccionado["EQUIPO_NEONATAL" if obst else "EQUIPO_ONCOLOGIA"][0],
            "INSTRUMENTAL_ID": seleccionado["INSTRUMENTAL"][0],
            "POSTOP_ID": seleccionado[f"POSTOP_{tipo_post}"][0],
            "POSTOP_FIN": post_fin.strftime("%Y-%m-%d %H:%M"),
            "TIPO_PROCEDIMIENTO": caso["TIPO_PROCEDIMIENTO"],
            "PRIORIDAD": caso["CATEGORIA_PRIORIDAD_SIM"],
            "ESTADO": "PROGRAMADA", "METODO": "GREEDY_LOCAL_V1"
        }

    def ejecutar(self, limite=120, dias_busqueda=7, paso_min=60):
        casos = sorted(self.casos, key=lambda c: (
            int(c["PRIORIDAD_SIM"]), c["FECHA_MINIMA_OPERABLE_SIM"], c["CASO_ID"]))[:limite]
        for caso in casos:
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
                desde = minutos(caso["HORA_PREFERIDA_SIM"]) if dia == dia_min else 7*60
                desde = ((max(7*60, desde) + paso_min - 1) // paso_min) * paso_min
                for min_inicio in range(desde, 21*60, paso_min):
                    inicio = datetime.combine(dia, time(min_inicio//60, min_inicio%60))
                    encontrado = self.intentar(caso, hospital, dia, inicio)
                    if encontrado:
                        break
                if encontrado:
                    break
            if encontrado:
                self.registros.append(encontrado)
            else:
                self.pendientes.append({"CASO_ID": caso["CASO_ID"], "MOTIVO": "NO_ASIGNADA_POR_GREEDY_EN_HORIZONTE"})
        return self.registros, self.pendientes


def verificar_asignaciones(registros):
    """No solapamientos exactos de recursos físicos. Incluye limpieza y postoperatorio."""
    claves = ("SALA_ID", "CIRUJANO_ID", "ANESTESIOLOGO_ID", "INSTRUMENTISTA_ID",
              "CIRCULANTE_ID", "NEONATOLOGO_ID", "INTENSIVISTA_ID", "EQUIPO_ANESTESIA_ID", "EQUIPO_ESPECIALIZADO_ID",
              "INSTRUMENTAL_ID", "LIMPIEZA_ID", "POSTOP_ID")
    
    
    por_recurso = defaultdict(list)
    for r in registros:
        inicio = datetime.fromisoformat(r["FECHA"]+"T"+r["INICIO"])
        fin = datetime.fromisoformat(r["FECHA"]+"T"+r["FIN_CIRUGIA"])
        for clave in claves:
            rid = r[clave]
            if not rid:
                continue
            if clave == "SALA_ID":
                hasta = datetime.fromisoformat(r["FECHA"]+"T"+r["FIN_LIMPIEZA"])
                desde = inicio
            elif clave == "LIMPIEZA_ID":
                desde = fin
                hasta = datetime.fromisoformat(r["FECHA"]+"T"+r["FIN_LIMPIEZA"])
            elif clave == "POSTOP_ID":
                desde = fin
                hasta = datetime.fromisoformat(r["POSTOP_FIN"])
            else:
                desde, hasta = inicio, fin
            por_recurso[rid].append((desde, hasta, r["CASO_ID"]))
    errores=[]
    for rid, ventanas in por_recurso.items():
        ventanas.sort()
        for a,b in zip(ventanas, ventanas[1:]):
            if b[0]<a[1]: errores.append((rid,a[2],b[2]))
    return errores


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--base", default=".")
    cli.add_argument("--limite", type=int, default=120)
    cli.add_argument("--dias-busqueda", type=int, default=7,
                     help="Número de días a partir de la fecha mínima, por solicitud")
    cli.add_argument("--paso-min", type=int, choices=(30, 60), default=60)
    args = cli.parse_args()
    app = Programador(args.base)
    programadas, pendientes = app.ejecutar(args.limite, args.dias_busqueda, args.paso_min)
    errores = verificar_asignaciones(programadas)
    if errores:
        raise RuntimeError(f"Conflictos detectados: {errores[:5]}")
    out = Path(args.base)/("8 Motores/Pruebas" if (Path(args.base)/"3 Datos").exists() else "03_Pruebas")
    campos = list(programadas[0]) if programadas else ["CASO_ID"]
    escribir(out/"programaciones_prueba.csv", programadas, campos)
    escribir(out/"pendientes_prueba.csv", pendientes, ["CASO_ID","MOTIVO"])
    print(f"Evaluadas: {args.limite} | Programadas: {len(programadas)} | Pendientes: {len(pendientes)} | Conflictos: {len(errores)}")
    print(f"Programadas por hospital: {dict(Counter(p['HOSPITAL'] for p in programadas))}")
    print("Archivos generados en:", out)
