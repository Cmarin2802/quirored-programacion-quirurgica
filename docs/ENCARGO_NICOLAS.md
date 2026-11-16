# Encargo de Nicolás — Algoritmos y evaluación experimental

**Rama GitHub:** `feature/benchmarks-optimizacion`  
**Objetivo:** demostrar que los algoritmos mejoran la programación de quirófanos, no solo que se ejecutan.

## Revisar estos archivos

- `9 Aplicacion Web/backend/planificacion_jornada.py`
- `9 Aplicacion Web/backend/programacion_manual.py`
- `9 Aplicacion Web/backend/motores/algoritmos_integrados.py`
- `9 Aplicacion Web/backend/motores/motor_programacion_v1.py`
- `9 Aplicacion Web/backend/motores/motor_reprogramacion_v1.py`
- `9 Aplicacion Web/backend/motores/motor_interhospitalario.py` y `red_vial.py`

## Qué debes construir y entregar

1. **Auditoría de los ocho algoritmos**: función, archivo, flujo de ejecución, cuándo se invoca desde la web, entradas/salidas, coste estimado y utilidad. Separar algoritmos usados realmente en operaciones de los ejecutados solo en verificadores. No eliminar ninguno antes de la auditoría.
2. **Programador base FCFS/FIFO** que procese solicitudes pendientes en orden de llegada **respetando exactamente las mismas restricciones** de salas, personal, instrumental, disponibilidad y limpieza. Es la comparación justa del “antes”.
3. **Benchmark reproducible** sobre N=100, 500, 1000 y 1500 solicitudes, con los mismos casos, recursos, horizonte y semilla en FCFS y en el método optimizado. No modificar `hospital_red` original.
4. **Tabla real** con cirugías programadas/pendientes, **ocupabilidad por quirófano**, tiempo de ejecución, memoria RAM pico y solapamientos (esperado: cero). Definir denominador de ocupabilidad y tratamiento de limpieza. Si mides latencia, repetir corridas y mostrar dispersión.
5. **Comparación y conclusión** por uno o dos casos de uso representativos. Los valores A1/A2/A3 de la tabla del profesor son ilustrativos, **no se copian como resultados**.
6. Completar el diagrama de clases conforme al sistema, sin inventar entidades ni métodos.

## Entregables en GitHub

`benchmarks/AUDITORIA_ALGORITMOS.md`, `benchmarks/METODOLOGIA.md`, `benchmarks/RESULTADOS.csv`, scripts reproducibles y versión del diagrama de clases en `docs/`.

## Criterios de aceptación

- Cualquier integrante puede repetir las pruebas siguiendo un README, con N y semilla configurables.
- Comparación con los mismos casos/restricciones, sin errores de solapamiento.
- Las cifras proceden de ejecuciones, no de ejemplos o supuestos.
- Los cambios van por Pull Request sin editar `app.py`, `app.js`, PostgreSQL principal o el motor central sin coordinación.

**No te corresponde ahora:** calles reales ni Docker.
