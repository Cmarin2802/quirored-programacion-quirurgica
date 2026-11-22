# QuiroRed — Programación y coordinación quirúrgica

**UPC · Complejidad Algorítmica (1ACC0184) · 2026-20 · Grupo 5 · Hito 2**

QuiroRed es una aplicación académica que coordina solicitudes quirúrgicas entre tres sedes de referencia (H1: Clínica Ricardo Palma, H2: Clínica Javier Prado y H3: Clínica Limatambo). Permite consultar el cronograma, programar solicitudes y jornadas, registrar y resolver incidencias, evaluar rutas y alternativas de derivación entre clínicas, y estudiar el rendimiento de ocho algoritmos. Los datos operativos corresponden al modelo experimental del proyecto y no a las agendas de las clínicas mencionadas.

**Aplicación desplegada:** https://quirored-web-production.up.railway.app  
**Repositorio:** https://github.com/Cmarin2802/quirored-programacion-quirurgica

## Estado verificado del sistema

El estado de referencia restaurado y comprobado en PostgreSQL 18 contiene:

| Indicador | Valor |
|---|---:|
| Solicitudes | 1 500 |
| Cirugías programadas | 524 |
| Solicitudes pendientes | 976 |
| Eventos registrados | 35 |
| Grafo de compatibilidad | 1 704 nodos y 180 502 aristas |
| Red vial OSM | 136 nodos y 228 aristas dirigidas |
| Solapamientos detectados por el verificador | 0 |

Los recuentos operativos pueden cambiar cuando se programan casos o se registran incidencias. La comparación experimental y los verificadores utilizan datos y condiciones documentados en `benchmarks/`.

## Funcionalidades

- **Cronograma quirúrgico:** consulta por sede y jornada, salas, reservas y tiempos de limpieza.
- **Programación:** búsqueda de solicitudes pendientes, asignación individual y planificación de jornada con validación de recursos.
- **Contingencias:** incidencias de personal, quirófano, equipamiento, postoperatorio, sede y red vial; evaluación del impacto y reprogramación cuando proceda.
- **Coordinación entre clínicas:** mapa Leaflet/OpenStreetMap, cálculo de rutas, alternativas de derivación y confirmación de propuestas.
- **Área técnica:** acceso mediante clave independiente, comparación FCFS frente a Greedy y resultados de medición de ocho algoritmos. La web general no exige cuenta de usuario.

## Algoritmos implementados

| Algoritmo | Uso principal |
|---|---|
| BFS | Exploración de compatibilidad entre cirugías y recursos |
| DFS | Exploración de relaciones e impacto de incidencias |
| Greedy | Selección de asignaciones factibles |
| Programación dinámica | Selección de solicitudes según restricciones de capacidad |
| Ford-Fulkerson | Emparejamiento preliminar de solicitudes y oportunidades |
| Backtracking | Exploración de combinaciones alternativas |
| Bellman-Ford | Cálculo de rutas en la red vial dirigida |
| Prim | Estudio de conectividad y árbol de expansión mínimo |

Las técnicas se activan según el proceso; no todas se ejecutan en cada solicitud. El emparejamiento preliminar no equivale por sí mismo a una reserva quirúrgica confirmada.

## Estructura del código fuente

La raíz del repositorio mantiene las rutas relativas utilizadas por el backend:

```text
quirored-programacion-quirurgica/
├── Dockerfile
├── .dockerignore
├── README.md
├── 3 Datos/                 # Datos experimentales y diccionario
├── 4 Grafos/                # Grafo de compatibilidad
├── 9 Aplicacion Web/
│   ├── requirements.txt
│   ├── backend/             # Flask, servicios, motores, verificadores
│   └── frontend/            # HTML, CSS y JavaScript
├── geo/                     # Red vial, geometrías y datos OSM
├── benchmarks/              # Mediciones FCFS/Greedy y ocho algoritmos
├── docs/                    # Documentación técnica y diagramas
└── tests/                   # Pruebas complementarias
```

**No mover `geo/` ni `benchmarks/` dentro de `9 Aplicacion Web/`:** el código las consulta desde la raíz. El directorio `8 Motores` utilizado en la carpeta académica puede conservarse como documentación adicional, pero los motores operativos de la aplicación están en `9 Aplicacion Web/backend/motores/`.

## Requisitos

- Python 3.12 y `pip` para ejecución local, o Docker Desktop/Engine para ejecución en contenedor.
- PostgreSQL 18, con una **base de pruebas independiente y restaurada**. La aplicación no importa automáticamente todas las tablas a partir de los CSV.
- Archivo de respaldo consistente, facilitado con la entrega del curso cuando corresponda. El respaldo validado del proyecto se denomina `hospital_red_524_programadas_20261121_212052.backup`. **No se almacena en GitHub**.

El código fuente por sí solo no reproduce las 524 reservas: requiere una base PostgreSQL restaurada. Si el paquete de entrega no incluye el `.backup`, se puede evaluar el despliegue público y las pruebas de solo lectura, o solicitar la copia de demostración al equipo.

## Ejecución local en Windows (PowerShell)

1. Abrir PowerShell en la **raíz del repositorio** y crear el entorno Python:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r "9 Aplicacion Web/requirements.txt"
```

2. Crear previamente una base vacía de pruebas en PostgreSQL 18 y restaurar el respaldo en ella. Por ejemplo, si el usuario es `hospital_app` y la base se denomina `hospital_red_pruebas`:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" `
  -h 127.0.0.1 -p 5432 -U hospital_app -d hospital_red_pruebas `
  --no-owner --no-acl --single-transaction --exit-on-error `
  "C:\RUTA\AL\RESPALDO\hospital_red_524_programadas_20261121_212052.backup"
```

   **Restaurar únicamente sobre una base vacía de pruebas.** Nunca usar una base con datos que deban conservarse.

3. Configurar `DATABASE_URL` en esa terminal, sin guardar contraseñas en código:

```powershell
$segura = Read-Host "Contraseña de hospital_app" -AsSecureString
$clave = [System.Net.NetworkCredential]::new("", $segura).Password
$env:DATABASE_URL = "postgresql://hospital_app:$([uri]::EscapeDataString($clave))@127.0.0.1:5432/hospital_red_pruebas"
Remove-Variable clave, segura
```

4. Validar e iniciar la web:

```powershell
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_backend.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_frontend_integrado.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/app.py"
```

Abrir **http://127.0.0.1:5000**. Para finalizar, pulsar **Ctrl+C**. `DATABASE_URL` debe volver a configurarse en cada nueva terminal.

## Construcción con Docker

Desde la raíz del repositorio:

```powershell
docker build -t quirored:local .
```

El contenedor usa Python 3.12, Gunicorn y Flask y escucha en el puerto **8080**. Es necesario proporcionarle una variable `DATABASE_URL` que apunte a PostgreSQL accesible desde **el contenedor**, no a `localhost` del contenedor. En las pruebas de integración se utilizó una red Docker privada con el servicio PostgreSQL 18 en otro contenedor y el puerto web `127.0.0.1:5001:8080`.

La conexión a PostgreSQL, las contraseñas y los secretos deben configurarse por variables de entorno, no incluirse en la imagen ni el repositorio.

## Despliegue en Railway

El sistema se desplegó desde el `Dockerfile` de la raíz con dos servicios:

- **QuiroRed-Web:** contenedor Docker, Gunicorn/Flask, HTTPS público y puerto interno 8080.
- **Postgres:** PostgreSQL 18 con volumen persistente y conexión privada al servicio web.

Variables relevantes del servicio web: `DATABASE_URL` (referencia al servicio Postgres), `HOSPITAL_DEMO_MODE=0`, `QUIRORED_TECNICA_CLAVE`, `QUIRORED_SESSION_SECRET` y `QUIRORED_SECURE_COOKIE=1`. Las claves no deben publicarse. El acceso público TCP a PostgreSQL se utilizó únicamente para restauración y posteriormente se retiró.

El dominio de la web es **https://quirored-web-production.up.railway.app**. La dirección está sujeta a la continuidad del servicio y al plan de Railway.

## Verificación y resultados experimentales

Desde la raíz del proyecto, con `DATABASE_URL` apuntando a una base de pruebas:

```powershell
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_backend.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_algoritmos_integrados.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_interhospitalario.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_frontend_integrado.py"
```

Los verificadores comprueban respectivamente integridad/solapamientos, los ocho algoritmos, rutas y derivaciones entre sedes, y contratos básicos de frontend/API. Las operaciones interactivas que crean reservas o incidencias deben probarse **solo en una base aislada**.

Resultados reproducibles y metodología: `benchmarks/RESULTADOS.csv`, `benchmarks/RESULTADOS_ALGORITMOS.csv`, `benchmarks/OCUPABILIDAD_QUIROFANOS.csv` y documentos del mismo directorio. En una muestra de 1 500 solicitudes, FCFS programó 590 y Greedy 524; el tiempo observado promedio fue 28,032 s y 25,521 s respectivamente, ambos sin solapamientos en esa evaluación. No se concluye que una técnica sea universalmente superior.

La API de solo lectura permite consultar el resumen en: https://quirored-web-production.up.railway.app/api/estado

## Documentación y entrega

La entrega académica acompaña el código con el informe y los anexos en Word/PDF. Los diagramas de casos de uso, clases, despliegue y arquitectura se documentan en los anexos. Las fuentes de datos y sus transformaciones están en `3 Datos/`, los resultados del grafo en `4 Grafos/` y los experimentos en `benchmarks/`.

Para ejecutar una copia local con el mismo estado de referencia, se adjuntó en el zip de entrega dle trabajo el backup necesario de postgresql.
