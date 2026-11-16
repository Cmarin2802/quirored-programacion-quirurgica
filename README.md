# Red quirúrgica experimental — base inicial para GitHub

**Origen:** `TB2 feedback.zip`, aplicación operativa ubicada en `9 Aplicacion Web`.  
**Fecha:** 16 de noviembre de 2026.  
**Estado:** primera actualización visual aprobada por el equipo; no incorpora todavía red vial real, experimento comparativo, Docker ni despliegue público.

## Qué sí cambió

- H1 = **Clínica Ricardo Palma**, H2 = **Clínica Javier Prado**, H3 = **Clínica Limatambo**, solo **como nombres y direcciones geográficas de referencia**.
- Los formularios, cronograma, rutas y resultados muestran nombres más claros, procedentes del catálogo de sedes y de los CSV de recursos simulados.
- Se agregó `/api/sedes` y `catalogo_sedes.py` sin modificar las tablas de PostgreSQL ni los identificadores H1/H2/H3.
- Se conserva el parche de CSV para incidencias que ya existía en `TB2 feedback.zip`.

**Atención:** las tres instituciones son privadas. El objetivo académico previo decía «hospitales públicos»: deberá ajustarse la redacción de informe y diagramas tras cerrar el alcance. El personal, salas, horarios y cirugías **NO** son datos de esas clínicas; siguen siendo simulados. Los nodos `VIA_01..VIA_06` y tiempos viales actuales son ficticios, pendientes del trabajo de Sebastián.

Direcciones consultadas (referencias, no geocodificación de puertas):
- Ricardo Palma: Av. Javier Prado Este 1066, San Isidro. [Sitio oficial](https://preguntasfrecuentes.crp.com.pe/ubicaci%C3%B3n-de-la-cl%C3%ADnica)
- Javier Prado: Av. Javier Prado Este 499, San Isidro. [Sitio oficial](https://cjp.pe/contacto/)
- Limatambo: Av. República de Panamá 3606, San Isidro. [Directorio Rímac 2026](https://imagescdn.rimac.com/blteb037de98628eb08/69a1dee7e0cee65e0e39098c/Red_de_clinicas_afiliadas_2026_V2_%281%29.pdf)

## Organización

- `9 Aplicacion Web/`: frontend HTML/CSS/JS, backend Flask y motores Python **operativos**. La única copia activa de los motores está dentro de `backend/motores/`.
- `3 Datos/`: insumos CSV experimentales. Los dos CSV originales limpios más voluminosos quedaron fuera del ZIP GitHub; se conservan en el material histórico de OneDrive.
- `4 Grafos/`: constructor/notebook histórico y validación; aún puede requerir ajustar rutas de archivos para regeneración.
- `docs/`: guía de GitHub Desktop y encargos. `geo/` y `benchmarks/`: espacios de trabajo acordados.
- **No contiene un respaldo de PostgreSQL** ni secretos. El backup histórico de OneDrive debe restaurarse aparte, una vez verificado.

## Ejecutar en Windows (después de restaurar PostgreSQL en una base DE DEMOSTRACIÓN)

Desde esta carpeta raíz que contiene `9 Aplicacion Web`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r "9 Aplicacion Web/requirements.txt"

$claveSegura = Read-Host "Contraseña PostgreSQL de hospital_app" -AsSecureString
$clave = [System.Net.NetworkCredential]::new("hospital_app", $claveSegura).Password
$env:DATABASE_URL = "postgresql://hospital_app:$([uri]::EscapeDataString($clave))@127.0.0.1:5432/hospital_red_demo"
Remove-Variable clave, claveSegura

.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_backend.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_algoritmos_integrados.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_interhospitalario.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_frontend_integrado.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/app.py"
```

Abre http://127.0.0.1:5000. **No se puede inicializar automáticamente la BD solo con este ZIP**; necesita backup restaurado y usuario de PostgreSQL con permisos suficientes. No ejecutar incidencias o programaciones sobre la base principal del equipo.

## Para publicar y trabajar en equipo

1. Lee `docs/GUIA_GITHUB_DESKTOP.md`.
2. Crea un repositorio **privado** con GitHub Desktop y publica la carpeta completa, sin colocarla dentro del antiguo directorio de OneDrive.
3. Invita a Nicolás y Sebastián. Ellos trabajarán por ramas y Pull Requests, con revisión de César antes de integrar.
4. Lee `docs/ENCARGO_NICOLAS.md` y `docs/ENCARGO_SEBASTIAN.md`. **Sebastián solo realiza red vial; Docker se prepara al final**.

## Verificación disponible

Pruebas estáticas Python/JS y tests del catálogo se ejecutaron sobre esta versión. **No se comprobó aquí una ejecución completa contra la instancia PostgreSQL de tu computadora**, ni una restauración del backup; esa prueba será el próximo paso antes de considerar `main` funcionalmente validada.
