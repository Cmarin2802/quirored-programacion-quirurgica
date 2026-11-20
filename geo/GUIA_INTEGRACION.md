# Guía de Integración — Red Vial Real (`feature/red-vial-real`)

## 1. Integración en Backend (`app.py` y `motores/red_vial.py`)

El motor `9 Aplicacion Web/backend/motores/red_vial.py` **no requiere cambios en su lógica matemática**, ya que `construir_arcos()` y `bellman_ford()` operan sobre listas de diccionarios con las llaves estándar:
- `CONEXION_ID`
- `ORIGEN_NODO`
- `DESTINO_NODO`
- `TIEMPO_MIN_SIM`
- `ESTADO`

Para activar la red real en producción/integración:
1. Reemplazar los datos cargados en PostgreSQL (o en `3 Datos/`) por `geo/hospitales_red_real.csv`, `geo/puntos_viales_red_real.csv` y `geo/conexiones_red_real.csv` (o invocar `geo/adaptador_red_vial.py`).
2. Asegurarse de que la columna `TIEMPO_MIN_SIM` entera se mantenga para `/api/red` (donde `app.py` ejecuta `int(x['TIEMPO_MIN_SIM'])`), mientras que `TIEMPO_MIN_EXACTO` puede usarse en `/api/ruta` si se desean decimales.

## 2. Adaptación de Interfaz (`9 Aplicacion Web/frontend/static/app.js`)

Actualmente, `cargarRed()` en `app.js` dibuja un `<svg id="grafo">` usando un diccionario estático (`const coords = {H1:[90,60], ...}`) y agrupa pares de aristas sin distinguir sentido único (`[a.desde, a.hasta].sort()`).

Para mostrar la red real de San Isidro existen dos opciones recomendadas:
- **Opción A (Proyección lineal en el SVG actual — cambio mínimo):**
  Incluir `lat` y `lon` en la respuesta de `/api/red` (ya soportado por `obtener_payload_api_red()` en `adaptador_red_vial.py`) y proyectar linealmente las coordenadas geográficas al `viewBox` del SVG (`x = (lon - minLon) / (maxLon - minLon) * ancho`, `y = (maxLat - lat) / (maxLat - minLat) * alto`), dibujando marcadores de flecha (`marker-end`) para reflejar el sentido dirigido de las calles de San Isidro.
- **Opción B (Mapa cartográfico con Leaflet.js):**
  Sustituir el `<svg id="grafo">` por un contenedor Leaflet usando las coordenadas `lat`/`lon` reales de cada nodo y dibujando polilíneas color `#c8525b` (punteadas) cuando `bloqueada === true`.