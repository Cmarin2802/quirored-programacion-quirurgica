# QuiroRed

**Sistema académico de programación y coordinación quirúrgica** — Complejidad Algorítmica, UPC, ciclo 2026-20.

Aplicación web experimental para organizar cirugías, consultar la programación, registrar y resolver incidencias, proponer traslados entre sedes y evaluar algoritmos de asignación.

> **Datos simulados.** Las clínicas Ricardo Palma (H1), Javier Prado (H2) y Limatambo (H3) son referencias geográficas en Lima. Las cirugías, los profesionales, las salas, las capacidades y las jornadas utilizadas en la demostración son datos experimentales; **no** representan agendas reales de dichas instituciones. La red vial mostrada inicialmente es esquemática; Sebastián desarrollará su sustitución por calles verificadas.

## 1. Qué contiene el repositorio

| Carpeta | Contenido |
| --- | --- |
| `9 Aplicacion Web/` | Aplicación Flask, interfaz HTML/CSS/JavaScript, motores de programación y verificadores. |
| `3 Datos/` | Archivos CSV experimentales de solicitudes, recursos y conexiones. |
| `4 Grafos/` | Datos del grafo de compatibilidad, generador y notebook. |
| `docs/` | Instrucciones de trabajo en GitHub y encargos individuales. |
| `geo/` | Trabajo de Sebastián sobre calles y rutas reales. |
| `benchmarks/` | Trabajo de Nicolás sobre algoritmos, ocupación y rendimiento. |
| `tests/` | Pruebas complementarias. |

El repositorio **no** incluye contraseñas, un servidor PostgreSQL ni un respaldo de la base de datos. Los archivos `.backup`, `.env` y otros elementos locales están excluidos por `.gitignore`.

## 2. Requisitos para ejecutar la aplicación completa

En Windows:

1. **GitHub Desktop** o Git, para clonar el repositorio.
2. **Python 3.11 o superior** y `pip` (la aplicación principal ya se comprobó con Python 3.14).
3. **PostgreSQL y pgAdmin** instalados en su computadora. Para restaurar el respaldo existente, usar herramientas `pg_restore` compatibles con el formato del archivo (se recomienda PostgreSQL 17 o superior).
4. **El respaldo de demostración** facilitado de forma privada por el responsable del repositorio. No estará publicado en GitHub.

> **¿Todos necesitan PostgreSQL?** Sí, si desean ejecutar **toda la web** y sus acciones de programación. Para trabajar exclusivamente sobre archivos CSV, el grafo vial o scripts aislados, puede no ser necesario. Cada integrante debe tener una base **local e independiente** para no alterar los datos de otro.

## 3. Clonar e instalar Python (una sola vez por computadora)

Clonar desde GitHub Desktop: **File → Clone repository**, elegir `quirored-programacion-quirurgica` y seleccionar una carpeta local.

Abrir PowerShell en la **raíz clonada**, donde se encuentran `3 Datos`, `4 Grafos` y `9 Aplicacion Web`, y ejecutar:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r "9 Aplicacion Web/requirements.txt"
```

Si `python` no está disponible, comprobar la instalación de Python y su incorporación al PATH. Las dependencias actuales de la web son Flask y psycopg, declaradas en `requirements.txt`. Los módulos de análisis geográfico y benchmarking podrán requerir paquetes adicionales que sus responsables deberán documentar en sus respectivas carpetas.

## 4. Preparar la base de datos local (una sola vez por computadora)

**No basta con clonar GitHub:** los CSV del repositorio no reconstruyen automáticamente las tablas y el estado operativo de QuiroRed. Para una instalación completa se debe restaurar una base de prueba.

### 4.1. Obtener el respaldo

Solicitar al responsable del proyecto una **copia de demostración** del respaldo PostgreSQL, enviada por un medio privado (por ejemplo, carpeta compartida de Drive con acceso al equipo).

El respaldo histórico utilizado como referencia se llama:

`hospital_red_pre_eventos.backup`

Su ubicación en el proyecto histórico era `9 Aplicacion Web/Respaldo_Demostracion/`, pero esa carpeta está excluida de GitHub. **El respaldo histórico no tiene por qué coincidir con el estado más reciente de la computadora de César** (522 cirugías programadas); los contadores pueden ser distintos y eso, por sí mismo, no implica un error. No se ha validado todavía una restauración limpia en otra computadora.

### 4.2. Crear usuario y base de datos con pgAdmin

1. Abrir **pgAdmin** y conectarse a su servidor PostgreSQL local.
2. En **Login/Group Roles**, crear el usuario `hospital_app`, habilitar **Can login** y establecer **una contraseña propia**.
3. En **Databases**, crear una base llamada `hospital_red` y seleccionar `hospital_app` como **Owner**.
4. Verificar que PostgreSQL esté escuchando en `127.0.0.1:5432` (la conexión usada por defecto en este proyecto).

La contraseña de cada integrante es independiente; **nunca** enviarla por chat ni subirla a GitHub.

### 4.3. Restaurar el archivo `.backup`

En PowerShell, con el respaldo descargado a una carpeta local, ejecutar (ajustar la ruta del archivo):

```powershell
pg_restore -h 127.0.0.1 -p 5432 -U hospital_app -d hospital_red --no-owner --no-acl --exit-on-error "C:\RUTA\DEL\RESPALDO\hospital_red_pre_eventos.backup"
```

El programa solicitará la contraseña de `hospital_app`. Si `pg_restore` no se reconoce como comando, usar su ruta de instalación, por ejemplo:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" -h 127.0.0.1 -p 5432 -U hospital_app -d hospital_red --no-owner --no-acl --exit-on-error "C:\RUTA\DEL\RESPALDO\hospital_red_pre_eventos.backup"
```

Sustituir `17` por la versión realmente instalada y `C:\RUTA\DEL\RESPALDO\...` por la ruta real. **Restaurar solo en una base vacía de pruebas**: no hacerlo sobre una base que tenga trabajos que se deseen conservar. Si la herramienta informa una versión de archivo no compatible, usar una versión más reciente de `pg_restore`.

## 5. Conectar QuiroRed a PostgreSQL (cada terminal nueva)

Desde PowerShell, introducir la contraseña **sin mostrarla en pantalla** y crear la variable de entorno de esta sesión:

```powershell
$claveSegura = Read-Host "Contraseña local de hospital_app" -AsSecureString
$clave = [System.Net.NetworkCredential]::new("hospital_app", $claveSegura).Password
$env:DATABASE_URL = "postgresql://hospital_app:$([uri]::EscapeDataString($clave))@127.0.0.1:5432/hospital_red"
Remove-Variable clave, claveSegura
```

**Importante:** `DATABASE_URL` existe únicamente en **esa terminal**. Si se abre otra terminal de PowerShell, será necesario repetir este paso. Si se escribe una contraseña incorrecta aparecerá `password authentication failed`; **no hace falta detener Flask** para resolverlo.

No pegar la contraseña directamente en un archivo de código ni subir un `.env` con secretos.

## 6. Verificar e iniciar QuiroRed

Desde la **raíz del repositorio** y en la misma terminal que tiene `DATABASE_URL`:

```powershell
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_backend.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/verificar_frontend_integrado.py"
.\.venv\Scripts\python.exe "9 Aplicacion Web/backend/app.py"
```

Abrir **http://127.0.0.1:5000** en el navegador. Detener el servidor con **Ctrl + C**. Para actualizar los archivos JavaScript/CSS después de un cambio, recargar con **Ctrl + F5**.

Los verificadores deben indicar, respectivamente:

- `VERIFICACION_POSTGRESQL_CORRECTA` y `errores_solapamiento: 0`.
- `FRONTEND_INTEGRADO_CORRECTO`.

En la computadora del integrador se verificaron **1,500 casos, 522 programados, 978 pendientes y cero solapamientos** después de las pruebas funcionales. **No se exigen esos mismos contadores** al restaurar un respaldo histórico: las cantidades dependen del estado de cada base local. El verificador de integridad sí supone una base experimental de 1,500 casos y el grafo de compatibilidad original completo.

### Problemas frecuentes

| Mensaje o síntoma | Qué revisar |
| --- | --- |
| `can't open file ... backend/...` | Estás en la raíz incorrecta. Si estás en la raíz del repositorio, agrega `9 Aplicacion Web/` a la ruta, como en los comandos anteriores. |
| `password authentication failed` | Usuario o contraseña de PostgreSQL incorrectos. Repetir el paso 5 con la clave local correcta. |
| `Falta DATABASE_URL` | Configurar la variable en **esa misma** terminal. |
| `PostgreSQL no contiene los datos iniciales` | La base no fue restaurada, o está apuntando a una base distinta. |
| `pg_restore: command not found` o no se reconoce | Ejecutar la ruta completa de `pg_restore.exe`, dentro de `C:\Program Files\PostgreSQL\<versión>\bin\`. |
| La página no abre | Verificar que Flask siga ejecutándose, que el puerto 5000 esté disponible y que la terminal no muestre errores. |
| Aparecen cifras distintas a las del compañero | Cada uno tiene su propia base de pruebas. No se sincronizan los datos de PostgreSQL con GitHub. |

## 7. Organización del trabajo del equipo

- **César — integración:** aplicación principal, interfaz, pruebas de asignación, derivaciones e incidencias, revisión de Pull Requests y entrega final.
- **Nicolás — algoritmos:** revisar `docs/ENCARGO_NICOLAS.md`, trabajar en la rama `feature/benchmarks-optimizacion`, documentar el algoritmo base y la comparación experimental. **No utilizar la base principal de César para los benchmarks.**
- **Sebastián — red vial:** revisar `docs/ENCARGO_SEBASTIAN.md`, trabajar en la rama `feature/red-vial-real`, producir los datos y pruebas geográficas. No sobrescribir la red operativa hasta la integración coordinada.

Cada integrante crea su **rama**, hace commits y sube sus cambios con **Push**; después abre un **Pull Request** para revisión antes de integrar en `main`. El repositorio se mantendrá **privado** hasta que el equipo decida lo contrario.

**Pendientes para la integración final:** porcentaje de ocupación y resultados comparativos de Nicolás; calles/rutas reales de Sebastián; adaptación final de interfaz; Docker, URL pública, informe, anexos y evidencias. No presentar los indicadores como medidos hasta ejecutar los experimentos.

## 8. Para el responsable: preparar una copia de demostración actualizada

Si los compañeros necesitan **exactamente el mismo estado de demostración** (en lugar del respaldo histórico), el responsable puede exportar la base **después de concluir las pruebas** con la herramienta `pg_dump` de su instalación PostgreSQL:

```powershell
pg_dump -h 127.0.0.1 -p 5432 -U hospital_app -d hospital_red -F c -f "hospital_red_equipo.backup"
```

Si `pg_dump` no se reconoce, utilizar la ruta completa de `pg_dump.exe` dentro de la carpeta `bin` de PostgreSQL. Ejecutar desde una carpeta de trabajo **fuera de GitHub**. Enviar el archivo resultante por un enlace privado a los compañeros; **nunca** hacer commit del respaldo. Esta copia incluye el estado que existía al exportar y puede cambiar los recuentos respecto al respaldo histórico. Para una evaluación justa, Nicolás debe documentar el estado inicial y ejecutar sus pruebas en su propia copia, sin alterar la base del equipo.

## 9. Seguridad y reproducibilidad

- No subir `.env`, claves, `.backup`, `.dump`, bases de datos locales ni historiales privados.
- Usar **datos experimentales** para todas las demostraciones. Las clínicas nombradas no aportaron sus agendas reales.
- Antes de cambiar código compartido, actualizar la rama con los cambios del repositorio y coordinar modificaciones sobre los archivos centrales.
- Guardar capturas, resultados y pasos de ejecución reproducibles de las pruebas.

> **Estado de esta guía:** comandos y rutas contrastados con los archivos del proyecto. La aplicación principal fue comprobada contra PostgreSQL en la computadora de César; **la restauración del respaldo en una segunda computadora todavía está pendiente de prueba**. Una vez probada, documentar cualquier ajuste requerido.
