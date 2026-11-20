"""
Extracción y construcción de la red vial real dirigida en San Isidro, Lima (OSMnx).
Rama: feature/red-vial-real
No modifica los CSV activos de '3 Datos/' ni la base de datos PostgreSQL.
"""
from __future__ import annotations

import math
from pathlib import Path

import folium
import networkx as nx
import osmnx as ox
import pandas as pd

BASE_GEO = Path(__file__).resolve().parent

SEDES_REFERENCIA = {
    "H1": {
        "nombre": "Clínica Ricardo Palma",
        "direccion": "Av. Javier Prado Este 1066, San Isidro",
        "lat": -12.09068,
        "lon": -77.01854,
        "nota_acceso": "Acceso vehicular sobre Av. Javier Prado Este (calzada este-oeste / auxiliar cuadra 10).",
    },
    "H2": {
        "nombre": "Clínica Javier Prado",
        "direccion": "Av. Javier Prado Este 499, San Isidro",
        "lat": -12.09155,
        "lon": -77.02780,
        "nota_acceso": "Acceso vehicular sobre Av. Javier Prado Este cuadra 4 / intersección Av. Petit Thouars.",
    },
    "H3": {
        "nombre": "Clínica Limatambo",
        "direccion": "Av. República de Panamá 3606, San Isidro",
        "lat": -12.10042,
        "lon": -77.01915,
        "nota_acceso": "Acceso vehicular sobre Av. República de Panamá cuadra 36 (sentido norte-sur).",
    },
}

VELOCIDADES_KMH = {
    "trunk": 45.0,
    "trunk_link": 35.0,
    "primary": 40.0,
    "primary_link": 30.0,
    "secondary": 35.0,
    "secondary_link": 25.0,
    "tertiary": 30.0,
    "tertiary_link": 25.0,
    "residential": 25.0,
    "living_street": 15.0,
    "service": 20.0,
    "unclassified": 25.0,
}
VELOCIDAD_DEFECTO_KMH = 25.0


def obtener_velocidad_kmh(highway_attr) -> float:
    if isinstance(highway_attr, list):
        highway_attr = highway_attr[0]
    return VELOCIDADES_KMH.get(str(highway_attr), VELOCIDAD_DEFECTO_KMH)


def normalizar_nombre_via(name_attr) -> str:
    if name_attr is None or (isinstance(name_attr, float) and math.isnan(name_attr)):
        return "Vía local sin nombre OSM"
    if isinstance(name_attr, list):
        return " / ".join(str(x) for x in name_attr)
    return str(name_attr)


def descargar_subgrafo_san_isidro() -> nx.MultiDiGraph:
    centro = (-12.0950, -77.0225)
    print("Descargando red vial dirigida desde OpenStreetMap (radio 1800 m alrededor de San Isidro)...")
    G = ox.graph_from_point(centro, dist=1800, network_type="drive", simplify=True)

    componentes = list(nx.strongly_connected_components(G))
    mayor_scc = max(componentes, key=len)
    G = G.subgraph(mayor_scc).copy()
    print(f"Grafo fuertemente conexo obtenido: {G.number_of_nodes()} nodos, {G.number_of_edges()} aristas.")
    return G


def nodo_mas_cercano(G: nx.MultiDiGraph, lat: float, lon: float) -> int:
    """Encuentra el nodo OSM más cercano usando distancia Haversine (en metros) sin requerir scikit-learn."""
    r_tierra = 6371000.0
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    mejor_nodo = None
    mejor_dist = float("inf")
    for nid, data in G.nodes(data=True):
        lat2 = math.radians(float(data["y"]))
        lon2 = math.radians(float(data["x"]))
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        dist = 2 * r_tierra * math.asin(math.sqrt(a))
        if dist < mejor_dist:
            mejor_dist = dist
            mejor_nodo = nid
    return mejor_nodo


def construir_tablas_y_archivos(G: nx.MultiDiGraph):
    nodos_hospital_osm = {}
    for cod, info in SEDES_REFERENCIA.items():
        nodo_osm = nodo_mas_cercano(G, info["lat"], info["lon"])
        nodos_hospital_osm[cod] = nodo_osm

    assert len(set(nodos_hospital_osm.values())) == 3, "Dos hospitales mapearon al mismo nodo OSM."

    osm_a_id_interno = {osm_id: cod for cod, osm_id in nodos_hospital_osm.items()}

    nodos_relevantes = set(nodos_hospital_osm.values())
    codigos = list(SEDES_REFERENCIA.keys())
    for o in codigos:
        for d in codigos:
            if o != d:
                ruta_osm = nx.shortest_path(G, nodos_hospital_osm[o], nodos_hospital_osm[d], weight="length")
                nodos_relevantes.update(ruta_osm)

    vecinos = set()
    for n in nodos_relevantes:
        vecinos.update(G.successors(n))
        vecinos.update(G.predecessors(n))
    nodos_relevantes.update(vecinos)

    G_sub = G.subgraph(nodos_relevantes).copy()
    mayor_scc_sub = max(nx.strongly_connected_components(G_sub), key=len)
    G_sub = G_sub.subgraph(mayor_scc_sub).copy()

    for cod, osm_id in nodos_hospital_osm.items():
        if osm_id not in G_sub:
            raise RuntimeError(f"El nodo de acceso de {cod} quedó fuera de la componente conexa.")

    contador_vial = 1
    for osm_id in sorted(G_sub.nodes()):
        if osm_id not in osm_a_id_interno:
            osm_a_id_interno[osm_id] = f"VIA_REAL_{contador_vial:03d}"
            contador_vial += 1

    filas_hospitales = []
    for cod, info in SEDES_REFERENCIA.items():
        osm_id = nodos_hospital_osm[cod]
        data_nodo = G_sub.nodes[osm_id]
        filas_hospitales.append({
            "HOSPITAL_ID": cod,
            "NOMBRE": info["nombre"],
            "DIRECCION_REFERENCIA": info["direccion"],
            "OSM_NODE_ID": osm_id,
            "LATITUD": round(float(data_nodo["y"]), 6),
            "LONGITUD": round(float(data_nodo["x"]), 6),
            "ACCESO_VIAL": info["nota_acceso"],
        })

    filas_puntos = []
    for osm_id, id_interno in osm_a_id_interno.items():
        if id_interno.startswith("H"):
            continue
        data_nodo = G_sub.nodes[osm_id]
        calles_incidentes = set()
        for _, _, edata in list(G_sub.in_edges(osm_id, data=True)) + list(G_sub.out_edges(osm_id, data=True)):
            nombre_v = normalizar_nombre_via(edata.get("name"))
            if nombre_v != "Vía local sin nombre OSM":
                calles_incidentes.add(nombre_v)
        etiqueta_interseccion = " con ".join(sorted(calles_incidentes)[:2]) or f"Intersección OSM {osm_id}"

        filas_puntos.append({
            "NODO_VIAL_ID": id_interno,
            "NOMBRE": etiqueta_interseccion,
            "OSM_NODE_ID": osm_id,
            "LATITUD": round(float(data_nodo["y"]), 6),
            "LONGITUD": round(float(data_nodo["x"]), 6),
        })

    filas_conexiones = []
    contador_arco = 1
    mejores_aristas = {}
    for u, v, _, edata in G_sub.edges(keys=True, data=True):
        if u == v:
            continue
        origen_id = osm_a_id_interno[u]
        destino_id = osm_a_id_interno[v]
        distancia_m = round(float(edata.get("length", 50.0)), 2)
        vel_kmh = obtener_velocidad_kmh(edata.get("highway"))
        tiempo_min_exacto = (distancia_m / 1000.0) / vel_kmh * 60.0
        tiempo_min_sim = max(1, int(round(tiempo_min_exacto)))

        clave = (origen_id, destino_id)
        if clave not in mejores_aristas or tiempo_min_exacto < mejores_aristas[clave]["TIEMPO_MIN_EXACTO"]:
            mejores_aristas[clave] = {
                "ORIGEN_NODO": origen_id,
                "DESTINO_NODO": destino_id,
                "NOMBRE_VIA": normalizar_nombre_via(edata.get("name")),
                "TIPO_VIA": str(edata.get("highway")),
                "SENTIDO_UNICO": bool(edata.get("oneway", True)),
                "DISTANCIA_M": distancia_m,
                "VELOCIDAD_SUPUESTA_KMH": vel_kmh,
                "TIEMPO_MIN_EXACTO": round(tiempo_min_exacto, 3),
                "TIEMPO_MIN_SIM": tiempo_min_sim,
                "ESTADO": "HABILITADA",
            }

    for clave in sorted(mejores_aristas.keys()):
        fila = {"CONEXION_ID": f"TRAMO_{contador_arco:04d}", **mejores_aristas[clave]}
        filas_conexiones.append(fila)
        contador_arco += 1

    df_hosp = pd.DataFrame(filas_hospitales)
    df_puntos = pd.DataFrame(filas_puntos)
    df_conex = pd.DataFrame(filas_conexiones)

    df_hosp.to_csv(BASE_GEO / "hospitales_red_real.csv", index=False, encoding="utf-8")
    df_puntos.to_csv(BASE_GEO / "puntos_viales_red_real.csv", index=False, encoding="utf-8")
    df_conex.to_csv(BASE_GEO / "conexiones_red_real.csv", index=False, encoding="utf-8")
    ox.save_graphml(G_sub, filepath=BASE_GEO / "red_vial_san_isidro.graphml")

    generar_mapa_folium(df_hosp, df_puntos, df_conex)
    print(f"Archivos exportados en {BASE_GEO}:")
    print(f"  - hospitales_red_real.csv ({len(df_hosp)} sedes)")
    print(f"  - puntos_viales_red_real.csv ({len(df_puntos)} intersecciones)")
    print(f"  - conexiones_red_real.csv ({len(df_conex)} tramos dirigidos)")
    print("  - red_vial_san_isidro.graphml")
    print("  - mapa_red_san_isidro.html")


def generar_mapa_folium(df_hosp: pd.DataFrame, df_puntos: pd.DataFrame, df_conex: pd.DataFrame):
    coords_nodos = {}
    for _, r in df_hosp.iterrows():
        coords_nodos[r["HOSPITAL_ID"]] = (r["LATITUD"], r["LONGITUD"])
    for _, r in df_puntos.iterrows():
        coords_nodos[r["NODO_VIAL_ID"]] = (r["LATITUD"], r["LONGITUD"])

    mapa = folium.Map(location=[-12.0955, -77.0228], zoom_start=15, tiles=None)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        name="Callejero San Isidro (OSM / CARTO)",
        control=True,
    ).add_to(mapa)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr='Tiles &copy; Esri &mdash; Source: Esri, OpenStreetMap contributors',
        name="Mapa Vial Detallado (Esri / OSM)",
        control=True,
    ).add_to(mapa)

    for _, r in df_conex.iterrows():
        p1 = coords_nodos.get(r["ORIGEN_NODO"])
        p2 = coords_nodos.get(r["DESTINO_NODO"])
        if p1 and p2:
            folium.PolyLine(
                locations=[p1, p2],
                color="#3b82f6",
                weight=2.5,
                opacity=0.65,
                tooltip=f"{r['CONEXION_ID']}: {r['NOMBRE_VIA']} ({r['DISTANCIA_M']} m | {r['TIEMPO_MIN_SIM']} min)",
            ).add_to(mapa)

    for _, r in df_puntos.iterrows():
        folium.CircleMarker(
            location=(r["LATITUD"], r["LONGITUD"]),
            radius=3.5,
            color="#475569",
            fill=True,
            fill_opacity=0.8,
            tooltip=f"{r['NODO_VIAL_ID']}: {r['NOMBRE']}",
        ).add_to(mapa)

    for _, r in df_hosp.iterrows():
        folium.Marker(
            location=(r["LATITUD"], r["LONGITUD"]),
            popup=f"<b>{r['HOSPITAL_ID']} - {r['NOMBRE']}</b><br>{r['DIRECCION_REFERENCIA']}<br><i>{r['ACCESO_VIAL']}</i>",
            tooltip=f"{r['HOSPITAL_ID']}: {r['NOMBRE']}",
            icon=folium.Icon(color="red", icon="plus-sign"),
        ).add_to(mapa)

    from adaptador_red_vial import calcular_ruta_real
    capa_rutas = folium.FeatureGroup(name="Rutas Óptimas Bellman-Ford (H1-H2-H3)", show=True)
    colores_ruta = {
        ("H1", "H2"): "#dc2626",
        ("H2", "H1"): "#ea580c",
        ("H1", "H3"): "#16a34a",
        ("H3", "H1"): "#0d9488",
        ("H2", "H3"): "#7c3aed",
        ("H3", "H2"): "#2563eb",
    }
    for (o, d), color in colores_ruta.items():
        res = calcular_ruta_real(o, d)
        if "camino" in res:
            pts = [coords_nodos[n] for n in res["camino"] if n in coords_nodos]
            folium.PolyLine(
                locations=pts,
                color=color,
                weight=4.5,
                opacity=0.85,
                tooltip=f"Ruta {o} -> {d}: {res['tiempo_min_sim']} min ({res['distancia_total_m']} m)",
            ).add_to(capa_rutas)
    capa_rutas.add_to(mapa)
    folium.LayerControl().add_to(mapa)

    mapa.save(str(BASE_GEO / "mapa_red_san_isidro.html"))


if __name__ == "__main__":
    grafo_osm = descargar_subgrafo_san_isidro()
    construir_tablas_y_archivos(grafo_osm)