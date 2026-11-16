# Encargo de Sebastián — Grafo vial con calles reales

**Rama GitHub:** `feature/red-vial-real`  
**Objetivo:** sustituir el modelo vial esquemático `VIA_01...VIA_06` por conexiones fundamentadas en calles e intersecciones reales de Lima.

## Tres sedes definidas por el equipo

| Código interno | Nombre visible | Dirección de referencia |
|---|---|---|
| H1 | Clínica Ricardo Palma | Av. Javier Prado Este 1066, San Isidro |
| H2 | Clínica Javier Prado | Av. Javier Prado Este 499, San Isidro |
| H3 | Clínica Limatambo | Av. República de Panamá 3606, San Isidro |

**Clave:** conserva H1/H2/H3 como IDs técnicos. Son clínicas privadas usadas solo como **referencias geográficas**. Médicos, quirófanos y solicitudes del proyecto siguen siendo simulados.

## Qué debes investigar e implementar

1. Obtener de OpenStreetMap/OSMnx un **grafo vial dirigido** con calles, intersecciones, sentido de circulación, coordenadas y distancias. Identificar las tres sedes verificando el punto de acceso vial; no suponer que geocodificar un número de calle localiza la entrada de ambulancias.
2. Guardar un CSV o GraphML de nodos y aristas con IDs estables, latitud/longitud, nombre de vía, origen/destino, longitud y **costo temporal estimado**. Documentar la velocidad supuesta; no afirmar que es tráfico en vivo.
3. Ajustar o crear un adaptador que respete los campos que hoy utiliza `9 Aplicacion Web/backend/motores/red_vial.py`: `CONEXION_ID`, `ORIGEN_NODO`, `DESTINO_NODO`, `TIEMPO_MIN_SIM`, `ESTADO`. No reemplazar directamente los archivos activos ni modificar PostgreSQL.
4. Demostrar Bellman-Ford en las seis direcciones H1→H2/H3, H2→H1/H3, H3→H1/H2; registrar el camino y tiempo calculado. Añadir al menos una prueba de bloqueo vial con ruta alternativa o explicación de “sin ruta”.
5. Documentar procedencia de calles, fecha de extracción, licencia y atribución `© OpenStreetMap contributors`.
6. Preparar un **mapa legible** y una guía corta para integrar el grafo en la aplicación; la interfaz actual utiliza coordenadas SVG fijas. La integración con frontend la coordinamos después.

## Archivos que debes revisar

- `3 Datos/conexiones_red.csv`, `3 Datos/puntos_viales_red.csv` y `3 Datos/hospitales_red.csv` (todos **antiguos/simulados**).
- `9 Aplicacion Web/backend/motores/red_vial.py`
- `9 Aplicacion Web/backend/app.py`: rutas `/api/red` y `/api/ruta`.
- `9 Aplicacion Web/frontend/static/app.js`: función `cargarRed()` y coordenadas SVG (solo consulta; la edición de UI la coordina César).

## Entregables y aceptación

En `geo/`: script Python de extracción/generación, archivos de nodos/aristas, `FUENTES_Y_CALLES.md`, pruebas automatizables de rutas y bloqueo, y mapa. Conexiones dirigidas, nombres reales verificables, costos documentados y tests reproducibles.

**No te corresponde ahora:** Docker, despliegue, editar la interfaz, ajustar PostgreSQL o cambiar la programación quirúrgica. Esta fase es exclusivamente el grafo vial y sus pruebas.
