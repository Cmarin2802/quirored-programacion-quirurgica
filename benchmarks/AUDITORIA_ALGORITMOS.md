# Auditoría de Algoritmos — QuiroRed

> **Nota:** Auditoría realizada sobre el código real del repositorio (`9 Aplicacion Web/backend/`) sin eliminar ningún algoritmo.

## 1. Resumen ejecutivo y clasificación de uso

### A. Algoritmos usados en operaciones reales de la web (8)
| # | Algoritmo | Archivo y función | Invocación desde la web | Coste estimado | Utilidad principal |
| --- | --- | --- | --- | --- | --- |
| 1 | **BFS (Anchura)** | `motores/algoritmos_integrados.py` → `bfs_compatibilidades` | Al instanciar `Programador` en `POST /api/programaciones/jornada`, `POST /api/programaciones/pendiente` e incidencias | $O(\text{grado}(u))$ (límite nivel 1) | Extraer recursos candidatos compatibles por `CASO_ID` desde el grafo de compatibilidad. |
| 2 | **Greedy (Voraz)** | `motores/motor_programacion_v1.py` → `Programador.intentar`, `elegir`, `ejecutar` | `POST /api/programaciones/jornada`, `POST /api/programaciones/pendiente` y reprogramación ante incidencias | $O(N \cdot D \cdot S \cdot R \log R)$ | Asignar el primer bloque horario válido seleccionando recursos con menor carga acumulada. |
| 3 | **Programación Dinámica** | `motores/algoritmos_integrados.py` → `seleccionar_dinamica` | `POST /api/programaciones/jornada` (`planificacion_jornada.py`) | $O(N \cdot K \cdot C)$ | Seleccionar el subconjunto óptimo de hasta $K$ cirugías que maximiza prioridad y uso de capacidad (bloques de 30 min). |
| 4 | **Ford-Fulkerson (Edmonds-Karp)** | `motores/algoritmos_integrados.py` → `ford_fulkerson` | `POST /api/programaciones/jornada` (`planificacion_jornada.py`) | $O(F \cdot E)$ ($F \le K$) | Emparejar cirugías seleccionadas por DP con pares `(sala, hora)` mediante flujo máximo en red bipartita unitaria. |
| 5 | **Backtracking** | `motores/algoritmos_integrados.py` → `backtracking_asignacion` | Respaldo en `POST /api/programaciones/jornada` y en `buscar_espacio` (`POST /api/programaciones/pendiente` / incidencias) | Exponencial, acotado por `max_intentos` (300–2500) | Encontrar combinaciones completas de recursos cuando el enfoque Greedy falla, usando heurística MRV (menor número de opciones primero). |
| 6 | **Bellman-Ford** | `motores/red_vial.py` → `bellman_ford` | `GET /api/ruta`, `POST /api/programaciones/pendiente` y derivaciones urgentes en `POST /api/programaciones/jornada` | $O(V \cdot E)$ | Calcular el camino mínimo en minutos simulados entre hospitales considerando vías bloqueadas. |
| 7 | **DFS (Profundidad)** | `motores/algoritmos_integrados.py` → `dfs_impacto` | `POST /api/incidencias` y `POST /api/simulacion/paso` (vía `motores/generador_eventos_v2.py`) | $O(V + E)$ | Recorrer el grafo inverso desde un recurso afectado para identificar qué casos válidos dependen de él. |
| 8 | **Prim (MST)** | `motores/red_vial.py` → `prim` | `POST /api/incidencias` y `POST /api/simulacion/paso` (vía `motores/generador_eventos_v2.py`) | $O(E \log V)$ | Construir el árbol de expansión mínima sobre la red vial proyectada como grafo no dirigido para verificar conectividad estructural antes y después de bloqueos. |

### B. Algoritmos ejecutados solo en verificadores / pruebas (0)
Tras rastrear las referencias en todo el backend, **ningún algoritmo es exclusivo de verificadores**: los 8 algoritmos se invocan en flujos reales de la aplicación web, aunque todos cuentan además con pruebas de comprobación en `verificar_algoritmos_integrados.py`.

---

## 2. Fichas técnicas detalladas

### 1. BFS — Búsqueda en Anchura (`bfs_compatibilidades`)
- **Archivo:** `9 Aplicacion Web/backend/motores/algoritmos_integrados.py`
- **Clasificación:** Operación real de la web.
- **Invocación:** Se ejecuta en `Programador.__init__` cada vez que el backend carga el estado (`planificacion_jornada.py`, `programacion_manual.py`, `generador_eventos_v2.py`, etc.).
- **Entradas:** `adyacencia` (diccionario de listas `(destino, relacion)`) y `origen` (`CASO_ID`).
- **Salidas:** Tupla `(relaciones, visitados)` donde `relaciones` agrupa recursos candidatos por tipo de relación.
- **Flujo de ejecución:**
  1. Inicializa una cola `deque` con `(origen, 0)` y el conjunto `visitados`.
  2. Extrae el nodo actual; si `nivel >= 1`, detiene la expansión.
  3. Agrega cada `(destino, relacion)` a `relaciones[relacion]` y marca el nodo como visitado.
- **Coste estimado:** Teórico $O(V + E)$; en la práctica $O(\text{grado}(u))$ porque corta en `nivel >= 1`.
- **Utilidad:** Desacopla la lectura del grafo de compatibilidad y alimenta el diccionario `self.candidatos` de `Programador`.

### 2. Greedy — Programación Voraz (`Programador.ejecutar`, `intentar`, `elegir`)
- **Archivo:** `9 Aplicacion Web/backend/motores/motor_programacion_v1.py`
- **Clasificación:** Operación real de la web.
- **Invocación:** `POST /api/programaciones/jornada` (tras DP y Ford-Fulkerson), `POST /api/programaciones/pendiente` (vía `buscar_asignacion` → `buscar_espacio`) y reprogramación ante incidencias.
- **Entradas:** Lista de casos, hospital, fecha/hora, disponibilidad, reservas activas y opcionalmente recursos forzados (`forzar`).
- **Salidas:** Diccionario con la asignación completa (sala, personal, equipos, instrumental, limpieza y postoperatorio) o `None`.
- **Flujo de ejecución:**
  1. En lote (`ejecutar`), ordena casos por `(PRIORIDAD_SIM, FECHA_MINIMA_OPERABLE_SIM, CASO_ID)`.
  2. Recorre días y bloques horarios buscando el primer horario donde `intentar` logre reservar todos los roles requeridos.
  3. En `elegir`, filtra candidatos compatibles/libres y ordena por `(carga_acumulada, rid)` eligiendo el menos cargado.
- **Coste estimado:** $O(N \cdot D \cdot S \cdot R \log R)$ en lote ($N$ casos, $D$ días, $S$ bloques horarios, $R$ recursos candidatos).
- **Utilidad:** Motor principal de asignación rápida sin solapamientos y con balanceo básico de carga de personal.

### 3. Programación Dinámica (`seleccionar_dinamica`)
- **Archivo:** `9 Aplicacion Web/backend/motores/algoritmos_integrados.py`
- **Clasificación:** Operación real de la web.
- **Invocación:** `POST /api/programaciones/jornada` (`planificacion_jornada.py`).
- **Entradas:** `casos` elegibles (hasta 70 candidatos filtrados), `capacidad` libre de salas en minutos y `max_casos` (1 a 15).
- **Salidas:** Lista ordenada de `CASO_ID` seleccionados.
- **Flujo de ejecución:**
  1. Discretiza la capacidad y duración de cada caso en bloques de 30 minutos.
  2. Calcula el valor de cada caso como `200 - 25 * prioridad + min(20, peso)`.
  3. Resuelve una mochila 2D sobre estados `(cantidad_casos, bloques_usados)` conservando el mayor puntaje.
- **Coste estimado:** Tiempo $O(N \cdot K \cdot C)$ y espacio $O(K \cdot C)$, donde $K = \text{max\_casos}$ y $C = \lfloor \text{capacidad}/30 \rfloor$.
- **Utilidad:** Decide qué subconjunto de cirugías programar en la jornada antes de asignar salas y personal.

### 4. Ford-Fulkerson / Edmonds-Karp (`ford_fulkerson`)
- **Archivo:** `9 Aplicacion Web/backend/motores/algoritmos_integrados.py`
- **Clasificación:** Operación real de la web.
- **Invocación:** `POST /api/programaciones/jornada` (`planificacion_jornada.py`), inmediatamente después de `seleccionar_dinamica`.
- **Entradas:** Diccionario `emparejamientos` que mapea cada `CASO_ID` seleccionado a una lista de tuplas `(SALA_ID, HH:MM)`.
- **Salidas:** Diccionario `{CASO_ID: (SALA_ID, HH:MM)}` con el emparejamiento máximo.
- **Flujo de ejecución:**
  1. Construye una red de flujo con fuente `S`, nodos de caso `C`, nodos de recurso-horario `R` y sumidero `T`, todos con capacidad 1.
  2. Busca caminos aumentantes mediante BFS (Edmonds-Karp) y actualiza las capacidades residuales.
  3. Extrae las aristas saturadas (`capacidad[R][C] == 1`) como propuesta inicial de sala y hora para `Programador.intentar`.
- **Coste estimado:** $O(F \cdot E)$ con flujo máximo $F \le K$ (en el peor caso general $O(V \cdot E^2)$).
- **Utilidad:** Maximiza el número de cirugías seleccionadas que obtienen un bloque `(sala, hora)` distinto antes de validar el resto del equipo.

### 5. Backtracking (`backtracking_asignacion`)
- **Archivo:** `9 Aplicacion Web/backend/motores/algoritmos_integrados.py`
- **Clasificación:** Operación real de la web (mecanismo de respaldo).
- **Invocación:** `POST /api/programaciones/jornada` (si Greedy falla en todos los bloques del día) y `buscar_espacio` en `motor_reprogramacion_v1.py` (usado por `programacion_manual.py` e incidencias).
- **Entradas:** Instancia de `Programador`, `caso`, `hospital`, `dia`, `inicio` y `max_intentos` (300 en reprogramación, 2500 por defecto).
- **Salidas:** Diccionario de asignación con `METODO = "BACKTRACKING_ASIGNACION"` o `None`.
- **Flujo de ejecución:**
  1. Recolecta todos los recursos válidos y libres por cada rol requerido.
  2. Ordena los roles de menor a mayor cantidad de opciones disponibles (heurística MRV).
  3. Explora combinaciones recursivamente sin repetir recursos hasta que `programador.intentar(..., forzar=asignados)` confirme validez o se alcance `max_intentos`.
- **Coste estimado:** Exponencial en el peor caso, acotado en la práctica por `max_intentos`.
- **Utilidad:** Resuelve asignaciones complejas donde la elección voraz de un rol bloquea a otro rol posterior.

### 6. Bellman-Ford (`bellman_ford`)
- **Archivo:** `9 Aplicacion Web/backend/motores/red_vial.py`
- **Clasificación:** Operación real de la web.
- **Invocación:** `GET /api/ruta` (`app.py`), `motor_interhospitalario.py` (`buscar_asignacion`, llamado desde `programacion_manual.py` y urgencias en `planificacion_jornada.py`) y `evento_ruta` (`motor_reprogramacion_v1.py`).
- **Entradas:** Lista de arcos dirigidos habilitados `(origen, destino, peso, id)`, nodo `origen` y nodo `destino`.
- **Salidas:** Diccionario `{'origen', 'destino', 'camino', 'tiempo_min_sim'}` o `None` si no hay ruta.
- **Flujo de ejecución:**
  1. Inicializa distancias en $\infty$ (0 para el origen).
  2. Relaja todos los arcos hasta $|V| - 1$ veces con corte temprano si no hubo cambios.
  3. Reconstruye el camino mínimo desde `destino` hacia `origen` mediante el diccionario `padre`.
- **Coste estimado:** Tiempo $O(V \cdot E)$ y espacio $O(V)$.
- **Utilidad:** Calcula tiempos de traslado simulados entre sedes para evaluar derivaciones interhospitalarias y rutas activas.

### 7. DFS — Búsqueda en Profundidad (`dfs_impacto`)
- **Archivo:** `9 Aplicacion Web/backend/motores/algoritmos_integrados.py`
- **Clasificación:** Operación real de la web.
- **Invocación:** `POST /api/incidencias` y `POST /api/simulacion/paso` (vía `motores/generador_eventos_v2.py`), además de `verificar_algoritmos_integrados.py`.
- **Entradas:** `adyacencia_inversa` (`grafo_inverso`), `recurso` (ID de sala/recurso) y conjunto `casos_validos`.
- **Salidas:** Conjunto `afectados` con los `CASO_ID` alcanzables desde ese recurso.
- **Flujo de ejecución:** Recorrido iterativo con pila (`pendientes.pop()`), registrando visitados y acumulando los nodos que pertenecen a `casos_validos`.
- **Coste estimado:** Tiempo y espacio $O(V + E)$.
- **Utilidad:** Identifica los casos vinculados o potencialmente impactados cuando ocurre una incidencia sobre un recurso.

### 8. Prim — Árbol de Expansión Mínima (`prim`)
- **Archivo:** `9 Aplicacion Web/backend/motores/red_vial.py`
- **Clasificación:** Operación real de la web (análisis estructural ante incidencias).
- **Invocación:** `POST /api/incidencias` y `POST /api/simulacion/paso` (vía `motores/generador_eventos_v2.py`, calculando `antes_prim` y `despues_prim`), además de `evento_ruta` en `motor_reprogramacion_v1.py` y `verificar_algoritmos_integrados.py`.
- **Entradas:** Lista de `arcos` habilitados y conjunto opcional de `nodos`.
- **Salidas:** Diccionario `{'aristas', 'costo_total_min_sim', 'conexo'}`.
- **Flujo de ejecución:** Proyecta la red dirigida como grafo no dirigido tomando el menor peso entre pares de nodos y expande el MST usando una cola de prioridad (`heapq`).
- **Coste estimado:** Tiempo $O(E \log V)$ y espacio $O(V + E)$.
- **Utilidad:** Diagnóstico estructural de conectividad global de la red vial antes y después de bloqueos de ruta; el propio código aclara que no sirve como camino mínimo entre hospitales.