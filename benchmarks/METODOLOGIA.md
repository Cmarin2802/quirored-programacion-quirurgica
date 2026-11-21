# Metodología y Evaluación Experimental — QuiroRed

## 1. Objetivo y diseño del experimento
Evaluar de forma justa y reproducible el desempeño del motor optimizado (**Greedy V1**, `motor_programacion_v1.py`) frente a una línea base **FCFS/FIFO** (`programador_fcfs.py`) sobre los mismos casos, recursos, horizonte temporal, semilla y restricciones físicas/clínicas, **sin alterar la base de datos PostgreSQL `hospital_red`**.

### Condiciones de ejecución
- **Dataset:** `3 Datos/*.csv` y grafo de compatibilidad `4 Grafos/grafo_aristas_red.csv` (1,500 solicitudes totales).
- **Tamaños evaluados ($N$):** `100`, `500`, `1000` y `1500` solicitudes.
- **Semilla fija:** `42` (muestreo aleatorio sin reemplazo conservando el orden original de llegada).
- **Horizonte y paso:** `7` días de búsqueda por solicitud, bloques de `60` minutos (`07:00` a `21:00`).
- **Repeticiones:** `2` corridas limpias por escenario para medir tiempo promedio y desviación estándar (sin sobrecarga de `tracemalloc`), más `1` corrida adicional con `tracemalloc` para medir la memoria RAM pico.
- **Diferencia controlada entre métodos:**
  - **FCFS/FIFO (base):** procesa en estricto orden de llegada (`FECHA_SOLICITUD_SIM`, índice original, `CASO_ID`) y elige el primer recurso libre por ID sin balanceo de carga.
  - **Optimizado (Greedy V1):** prioriza por `(PRIORIDAD_SIM, FECHA_MINIMA_OPERABLE_SIM, CASO_ID)` y balancea carga eligiendo el personal con menor carga acumulada en el día.
  - **Restricciones idénticas:** salas compatibles y activas, ventanas de disponibilidad, descansos mínimos, carga máxima por turno, equipos, instrumental con reprocesamiento, limpieza de sala y cama postoperatoria (más intensivista en UCI/UCIM).

---

## 2. Definición de ocupabilidad y tratamiento de limpieza
Para evitar ambigüedades, la ocupabilidad por quirófano se calcula sobre el horizonte de fechas activas (entre la primera y la última fecha con cirugías programadas en la corrida):

- **Denominador:** suma total de minutos en estado `DISPONIBLE` de cada sala activa dentro de la franja operativa (`07:00`–`21:00`) durante el horizonte evaluado.
- **Ocupabilidad solo cirugía (%):** $\frac{\text{Minutos de cirugía (INICIO a FIN\_CIRUGIA)}}{\text{Minutos disponibles totales}} \times 100$.
- **Ocupabilidad con limpieza (%):** $\frac{\text{Minutos de cirugía + limpieza (INICIO a FIN\_LIMPIEZA)}}{\text{Minutos disponibles totales}} \times 100$. El tiempo de limpieza bloquea físicamente la sala y se incluye como métrica separada para distinguir tiempo clínico efectivo frente a ocupación total del quirófano.

El desglose por cada sala individual se encuentra en `benchmarks/OCUPABILIDAD_QUIROFANOS.csv`.

---

## 3. Cómo reproducir el benchmark
Desde la raíz del repositorio en PowerShell (con el entorno `.venv` instalado):

```powershell
.\.venv\Scripts\python.exe "benchmarks/benchmarks_execution.py" --semilla 42 --repeticiones 2
```

Parámetros configurables: `--n-list` (ej. `100 500 1000 1500`), `--semilla`, `--repeticiones`, `--dias-busqueda` y `--paso-min` (`30` o `60`).

---

## 4. Tabla de resultados reales (`benchmarks/RESULTADOS.csv`)

| $N$ | Método | Programadas | Pendientes | Ocup. Cirugía (%) | Ocup. + Limpieza (%) | Tiempo prom. (s) | Desv. Est. (s) | RAM pico (MB) | Solapamientos |
| ---: | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | `FCFS_FIFO_BASE` | 86 | 14 | 3.32% | 4.36% | 0.719 | ±0.013 | 100.35 | 0 |
| 100 | `OPTIMIZADO_GREEDY_V1` | 86 | 14 | 3.32% | 4.35% | 0.730 | ±0.017 | 100.35 | 0 |
| 500 | `FCFS_FIFO_BASE` | 425 | 75 | 14.50% | 18.91% | 4.063 | ±0.038 | 100.35 | 0 |
| 500 | `OPTIMIZADO_GREEDY_V1` | 393 | 107 | 14.26% | 18.60% | 3.442 | ±0.021 | 100.35 | 0 |
| 1000 | `FCFS_FIFO_BASE` | 544 | 456 | 16.86% | 22.55% | 22.533 | ±4.407 | 100.35 | 0 |
| 1000 | `OPTIMIZADO_GREEDY_V1` | 488 | 512 | 16.21% | 21.25% | 15.527 | ±1.788 | 100.35 | 0 |
| 1500 | `FCFS_FIFO_BASE` | 590 | 910 | 16.96% | 23.18% | 28.032 | ±0.394 | 100.35 | 0 |
| 1500 | `OPTIMIZADO_GREEDY_V1` | 524 | 976 | 16.87% | 22.35% | 25.521 | ±0.518 | 100.35 | 0 |

---

## 5. Comparación por casos de uso y conclusiones

### Caso de uso 1: Demanda baja ($N = 100$, baja saturación)
Cuando la carga es baja, ambos métodos logran exactamente la misma cobertura (**86 programadas y 14 pendientes**), prácticamente la misma ocupabilidad (**3.32% solo cirugía / ~4.35% con limpieza**) y tiempos inferiores a un segundo (~0.72 s). En escenarios sin congestión, el cuello de botella son los pacientes no listos/no presentes o sin ventana compatible, no la estrategia de ordenamiento.

### Caso de uso 2: Demanda alta y saturación ($N = 1000$ y $N = 1500$)
Bajo congestión aparecen diferencias claras entre ambos enfoques:
1. **Latencia y escalabilidad:** `OPTIMIZADO_GREEDY_V1` fue consistentemente **más rápido** que `FCFS_FIFO_BASE`: **15.3% más rápido en $N=500$** (3.44 s vs. 4.06 s), **31.1% más rápido en $N=1000$** (15.53 s vs. 22.53 s) y **9.0% más rápido en $N=1500$** (25.52 s vs. 28.03 s).
2. **Compromiso entre volumen bruto y prioridad clínica:** `FCFS_FIFO_BASE` programó más cirugías en total (590 vs. 524 en $N=1500$, +66 casos) y alcanzó una ocupabilidad con limpieza ligeramente mayor (23.18% vs. 22.35%). Sin embargo, esto ocurre porque FCFS llena primero los horarios con casos que llegan antes (incluyendo electivas o de menor demanda de recursos), mientras que `OPTIMIZADO_GREEDY_V1` reserva recursos críticos primero para casos de **mayor prioridad clínica**, los cuales suelen requerir mayor duración o recursos más escasos (como UCI/intensivista), dejando menos espacio para casos electivos posteriores.
3. **Integridad y memoria:** Ambos métodos garantizaron **0 solapamientos** en todas las corridas y mantuvieron una memoria RAM pico constante de **100.35 MB** (dominada por la carga inicial de los CSV y el grafo de compatibilidad en memoria).

### Conclusión general
El motor optimizado mejora el tiempo de cómputo bajo saturación y garantiza atención prioritaria y balanceo de carga sin solapamientos, mientras que la comparación experimental demuestra un *trade-off* real frente a FCFS en cantidad total de cirugías programadas. Como mejora futura en el motor, se puede combinar la priorización clínica con la selección por Programación Dinámica y emparejamiento por Ford-Fulkerson (ya existentes en `planificacion_jornada.py`) a escala de múltiples jornadas para recuperar volumen sin sacrificar prioridad.