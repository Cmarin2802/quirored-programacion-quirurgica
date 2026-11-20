# Fuentes Cartográficas, Accesos Viales y Supuestos del Modelo

- **Fecha de extracción:** Noviembre 2026 (ciclo académico 2026-20).
- **Fuente cartográfica:** OpenStreetMap (OSM) mediante `OSMnx` (`network_type="drive"`, radio 1,800 m centrado en San Isidro).
- **Dimensión del subgrafo extraído:** 136 nodos (3 sedes hospitalarias + 133 intersecciones reales) y 228 aristas dirigidas fuertemente conexas.
- **Licencia y atribución obligatoria:** Datos cartográficos bajo Open Database License (ODbL).  
  **© OpenStreetMap contributors** (`https://www.openstreetmap.org/copyright`).

## 1. Verificación de Accesos Viales de las Sedes (San Isidro, Lima)

No se utilizó geocodificación automática de dirección postal pura, ya que en avenidas troncales con separador central o vías auxiliares el punto más cercano puede caer en la calzada de sentido contrario. Cada sede fue anclada al nodo dirigido de acceso vehicular correspondiente:

| Código | Sede de Referencia | Dirección | Coordenadas de Acceso | Observación Vial OSM |
|---|---|---|---|---|
| **H1** | Clínica Ricardo Palma | Av. Javier Prado Este 1066 | `-12.09068, -77.01854` | Calzada auxiliar / troncal Av. Javier Prado Este (flujo dirigido hacia el este / cruce Calle 5). |
| **H2** | Clínica Javier Prado | Av. Javier Prado Este 499 | `-12.09155, -77.02780` | Intersección Av. Javier Prado Este cuadra 4 / esquina Calle Las Orquídeas y Av. Petit Thouars. |
| **H3** | Clínica Limatambo | Av. República de Panamá 3606 | `-12.10042, -77.01915` | Calzada de Av. República de Panamá cuadra 36 (flujo dirigido norte-sur / acceso Calle Zorzales). |

## 2. Cálculo de Costos Temporales (Sin Tráfico en Vivo)

Los pesos `TIEMPO_MIN_EXACTO` y `TIEMPO_MIN_SIM` representan **tiempos de traslado estimados en condiciones urbanas estándar** calculados a partir de la longitud real de cada segmento (`length` en metros) y velocidades operativas conservadoras asignadas según la etiqueta `highway` de OpenStreetMap:

- **Vías troncales (`trunk` / `trunk_link`):** 45 km/h / 35 km/h (ej. Av. Javier Prado Este, Vía Expresa)
- **Vías primarias (`primary` / `primary_link`):** 40 km/h / 30 km/h (ej. Av. República de Panamá, Av. Enrique Canaval y Moreyra)
- **Vías secundarias (`secondary`):** 35 km/h (ej. Av. Pablo Carriquirry, Av. Juan de Arona, Av. Rivera Navarrete)
- **Vías terciarias (`tertiary`):** 30 km/h (ej. Calle Las Begonias, Calle Deán Valdivia)
- **Calles locales / residenciales (`residential` / `service`):** 20–25 km/h

> **Nota metodológica:** Este modelo **no consume APIs de tráfico en tiempo real**. Los tiempos son deterministas y reproducibles para la evaluación del algoritmo de Bellman-Ford en el sistema académico QuiroRed.

## 3. Resumen de Resultados Bellman-Ford (6 Direcciones y Bloqueos)

| Origen -> Destino | Distancia (m) | Tiempo Estimado (min) | Nodos | Corredor Vial Principal |
|---|---:|---:|---:|---|
| **H1 -> H2** | 2,673.1 | 5.51 | 33 | Av. Javier Prado Este -> Av. Pablo Carriquirry -> Av. Rep. de Panamá -> Vía Expresa -> Av. Rivera Navarrete -> Calle Las Orquídeas |
| **H1 -> H3** | 1,448.7 | 2.69 | 19 | Av. Javier Prado Este -> Calle 5 -> Calle Ricardo Angulo -> Av. Pablo Carriquirry -> Zorzales |
| **H2 -> H1** | 1,033.2 | 2.20 | 10 | Av. Javier Prado Este (sentido oeste-este directo) |
| **H2 -> H3** | 1,846.1 | 3.44 | 24 | Av. Javier Prado Este -> Av. Rivera Navarrete -> Calle Andrés Reyes -> Av. Rep. de Panamá -> Av. Canaval y Moreyra -> Av. Pablo Carriquirry |
| **H3 -> H1** | 1,280.5 | 2.44 | 16 | Av. República de Panamá -> Calle Las Oropéndolas -> Av. Pablo Carriquirry |
| **H3 -> H2** | 1,931.3 | 4.37 | 24 | Av. Rep. de Panamá -> Av. Canaval y Moreyra -> Av. Juan de Arona -> Calle Las Begonias -> Calle Deán Valdivia -> Calle Las Orquídeas |

- **Prueba de bloqueo parcial (`TRAMO_0075` en H1 -> H2):** Recalcula desvío por Av. Canaval y Moreyra, Av. Juan de Arona, Las Begonias y Deán Valdivia en **6.01 min** (+0.50 min respecto a la ruta base).
- **Prueba de bloqueo total de salida (`TRAMO_0001` desde H1):** Devuelve correctamente `sin_ruta: True`.