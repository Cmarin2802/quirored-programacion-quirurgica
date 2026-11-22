/* Vista independiente de solo lectura. No realiza operaciones sobre PostgreSQL. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const formato = (numero, decimales = 0) => Number(numero || 0).toLocaleString('es-PE', {
    minimumFractionDigits: decimales, maximumFractionDigits: decimales
  });
  const texto = (contenedor, etiqueta, contenido, clase) => {
    const elemento = document.createElement(etiqueta);
    elemento.textContent = String(contenido);
    if (clase) elemento.className = clase;
    contenedor.append(elemento);
    return elemento;
  };
  const celda = (fila, contenido) => texto(fila, 'td', contenido);
  const metrica = (titulo, valor, subtitulo) => {
    const card = document.createElement('div');
    card.className = 'metric';
    texto(card, 'span', titulo);
    texto(card, 'strong', valor);
    texto(card, 'small', subtitulo);
    return card;
  };
  let estado = null;
  function renderComparacion() {
    if (!estado) return;
    const n = $('tecnica-n').value;
    const resultados = estado.fcfs_greedy.filter((r) => String(r.N_SOLICITUDES) === n);
    const fcfs = resultados.find((r) => r.METODO === 'FCFS_FIFO_BASE');
    const greedy = resultados.find((r) => r.METODO === 'OPTIMIZADO_GREEDY_V1');
    $('metricas').replaceChildren();
    $('barras').replaceChildren();
    $('detalle-fcfs').replaceChildren();
    if (!fcfs || !greedy) {
      $('metricas').append(metrica('Sin mediciones', '—', 'No hay datos válidos para esta cantidad.'));
      return;
    }
    $('metricas').append(
      metrica('Programadas FCFS', formato(fcfs.PROGRAMADAS), 'Orden de llegada'),
      metrica('Programadas Greedy', formato(greedy.PROGRAMADAS), 'Orden de prioridad'),
      metrica('Tiempo FCFS', `${formato(fcfs.TIEMPO_PROMEDIO_S, 2)} s`, 'Promedio observado'),
      metrica('Tiempo Greedy', `${formato(greedy.TIEMPO_PROMEDIO_S, 2)} s`, 'Promedio observado')
    );
    const mayor = Math.max(1, Number(fcfs.PROGRAMADAS), Number(greedy.PROGRAMADAS));
    for (const [nombre, resultado, clase] of [['FCFS', fcfs, ''], ['Greedy', greedy, 'greedy']]) {
      const row = document.createElement('div');
      row.className = `bar-row ${clase}`;
      texto(row, 'span', nombre);
      const track = document.createElement('div'); track.className = 'bar-track';
      const fill = document.createElement('div'); fill.className = 'bar-fill';
      fill.style.width = `${100 * Number(resultado.PROGRAMADAS) / mayor}%`;
      track.append(fill); row.append(track);
      texto(row, 'strong', formato(resultado.PROGRAMADAS));
      $('barras').append(row);
    }
    for (const [nombre, resultado] of [['FCFS', fcfs], ['Greedy', greedy]]) {
      const fila = document.createElement('tr');
      for (const valor of [nombre, formato(resultado.PROGRAMADAS), formato(resultado.PENDIENTES),
        formato(resultado.TIEMPO_PROMEDIO_S, 3), formato(resultado.RAM_PICO_MB, 2),
        `${formato(resultado.OCUPABILIDAD_CON_LIMPIEZA_PCT, 2)}%`, formato(resultado.SOLAPAMIENTOS)]) celda(fila, valor);
      $('detalle-fcfs').append(fila);
    }
  }
  function medicionesDe(algoritmo) {
    if (algoritmo === 'GREEDY') {
      return (estado.fcfs_greedy || [])
        .filter((r) => r.METODO === 'OPTIMIZADO_GREEDY_V1')
        .map((r) => ({
          n: Number(r.N_SOLICITUDES), tipo: 'solicitudes quirúrgicas',
          tiempo: Number(r.TIEMPO_PROMEDIO_S), memoria: Number(r.RAM_PICO_MB),
          ramProceso: null, repeticiones: r.REPETICIONES, origen: 'comparacion'
        })).sort((a, b) => a.n - b.n);
    }
    return (estado.individuales || []).filter((r) => r.ALGORITMO === algoritmo)
      .map((r) => ({
        n: Number(r.N_ENTRADA), tipo: r.TIPO_ENTRADA,
        tiempo: Number(r.TIEMPO_PROMEDIO_MS), memoria: Number(r.MEMORIA_PYTHON_PICO_KB),
        ramProceso: r.RAM_PROCESO_OBSERVADA_MB === '' || r.RAM_PROCESO_OBSERVADA_MB == null ? null : Number(r.RAM_PROCESO_OBSERVADA_MB),
        repeticiones: r.REPETICIONES, origen: 'individual'
      })).sort((a, b) => a.n - b.n);
  }
  function miniBarras(id, mediciones, llave, seleccionado, decimales) {
    const contenedor = $(id);
    contenedor.replaceChildren();
    const mayor = Math.max(0.000001, ...mediciones.map((m) => m[llave]));
    for (const m of mediciones) {
      const fila = document.createElement('div');
      fila.className = `mini-bar-row ${m.n === seleccionado ? 'selected' : ''}`;
      texto(fila, 'span', formato(m.n), 'bar-label');
      const track = document.createElement('div'); track.className = 'bar-track';
      const barra = document.createElement('div'); barra.className = 'bar-fill';
      barra.style.width = `${Math.max(1, 100 * m[llave] / mayor)}%`;
      track.append(barra); fila.append(track);
      texto(fila, 'span', formato(m[llave], decimales), 'valor');
      contenedor.append(fila);
    }
  }
  function renderDetalleAlgoritmo() {
    const id = $('detalle-algoritmo').value;
    const algoritmo = (estado.algoritmos || []).find((a) => a.id === id);
    const mediciones = medicionesDe(id);
    const tamano = $('detalle-n');
    const anterior = tamano.value;
    tamano.replaceChildren();
    mediciones.forEach((m) => tamano.add(new Option(`${formato(m.n)} ${id === 'BELLMAN_FORD' || id === 'PRIM' ? 'nodos' : 'entradas'}`, String(m.n))));
    tamano.disabled = mediciones.length === 0;
    tamano.value = mediciones.some((m) => String(m.n) === anterior) ? anterior : String(mediciones.at(-1)?.n ?? '');
    dibujarDetalle(algoritmo, mediciones);
  }
  function dibujarDetalle(algoritmo, mediciones) {
    const resumen = $('resumen-algoritmo'); resumen.replaceChildren();
    const descripcion = document.createElement('div');
    texto(descripcion, 'strong', 'Uso en QuiroRed');
    texto(descripcion, 'p', algoritmo?.uso || 'Sin descripción');
    const complejidad = document.createElement('div');
    texto(complejidad, 'strong', 'Complejidad teórica');
    texto(complejidad, 'p', algoritmo?.complejidad || 'Por definir');
    resumen.append(descripcion, complejidad);
    const tarjetas = $('metricas-algoritmo'); tarjetas.replaceChildren();
    const tabla = $('detalle-algoritmos'); tabla.replaceChildren();
    const unidades = algoritmo?.id === 'GREEDY'
      ? {tiempo: 's', memoria: 'MB', decTiempo: 3, decMemoria: 2}
      : {tiempo: 'ms', memoria: 'KiB', decTiempo: 3, decMemoria: 2};
    $('tiempo-unidad').textContent = `Tiempo medio de ejecución (${unidades.tiempo})`;
    $('memoria-unidad').textContent = `Pico de memoria Python (${unidades.memoria})`;
    $('col-tiempo').textContent = `Tiempo medio (${unidades.tiempo})`;
    $('col-memoria').textContent = `Memoria Python pico (${unidades.memoria})`;
    if (!mediciones.length) {
      tarjetas.append(metrica('Mediciones', 'Pendiente', 'No hay resultados para este algoritmo'));
      $('barras-tiempo').replaceChildren(); $('barras-memoria').replaceChildren();
      const fila = document.createElement('tr'); const td = celda(fila, 'Aún no hay mediciones disponibles.'); td.colSpan = 6; tabla.append(fila);
      return;
    }
    const elegido = mediciones.find((m) => String(m.n) === $('detalle-n').value) || mediciones.at(-1);
    tarjetas.append(
      metrica('Tiempo medio', `${formato(elegido.tiempo, unidades.decTiempo)} ${unidades.tiempo}`, `${formato(elegido.n)} entradas`),
      metrica('Memoria Python pico', `${formato(elegido.memoria, unidades.decMemoria)} ${unidades.memoria}`, 'Medición de Python'),
      metrica('RAM del proceso', elegido.ramProceso === null ? '—' : `${formato(elegido.ramProceso, 2)} MB`, elegido.ramProceso === null ? 'No medida en esta prueba' : 'RAM observada'),
      metrica('Repeticiones', formato(elegido.repeticiones), 'Por tamaño de entrada')
    );
    miniBarras('barras-tiempo', mediciones, 'tiempo', elegido.n, unidades.decTiempo);
    miniBarras('barras-memoria', mediciones, 'memoria', elegido.n, unidades.decMemoria);
    for (const m of mediciones) {
      const fila = document.createElement('tr');
      if (m.n === elegido.n) fila.className = 'seleccionado';
      for (const valor of [formato(m.n), m.tipo, formato(m.tiempo, unidades.decTiempo),
        formato(m.memoria, unidades.decMemoria), m.ramProceso == null ? '—' : formato(m.ramProceso, 2),
        formato(m.repeticiones)]) celda(fila, valor);
      tabla.append(fila);
    }
  }
  function renderAlgoritmos() {
    $('tabla-algoritmos').replaceChildren();
    const selector = $('detalle-algoritmo');
    const anterior = selector.value;
    selector.replaceChildren();
    for (const a of estado.algoritmos || []) {
      selector.add(new Option(a.nombre, a.id));
      const fila = document.createElement('tr');
      celda(fila, a.nombre); celda(fila, a.uso); celda(fila, a.complejidad);
      const muestras = medicionesDe(a.id);
      celda(fila, muestras.length ? `${formato(muestras.at(-1).n)} entradas · ${formato(muestras.at(-1).tiempo, 3)} ${a.id === 'GREEDY' ? 's' : 'ms'}` : 'Pendiente de medición');
      $('tabla-algoritmos').append(fila);
    }
    selector.value = (estado.algoritmos || []).some((a) => a.id === anterior) ? anterior : 'BFS';
    renderDetalleAlgoritmo();
  }
  document.querySelectorAll('[data-panel]').forEach((tab) => tab.addEventListener('click', () => {
    document.querySelectorAll('[data-panel]').forEach((otro) => {
      const activo = tab === otro;
      otro.classList.toggle('active', activo);
      otro.setAttribute('aria-selected', String(activo));
      $(otro.dataset.panel).hidden = !activo;
    });
  }));
  $('tecnica-n').addEventListener('change', renderComparacion);
  $('detalle-algoritmo').addEventListener('change', renderDetalleAlgoritmo);
  $('detalle-n').addEventListener('change', () => {
    const id = $('detalle-algoritmo').value;
    dibujarDetalle((estado.algoritmos || []).find((a) => a.id === id), medicionesDe(id));
  });
  fetch('/api/tecnica/resultados', {credentials: 'same-origin', cache: 'no-store'})
    .then((r) => { if (!r.ok) throw new Error('No se pudieron consultar las métricas técnicas.'); return r.json(); })
    .then((data) => { estado = data; renderComparacion(); renderAlgoritmos(); })
    .catch((error) => { $('error-datos').textContent = error.message; $('error-datos').hidden = false; });
})();
