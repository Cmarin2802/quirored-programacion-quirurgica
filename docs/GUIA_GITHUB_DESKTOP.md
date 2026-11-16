# GitHub Desktop — publicar la base en equipo

## 1. Prepara la carpeta

1. **No borres** tu `TRABAJO FINAL ENCAMINADO` original ni el backup PostgreSQL.
2. Extrae `RED_QUIROFANOS_GITHUB_BASE_LIMATAMBO_16NOV2026.zip` en una ubicación nueva, por ejemplo `D:\1 UPC\Complejidad algorítmica\GITHUB_RED_QUIROFANOS`.
3. En el explorador, entra a la carpeta extraída hasta encontrar `README.md`, `.gitignore`, `9 Aplicacion Web`, `3 Datos` y `docs`. **Esa es la carpeta que se publicará**.

## 2. Crear el repositorio (no necesitas terminal)

1. Abre GitHub Desktop e inicia sesión en GitHub (`File > Options > Accounts`, si aún no lo hiciste).
2. Ve a **File > Add local repository > Choose** y señala la carpeta que contiene `README.md`.
3. Si aparece **This directory does not appear to be a Git repository**, usa **Create a repository here** para iniciar Git en esa misma carpeta (no crees un nivel adicional).
4. Revisa la pestaña **Changes**. Escribe un resumen como `Base del proyecto tras retroalimentación` y selecciona **Commit to main**.
5. Pulsa **Publish repository**. Elige un nombre, por ejemplo `red-quirofanos-algoritmos`, y **mantén seleccionado Keep this code private**.
6. Comprueba en GitHub web que aparecen `README.md`, `9 Aplicacion Web`, `3 Datos` y `docs` y que NO existen `.env`, `.backup`, `.dump` ni contraseñas.

## 3. Invitar a Nicolás y Sebastián

1. Abre el repositorio publicado en GitHub web.
2. Entra a **Settings > Collaborators** (la ubicación exacta del menú puede variar según la interfaz).
3. Selecciona **Add people** y escribe cada usuario de GitHub. Ellos aceptan la invitación.
4. Envíales el enlace al repositorio y sus archivos `docs/ENCARGO_*.md`.

## 4. Cómo colaboran sin sobreescribirse

1. Cada integrante abre/clona el repositorio en GitHub Desktop.
2. **Nicolás** crea la rama `feature/benchmarks-optimizacion`; **Sebastián**, `feature/red-vial-real`.
3. Cambian solo sus archivos asignados, hacen **Commit**, luego **Push origin** y crean un **Pull Request**.
4. Antes de aprobar un PR, César revisa archivos y resultados; luego actualiza su rama principal con **Fetch origin / Pull origin**.
5. Para una nueva tarea, crear rama desde `main` actualizada; no editar a la vez `app.py`, `app.js` ni el esquema SQL sin acuerdo.

## 5. Qué NO hacer

- No subir el archivo `hospital_red_pre_eventos.backup`, contraseñas o `.env` de la computadora.
- No usar el mismo PostgreSQL para pruebas de escritura de los tres integrantes.
- No reemplazar la aplicación antigua por este ZIP hasta verificar la nueva presentación con una base demo y los verificadores.
- No presentar todavía la red vial como calles reales, ni afirmar que la aplicación está desplegada públicamente.

**Nota:** esta guía usa GitHub Desktop. No se necesita TortoiseSVN, ni Docker ahora. Docker se analizará al final para entrega y posterior despliegue.
