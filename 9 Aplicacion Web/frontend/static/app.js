'use strict';
const $ = id => document.getElementById(id);
const safe = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nombres = {cronograma:['Cronograma quirúrgico','Consulta las cirugías de las tres clínicas.'],programar:['Programar cirugía','']};
let primerDia=null, ultimoDia=null, candidatoDatos=[], opcionesIncidencia=[], procesando=false, consultaEnCurso=false;
let ultimoToast=0, sedesVisibles={}, recursosVisibles={};
function sede(id){return sedesVisibles[id]?.nombre||id||''}
function recurso(id){return id?(recursosVisibles[id]||String(id)):''}
function solicitud(id){
 const valor=String(id||'');
 const partes=/^RED_(CES|ONC)_(\d+)$/.exec(valor);
 if(!partes)return valor?`Solicitud ${valor}`:'Solicitud sin identificar';
 return `${partes[1]==='CES'?'Cesárea':'Cirugía oncológica'} · Solicitud N.º ${partes[2]}`;
}
function solicitudBreve(id){
 const partes=/^RED_(CES|ONC)_(\d+)$/.exec(String(id||''));
 return partes?`${partes[1]==='CES'?'Cesárea':'Oncológica'} ${partes[2]}`:solicitud(id);
}
function nodoVisible(id){return sede(id)}
function descripcionIncidencia(x){if(x.caso_id)return solicitud(x.caso_id);return String(x.descripcion||'').startsWith('Hospital H')?sede(x.hospital):recurso(x.descripcion)}
async function cargarEtiquetas(){
 const [catalogo,recursos]=await Promise.all([api('/api/sedes'),api('/static/recursos_visibles.json')]);
 sedesVisibles=Object.fromEntries((catalogo.sedes||[]).map(x=>[x.id,x]));
 recursosVisibles=recursos;
 for(const select of document.querySelectorAll('select'))for(const opt of select.options){
   const codigo=opt.value;if(sedesVisibles[codigo]){opt.value=codigo;opt.textContent=sede(codigo)}
 }
}

// Confirmación integrada: evita la ventana nativa «127.0.0.1:5000 dice».
function confirmarAccion(mensaje, titulo='Confirmar acción') {
 return new Promise(resolve => {
  let cuadro=$('quirored-dialogo-confirmacion');
  if(!cuadro){
   cuadro=document.createElement('dialog');
   cuadro.id='quirored-dialogo-confirmacion';
   cuadro.className='quirored-dialogo';
   cuadro.setAttribute('aria-labelledby','quirored-dialogo-titulo');
   cuadro.innerHTML=`<form method="dialog" class="quirored-dialogo-form">
     <h2 id="quirored-dialogo-titulo">Confirmar acción</h2>
     <p id="quirored-dialogo-texto"></p>
     <div class="quirored-dialogo-botones">
      <button class="button secondary" type="submit" value="cancelar" autofocus>Cancelar</button>
      <button class="button primary" type="submit" value="aceptar">Confirmar</button>
     </div></form>`;
   document.body.append(cuadro);
  }
  if(cuadro.open){resolve(false);return;}
  if(typeof cuadro.showModal!=='function'){resolve(window.confirm(mensaje));return;}
  cuadro.querySelector('#quirored-dialogo-titulo').textContent=titulo;
  cuadro.querySelector('#quirored-dialogo-texto').textContent=mensaje;
  cuadro.returnValue='cancelar';
  cuadro.addEventListener('close',()=>resolve(cuadro.returnValue==='aceptar'),{once:true});
  cuadro.showModal();
 });
}

function toast(msj){const t=$('toast');t.textContent=msj;t.classList.remove('hidden');const turno=++ultimoToast;setTimeout(()=>{if(turno===ultimoToast)t.classList.add('hidden')},3100)}
function reloj(){ $('last-update').textContent=new Intl.DateTimeFormat('es-PE',{dateStyle:'short',timeStyle:'medium'}).format(new Date()); }
function vista(nombre){document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===nombre));document.querySelectorAll('.nav-link').forEach(b=>b.classList.toggle('active',b.dataset.view===nombre));$('page-title').textContent=nombres[nombre][0];$('page-subtitle').textContent=nombres[nombre][1];$('page-subtitle').hidden=!nombres[nombre][1];window.scrollTo({top:0,behavior:'smooth'});if(nombre==='programar')cargarPendientes().catch(notificarError)}
function mensajeAmable(error) {
 const texto=String(error?.message??error??'').trim();
 const estados={SIN_CUPO:'No se encontraron horarios disponibles.',SIN_CANDIDATOS:'No hay cirugías pendientes para esta fecha.',SIN_RUTA:'No hay una ruta disponible para ese traslado.'};
 if(estados[texto])return estados[texto];
 if(!texto)return 'No se pudo completar la operación. Inténtalo nuevamente.';
 if(/postgres|psycopg|sql|traceback|internal server|http\s*\d+|json|\/api\/|database|sin_cupo|sin_candidatos|error de servidor/i.test(texto))return 'No se pudo completar la operación. Revisa la conexión e inténtalo de nuevo.';
 return texto.length>180?'No se pudo completar la operación. Inténtalo nuevamente.':texto;
}
function notificarError(e){console.error('QuiroRed:',e);toast(mensajeAmable(e))}
async function api(url,opts={}){const r=await fetch(url,{cache:'no-store',...opts});let d;try{d=await r.json()}catch(_){throw Error('No se pudo leer la información. Inténtalo nuevamente.')}if(!r.ok)throw Error(d.error||'No se pudo completar la solicitud.');return d}
function post(url,d={}){return api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})}
function pasoTexto(e){const nombres={ausencia_cirujano:'Ausencia de cirujano',falla_equipo:'Falla de equipo',limpieza_prolongada:'Limpieza prolongada',postoperatorio_saturado:'Recuperación sin disponibilidad',bloqueo_ruta:'Ruta bloqueada',derivacion_confirmada:'Traslado confirmado',derivacion_confirmada_modelo:'Traslado confirmado',resolucion_incidencia:'Incidencia resuelta',incidencia_resuelta:'Incidencia resuelta',planificacion_jornada:'Jornada organizada'};const tipo=String(e.tipo||'evento');const a=nombres[tipo]||tipo.replaceAll('_',' ');return a.charAt(0).toUpperCase()+a.slice(1)}
function estadoVisible(valor){const clave=String(valor||'REGISTRADO').toUpperCase();const estados={APLICADO:'Registrado',REGISTRADO:'Registrado',RESUELTO:'Resuelta',CONFIRMADO:'Confirmado',PROGRAMADA:'Programada',SIN_CUPO:'Sin disponibilidad',SIN_CANDIDATOS:'Sin cirugías elegibles',SIN_CAMBIOS:'Sin cambios',RECHAZADO:'No realizado'};return estados[clave]||String(valor||'Registrado').replaceAll('_',' ').toLowerCase()}
async function refrescarEstado(){const r=await api('/api/estado');$('estado-servidor').textContent=r.inicializada?'Sistema disponible':'Información no disponible';$('sin-inicializar').classList.toggle('hidden',!!r.inicializada);if(!r.inicializada)return false;
 for(const [k,id] of [['casos','m-casos'],['programadas','m-programadas'],['pendientes','m-pendientes'],['propuestas','m-propuestas']])$(id).textContent=(r[k]??0).toLocaleString('es-PE');
 $('contador-eventos').textContent='Movimientos registrados: '+(r.eventos??0);reloj();return true;}
async function cargarFechas(){const d=await api('/api/fechas');primerDia=d.primera;ultimoDia=d.ultima;if(!$('f-fecha').value&&primerDia)$('f-fecha').value=primerDia;if(!$('j-fecha').value&&primerDia)$('j-fecha').value=primerDia;}
const MIN_H=7*60,MAX_H=21*60;
function minutos(t){const [h,m]=String(t||'00:00').split(':').map(Number);return h*60+m}
function colocar(parent,tag,clase,contenido){const e=document.createElement(tag);if(clase)e.className=clase;if(contenido!==undefined)e.textContent=contenido;parent.append(e);return e}
function tabular(filas,total){$('cantidad-dia').textContent=`${filas.length} de ${total} en la jornada seleccionada`;
 $('tabla-cronograma').innerHTML=filas.length?filas.map(r=>`<tr><td class="case-id">${safe(solicitud(r.CASO_ID))}</td><td>${safe(r.TIPO_PROCEDIMIENTO==='CESAREA'?'Cesárea':'Oncológica')}</td><td>${safe(sede(r.HOSPITAL))}</td><td>${safe(r.INICIO)}–${safe(r.FIN_CIRUGIA)}</td><td>${safe(recurso(r.SALA_ID))}</td><td>${safe(recurso(r.CIRUJANO_ID))}</td><td>${safe(r.PRIORIDAD)}</td></tr>`).join(''):'<tr><td colspan="7">No hay cirugías en esta jornada o hospital.</td></tr>';
}
function pintarCronograma(filas){const raiz=$('timeline-rooms');raiz.replaceChildren();if(!filas.length){colocar(raiz,'p','timeline-empty','No hay cirugías programadas para los filtros elegidos.');return}
 const salas=new Map();for(const r of filas){const k=r.HOSPITAL+'|'+r.SALA_ID;if(!salas.has(k))salas.set(k,[]);salas.get(k).push(r)}
 for(const [clave,registros] of [...salas].sort((a,b)=>a[0].localeCompare(b[0]))){const [h,sala]=clave.split('|');const fila=colocar(raiz,'div','timeline-room');const etiqueta=colocar(fila,'div','timeline-room-label');colocar(etiqueta,'strong',null,recurso(sala));colocar(etiqueta,'small',null,sede(h));const pista=colocar(fila,'div','timeline-track');
  for(const r of registros){let a=Math.max(MIN_H,minutos(r.INICIO)),b=Math.min(MAX_H,minutos(r.FIN_CIRUGIA)),c=Math.min(MAX_H,minutos(r.FIN_LIMPIEZA));if(b>a){const t=colocar(pista,'div','timeline-slot '+(r.TIPO_PROCEDIMIENTO==='CESAREA'?'ces':'onco'));const l=((a-MIN_H)/(MAX_H-MIN_H))*100,w=((b-a)/(MAX_H-MIN_H))*100;t.style.left=l+'%';t.style.width=w+'%';t.title=`${solicitud(r.CASO_ID)} · ${r.INICIO}–${r.FIN_CIRUGIA} · ${recurso(r.CIRUJANO_ID)}`;colocar(t,'strong',null,solicitudBreve(r.CASO_ID));colocar(t,'small',null,r.INICIO+'–'+r.FIN_CIRUGIA)}if(c>b){const z=colocar(pista,'div','timeline-slot clean');z.style.left=((b-MIN_H)/(MAX_H-MIN_H))*100+'%';z.style.width=((c-b)/(MAX_H-MIN_H))*100+'%';z.title='Limpieza hasta '+r.FIN_LIMPIEZA;}}
 }
}
async function cargarCronograma(){const dia=$('f-fecha').value;if(!dia)return;const params=new URLSearchParams({hospital:$('f-hospital').value,fecha:dia,limite:'200'});const d=await api('/api/programaciones?'+params);pintarCronograma(d.filas);tabular(d.filas,d.total);}
async function cargarEventos(){const d=await api('/api/eventos');$('lista-eventos').innerHTML=d.length?d.slice(0,9).map(x=>{const deriv=x.derivaciones_confirmadas_modelo||[];const detalle=deriv.length?deriv.slice(0,3).map(v=>`${solicitud(v.caso_id)}: ${sede(v.origen)} → ${sede(v.destino)} (${(v.ruta||[]).map(nodoVisible).join(' → ')})`).join(' · '):'';return `<div class="event-row"><div><strong>${safe(pasoTexto(x))}</strong><small>${safe(x.instante_registro||x.instante_simulado||'Sin hora registrada')} · ${safe(x.afectadas??0)} afectada(s)</small>${detalle?`<small>${safe(detalle)}</small>`:''}</div><span class="event-state">${safe(estadoVisible(x.estado))}</span></div>`}).join(''):'<p class="micro-note">No se han registrado eventos.</p>'}
async function cargarPropuestas(){const d=await api('/api/propuestas');$('tabla-propuestas').innerHTML=d.length?d.slice(0,50).map(x=>`<tr><td>${safe(solicitud(x.CASO_ID))}</td><td>${safe(sede(x.HOSPITAL_DESTINO))}</td><td>${safe(x.TIEMPO_TRASLADO_MIN_SIM)} min</td><td>Por confirmar</td><td><button class="button secondary" type="button" data-confirmar-caso="${safe(x.CASO_ID)}">Confirmar</button></td></tr>`).join(''):'<tr><td colspan="5">No hay traslados pendientes. Pulsa «Buscar alternativas».</td></tr>'}
async function cargarIncidenciasActivas(){const d=await api('/api/incidencias/activas');$('lista-incidencias-activas').innerHTML=d.length?d.map(x=>`<div class="event-row"><div><strong>${safe(pasoTexto(x))} n.º ${safe(x.paso)}</strong><small>${safe(x.fecha||'Red vial')} · ${safe(sede(x.hospital)||'Red')} · ${safe(x.recursos_bloqueados.length)} recurso(s), ${safe(x.rutas_bloqueadas.length)} conexión(es)</small></div><button class="button secondary" type="button" data-resolver-paso="${safe(x.paso)}">Resolver</button></div>`).join(''):'<p class="micro-note">No hay bloqueos activos.</p>'}
async function proponerDerivaciones(){if(procesando)return;if(!(await confirmarAccion('¿Deseas buscar otras clínicas disponibles para las cirugías pendientes?', 'Buscar alternativas')))return;const b=$('btn-generar-derivaciones');procesando=true;b.disabled=true;$('mensaje-derivaciones').textContent='Buscando alternativas disponibles…';try{const d=await post('/api/derivaciones/proponer');$('mensaje-derivaciones').textContent=`Se encontraron ${d.propuestas??0} alternativas de traslado.`;await refrescarTodo();toast('Búsqueda finalizada.')}catch(e){$('mensaje-derivaciones').textContent=mensajeAmable(e);notificarError(e)}finally{procesando=false;b.disabled=false}}
async function confirmarPropuesta(caso){if(procesando)return;if(!(await confirmarAccion(`¿Deseas confirmar el traslado de ${solicitud(caso)} a otra clínica? El sistema comprobará la disponibilidad antes de asignarlo.`, 'Confirmar traslado')))return;procesando=true;$('mensaje-derivaciones').textContent='Comprobando disponibilidad…';try{const d=await post('/api/derivaciones/confirmar',{caso_id:caso});$('mensaje-derivaciones').textContent=` ${solicitud(d.programacion.CASO_ID)} programada en ${sede(d.programacion.HOSPITAL)} el ${d.programacion.FECHA} a las ${d.programacion.INICIO}.`;$('f-fecha').value=d.programacion.FECHA;$('f-hospital').value=d.programacion.HOSPITAL;toast('Cirugía asignada en otra clínica.');await refrescarTodo();await cargarPendientes()}catch(e){$('mensaje-derivaciones').textContent=mensajeAmable(e);notificarError(e)}finally{procesando=false}}
async function resolverBloqueo(paso){if(procesando)return;if(!(await confirmarAccion(`¿Marcar la incidencia n.º ${paso} como resuelta? Los recursos podrán utilizarse en nuevas programaciones.`, 'Resolver incidencia')))return;procesando=true;msgEvento('Resolviendo incidencia…');try{const d=await post('/api/incidencias/resolver',{paso:Number(paso)});msgEvento(`Incidencia n.º ${paso} resuelta. Los recursos afectados vuelven a estar disponibles.`);toast('Incidencia resuelta y registrada en el historial.');await refrescarTodo();await cargarOpcionesIncidencia()}catch(e){msgEvento(mensajeAmable(e),true);notificarError(e)}finally{procesando=false}}

// Red real: calles dirigidas de San Isidro con OpenStreetMap y tiempos estimados.
let mapaVial = null, capaCalles = null, capaSedes = null, capaRuta = null, capaTramoSeleccionado = null;
let nodosViales = new Map(), conexionesViales = new Map(), tramoElegido = '', solicitudOpciones = 0;
function puntoMapa(id){const n=nodosViales.get(id);return n&&Number.isFinite(Number(n.lat))&&Number.isFinite(Number(n.lon))?[Number(n.lat),Number(n.lon)]:null;}
function mostrarRutaEnMapa(camino){
 if(!mapaVial||!capaRuta)return;
 capaRuta.clearLayers();
 const puntos=(camino||[]).map(puntoMapa).filter(Boolean);
 if(puntos.length<2)return;
 L.polyline(puntos,{color:'#1266b1',weight:6,opacity:.95}).addTo(capaRuta);
 mapaVial.fitBounds(L.latLngBounds(puntos).pad(.25),{maxZoom:16});
}
function destacarTramoVial(){
 if(!capaTramoSeleccionado)return;
 capaTramoSeleccionado.clearLayers();
 if($('tipo-evento').value!=='bloqueo_ruta'||!tramoElegido)return;
 const tramo=conexionesViales.get(tramoElegido);
 if(!tramo||tramo.bloqueada)return;
 const inicio=puntoMapa(tramo.desde),fin=puntoMapa(tramo.hasta);
 if(!inicio||!fin)return;
 L.polyline([inicio,fin],{color:'#f0a327',weight:8,opacity:.97})
   .bindTooltip(safe(tramo.via||'Tramo seleccionado')+' · Tramo seleccionado')
   .addTo(capaTramoSeleccionado);
}
async function cargarRed(){
 const d=await api('/api/red');
 conexionesViales=new Map((d.conexiones||[]).map(x=>[x.id,x]));
 const elemento=$('grafo');
 if(!window.L){elemento.textContent='El mapa no se pudo cargar. Puedes seguir calculando rutas desde los controles.';return;}
 if(!d.red_real){elemento.textContent='La red vial aún no está activada.';return;}
 nodosViales=new Map((d.nodos||[]).map(x=>[x.id,x]));
 if(!mapaVial){
   // Mantiene el mapa en San Isidro: sin desplazamiento con mouse, dedo ni teclado.
   // El usuario puede acercar/alejar con los botones +/- y la ruta puede encuadrarse.
   mapaVial=L.map(elemento,{scrollWheelZoom:false,zoomControl:true,dragging:false,
     touchZoom:false,doubleClickZoom:false,boxZoom:false,keyboard:false});
   L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
     maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>'
   }).addTo(mapaVial);
   capaCalles=L.layerGroup().addTo(mapaVial);
   capaSedes=L.layerGroup().addTo(mapaVial);
   capaRuta=L.layerGroup().addTo(mapaVial);
   capaTramoSeleccionado=L.layerGroup().addTo(mapaVial);
 }
 capaCalles.clearLayers();capaSedes.clearLayers();
 for(const a of d.conexiones){
   const p=puntoMapa(a.desde),q=puntoMapa(a.hasta);if(!p||!q)continue;
   const pol=L.polyline([p,q],{color:a.bloqueada?'#d34252':'#4c8096',weight:a.bloqueada?5:3,opacity:a.bloqueada?.9:.65,dashArray:a.bloqueada?'7 5':null});
   pol.bindTooltip(`${safe(a.via||'Calle sin nombre')} · ${safe(a.peso_min)} min${a.bloqueada?' · Bloqueada':''}`);
   pol.addTo(capaCalles);
 }
 const sedes=[];
 for(const n of d.nodos){
   if(n.tipo!=='HOSPITAL')continue;
   const p=puntoMapa(n.id);if(!p)continue;sedes.push(p);
   L.circleMarker(p,{radius:10,color:'#fff',weight:2,fillColor:'#a6192e',fillOpacity:1})
     .bindTooltip(safe(sede(n.id)),{permanent:false}).addTo(capaSedes);
 }
 if(!mapaVial._quiroredEncuadre&&sedes.length){mapaVial.fitBounds(L.latLngBounds(sedes).pad(.3));mapaVial._quiroredEncuadre=true;}
 // Los bloqueos pueden cambiar cada 15 s; la ruta resaltada se recalcula al solicitarla.
 if(capaRuta)capaRuta.clearLayers();
 destacarTramoVial();
 setTimeout(()=>mapaVial&&mapaVial.invalidateSize(),0);
}
async function refrescarTodo(){if(consultaEnCurso)return;consultaEnCurso=true;try{const ok=await refrescarEstado();if(!ok)return;await cargarFechas();await Promise.all([cargarCronograma(),cargarEventos(),cargarPropuestas(),cargarIncidenciasActivas(),cargarRed()]);}catch(e){$('estado-servidor').textContent='Sin conexión';notificarError(e)}finally{consultaEnCurso=false}}
function msgEvento(t,error=false){const el=$('mensaje-evento');el.textContent=t;el.classList.toggle('error',!!error)}
async function cargarOpcionesIncidencia(){
 const tipo=$('tipo-evento').value,pedido=++solicitudOpciones;
 const d=await api('/api/incidencias/opciones?'+new URLSearchParams({tipo}));
 if(pedido!==solicitudOpciones||tipo!==$('tipo-evento').value)return;
 opcionesIncidencia=d.opciones||[];
 actualizarOpcionesIncidencia();
}
function referenciaBreve(nombre,calle){
 const valor=String(nombre||'').trim();
 if(!valor)return 'Intersección sin referencia';
 if(valor.toLocaleLowerCase('es')===calle.toLocaleLowerCase('es'))return 'la misma vía';
 const prefijo=calle+' con ';
 return valor.toLocaleLowerCase('es').startsWith(prefijo.toLocaleLowerCase('es'))
   ?'cruce con '+valor.slice(prefijo.length):valor;
}
function textoTramoVial(x){
 const calle=x.calle||'Calle sin nombre',a=referenciaBreve(x.origen_nombre,calle);
 const b=referenciaBreve(x.destino_nombre,calle);
 const longitud=Number(x.distancia_m)>0?` · ${Math.round(Number(x.distancia_m))} m`:'';
 const seccion=(x.descripcion||'').match(/ · sección (\d+\/\d+)$/);
 return `Desde ${a} hacia ${b}${longitud}${seccion?' · tramo '+seccion[1]:''}`;
}
function renderizarTramosViales(){
 const calle=$('inc-calle').value,busqueda=$('inc-buscar-tramo').value.trim().toLocaleLowerCase('es');
 const panel=$('inc-lista-tramos');panel.replaceChildren();
 const todos=opcionesIncidencia.filter(x=>x.calle===calle);
 const visibles=todos.filter(x=>!busqueda||(`${textoTramoVial(x)} ${x.descripcion}`).toLocaleLowerCase('es').includes(busqueda));
 if(tramoElegido&&!visibles.some(x=>x.recurso_id===tramoElegido)){
   tramoElegido='';$('inc-objetivo').value='';$('paso-evento').disabled=true;destacarTramoVial();
 }
 $('inc-cantidad-tramos').textContent=!calle?'Selecciona una calle para ver sus tramos.':
   `${visibles.length} de ${todos.length} tramos visibles`;
 if(!visibles.length){const p=document.createElement('p');p.className='micro-note road-empty';p.textContent=calle?'No hay tramos que coincidan con la búsqueda.':'Elige una calle para continuar.';panel.append(p);}
 for(const x of visibles){
   const b=document.createElement('button');b.type='button';b.className='road-segment-item';
   b.dataset.tramoId=x.recurso_id;b.setAttribute('aria-pressed',String(x.recurso_id===tramoElegido));
   b.textContent=textoTramoVial(x);b.title=x.descripcion;panel.append(b);
 }
 const seleccionado=opcionesIncidencia.find(x=>x.recurso_id===tramoElegido);
 $('inc-tramo-confirmado').textContent=seleccionado?`Seleccionado: ${seleccionado.calle} · ${textoTramoVial(seleccionado)}. Tramo destacado en naranja en el mapa.`:
   'Elige un tramo para destacarlo en el mapa.';
}
function seleccionarTramoVial(id){
 const i=opcionesIncidencia.findIndex(x=>x.recurso_id===id);
 if(i<0)return;
 tramoElegido=id;$('inc-objetivo').value=String(i);
 $('paso-evento').disabled=false;
 renderizarTramosViales();destacarTramoVial();
}
function actualizarOpcionesIncidencia(){
 const tipo=$('tipo-evento').value,vial=tipo==='bloqueo_ruta';
 $('inc-filtros').classList.toggle('hidden',vial);
 $('inc-objetivo-contenedor').classList.toggle('hidden',vial);
 $('selector-vial').classList.toggle('hidden',!vial);
 const hospital=$('inc-hospital').value,fecha=$('inc-fecha').value,lista=$('inc-objetivo');
 lista.replaceChildren();lista.append(new Option('Selecciona el recurso o la jornada afectada',''));
 if(vial){
   const calleSelect=$('inc-calle'),anterior=calleSelect.value;
   const calles=[...new Set(opcionesIncidencia.map(x=>x.calle||'Calle sin nombre'))]
     .sort((a,b)=>a.localeCompare(b,'es'));
   calleSelect.replaceChildren();calleSelect.append(new Option('Selecciona una calle',''));
   for(const calle of calles)calleSelect.append(new Option(calle,calle));
   if(calles.includes(anterior))calleSelect.value=anterior;
   const i=opcionesIncidencia.findIndex(x=>x.recurso_id===tramoElegido);
   if(i<0||opcionesIncidencia[i].calle!==calleSelect.value)tramoElegido='';
   for(let i=0;i<opcionesIncidencia.length;i++)lista.append(new Option(opcionesIncidencia[i].descripcion,String(i)));
   if(tramoElegido)lista.value=String(opcionesIncidencia.findIndex(x=>x.recurso_id===tramoElegido));
   renderizarTramosViales();destacarTramoVial();
 }else{
   tramoElegido='';destacarTramoVial();
   for(let i=0;i<opcionesIncidencia.length;i++){
     const x=opcionesIncidencia[i];
     if((hospital!=='TODOS'&&x.hospital!==hospital)||(fecha&&x.fecha!==fecha))continue;
     lista.append(new Option(`${sede(x.hospital)} · ${x.fecha} · ${descripcionIncidencia(x)}`,String(i)));
   }
 }
 $('paso-evento').disabled=!lista.value;
}
async function registrarIncidencia(){if(procesando)return;const id=$('inc-objetivo').value;if(id===''){msgEvento('Selecciona la jornada o el recurso afectado.',true);return}const x=opcionesIncidencia[Number(id)];if(!x)return;if(!(await confirmarAccion('¿Registrar esta incidencia y buscar nuevos horarios para las cirugías afectadas?', 'Registrar incidencia')))return;procesando=true;$('paso-evento').disabled=true;msgEvento('Registrando incidencia y revisando horarios…');
 try{const d=await post('/api/incidencias',{tipo:$('tipo-evento').value,...x,origen:$('origen').value,destino:$('destino').value});const e=d.evento;const mensaje=`Incidencia registrada. Cirugías afectadas: ${e.afectadas??0}. Reprogramadas: ${e.reprogramadas??0}. Pendientes: ${e.nuevas_pendientes??0}. Traslados: ${(e.derivaciones_confirmadas_modelo||[]).length}.`;msgEvento(mensaje);toast('Incidencia registrada.');await refrescarTodo();await cargarOpcionesIncidencia()}
 catch(e){msgEvento(mensajeAmable(e),true);notificarError(e)}finally{procesando=false;$('paso-evento').disabled=!$('inc-objetivo').value}}
async function planificarDia(){if(procesando)return;if(!(await confirmarAccion('¿Deseas organizar las cirugías pendientes de esta jornada?', 'Organizar cirugías')))return;const boton=$('btn-jornada');procesando=true;boton.disabled=true;$('resultado-jornada').textContent='Buscando horarios disponibles…';
 try{const d=await post('/api/programaciones/jornada',{hospital:$('j-hospital').value,fecha:$('j-fecha').value,cantidad:Number($('j-cantidad').value)});const detalle=d.detalle||{};const n=detalle.programadas??d.programadas??0;$('resultado-jornada').textContent=n?`${n===1?'Se programó 1 cirugía.':`Se programaron ${n} cirugías.`}${(detalle.derivaciones_confirmadas_modelo||[]).length?` Traslados a otra clínica: ${(detalle.derivaciones_confirmadas_modelo||[]).length}.`:''}`:(d.estado==='SIN_CANDIDATOS'?'No hay cirugías pendientes que cumplan las condiciones para esta fecha.':d.estado==='SIN_CUPO'?'No se encontraron horarios disponibles para esta jornada.':'No fue posible programar nuevas cirugías en esta jornada.');if(n){$('f-fecha').value=$('j-fecha').value;$('f-hospital').value=$('j-hospital').value;toast('La jornada se actualizó correctamente.')}await refrescarTodo();await cargarPendientes();await cargarOpcionesIncidencia()}
 catch(e){$('resultado-jornada').textContent=mensajeAmable(e);notificarError(e)}finally{procesando=false;boton.disabled=false}}
async function cargarPendientes(){const busca=$('buscar-caso').value.trim(),d=await api('/api/pendientes/candidatos?'+new URLSearchParams({buscar:busca,limite:'40'}));candidatoDatos=d.filas;const select=$('caso-pendiente'),antes=select.value;select.replaceChildren();select.append(new Option('Selecciona una solicitud pendiente',''));for(const c of candidatoDatos){const flag=c.listo?'':' (aún no disponible)';select.append(new Option(`${solicitud(c.caso_id)} · ${sede(c.hospital)}${flag}`,c.caso_id));}if(candidatoDatos.some(x=>x.caso_id===antes))select.value=antes;
 $('total-pendientes-opciones').textContent=`${d.total} solicitudes coinciden con la búsqueda. Se muestran hasta 40.`;actualizarCaso();}
function actualizarCaso(){const c=candidatoDatos.find(x=>x.caso_id===$('caso-pendiente').value);$('hospital-caso').value=c?sede(c.hospital):'';$('tipo-caso').value=c?.procedimiento==='CESAREA'?'Cesárea':c?.procedimiento==='ONCO'?'Cirugía oncológica':'';
 if(c){$('fecha-programar').min=c.fecha_minima;const ref=ultimoDia?new Date(ultimoDia+'T12:00:00'):null;if(ref)ref.setDate(ref.getDate()-1);const candidata=ref?ref.toISOString().slice(0,10):c.fecha_minima;$('fecha-programar').value=candidata>=c.fecha_minima?candidata:c.fecha_minima;$('hora-programar').value=c.hora_preferida||'08:00'}else{$('fecha-programar').min='';$('fecha-programar').value=''}$('btn-programar').disabled=!c||!c.listo;}
function ocultarResultado(){$('resultado-vacio').classList.remove('hidden');$('resultado-ok').classList.add('hidden');$('resultado-pendiente').classList.add('hidden');$('proposal-status').className='status neutral';$('proposal-status').textContent='Sin evaluar';}
async function programar(event){event.preventDefault();const caso=$('caso-pendiente').value;if(!caso)return;const boton=$('btn-programar');boton.disabled=true;ocultarResultado();$('resultado-vacio').querySelector('p').textContent='Buscando recursos y horarios compatibles…';try{const d=await post('/api/programaciones/pendiente',{caso_id:caso,fecha:$('fecha-programar').value,hora:$('hora-programar').value});$('resultado-vacio').classList.add('hidden');if(d.estado==='PROGRAMADA'){
 $('proposal-status').className='status ok';$('proposal-status').textContent='Programada';$('resultado-ok').classList.remove('hidden');const r=d.programacion;for(const [id,val] of [['r-caso',solicitud(r.CASO_ID)],['r-fecha',r.FECHA+' · '+r.INICIO],['r-sala',recurso(r.SALA_ID)],['r-hospital',sede(r.HOSPITAL)],['r-cirujano',recurso(r.CIRUJANO_ID)],['r-anest',recurso(r.ANESTESIOLOGO_ID)],['r-equipo',recurso(r.EQUIPO_ESPECIALIZADO_ID)+' / '+recurso(r.INSTRUMENTAL_ID)]])$(id).textContent=val;
 $('r-metodo').textContent='';$('r-derivacion').textContent=r.HOSPITAL_ORIGEN?`Traslado desde ${sede(r.HOSPITAL_ORIGEN)} hacia ${sede(r.HOSPITAL)}. Tiempo estimado: ${r.TIEMPO_TRASLADO_MIN_SIM} minutos.`:'Cirugía asignada en su clínica de origen.';$('f-fecha').value=r.FECHA;$('f-hospital').value=r.HOSPITAL;toast('Cirugía programada correctamente.');await refrescarTodo();await cargarPendientes();
 }else{$('proposal-status').className='status neutral';$('proposal-status').textContent='Sin cupo';$('resultado-pendiente').classList.remove('hidden');$('resultado-pendiente').textContent=mensajeAmable(d.mensaje||'No se encontró un horario disponible para esta cirugía.')}}
 catch(e){$('resultado-vacio').classList.add('hidden');$('resultado-pendiente').classList.remove('hidden');$('resultado-pendiente').textContent=mensajeAmable(e);notificarError(e)}finally{boton.disabled=false;}}
function eventosUI(){document.querySelectorAll('.nav-link').forEach(b=>b.addEventListener('click',()=>vista(b.dataset.view)));document.querySelectorAll('[data-go]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();vista(a.dataset.go)}));
 $('f-hospital').addEventListener('change',()=>cargarCronograma().catch(notificarError));$('f-fecha').addEventListener('change',()=>cargarCronograma().catch(notificarError));$('f-hoy').addEventListener('click',()=>{if(primerDia){$('f-fecha').value=primerDia;cargarCronograma().catch(notificarError)}});
 $('tipo-evento').addEventListener('change',()=>cargarOpcionesIncidencia().catch(notificarError));$('inc-hospital').addEventListener('change',actualizarOpcionesIncidencia);$('inc-fecha').addEventListener('change',actualizarOpcionesIncidencia);
 $('inc-calle').addEventListener('change',()=>{tramoElegido='';$('inc-objetivo').value='';$('inc-buscar-tramo').value='';$('paso-evento').disabled=true;renderizarTramosViales();destacarTramoVial();});
 $('inc-buscar-tramo').addEventListener('input',renderizarTramosViales);
 $('inc-lista-tramos').addEventListener('click',e=>{const b=e.target.closest('button[data-tramo-id]');if(b)seleccionarTramoVial(b.dataset.tramoId)});
 $('inc-objetivo').addEventListener('change',()=>{$('paso-evento').disabled=!$('inc-objetivo').value});
 $('paso-evento').addEventListener('click',registrarIncidencia);$('btn-jornada').addEventListener('click',planificarDia);
 $('btn-generar-derivaciones').addEventListener('click',proponerDerivaciones);
 $('tabla-propuestas').addEventListener('click',e=>{const b=e.target.closest('button[data-confirmar-caso]');if(b)confirmarPropuesta(b.dataset.confirmarCaso)});
 $('lista-incidencias-activas').addEventListener('click',e=>{const b=e.target.closest('button[data-resolver-paso]');if(b)resolverBloqueo(b.dataset.resolverPaso)});
 $('calcular-ruta').addEventListener('click',async()=>{if($('origen').value===$('destino').value){$('resultado-ruta').textContent='Selecciona dos clínicas diferentes.';return}try{const r=await api('/api/ruta?'+new URLSearchParams({origen:$('origen').value,destino:$('destino').value}));$('resultado-ruta').textContent=r.sin_ruta?'No hay una ruta disponible entre esas clínicas.':`Tiempo estimado: ${r.tiempo_min_sim} minutos · Distancia: ${r.distancia_total_m??'—'} m. ${(r.calles||[]).slice(0,7).join(' → ')}${(r.calles||[]).length>7?'…':''}`;mostrarRutaEnMapa(r.sin_ruta?[]:r.camino)}catch(e){$('resultado-ruta').textContent=mensajeAmable(e)}});
 $('buscar-btn').addEventListener('click',()=>cargarPendientes().catch(notificarError));$('buscar-caso').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();cargarPendientes().catch(notificarError)}});$('caso-pendiente').addEventListener('change',()=>{actualizarCaso();ocultarResultado()});$('recargar-casos').addEventListener('click',()=>cargarPendientes().catch(notificarError));$('form-programacion').addEventListener('submit',programar);$('ir-cronograma').addEventListener('click',()=>vista('cronograma'));
}
eventosUI();ocultarResultado();
(async()=>{try{await cargarEtiquetas()}catch(e){notificarError(e)}await refrescarTodo();await cargarOpcionesIncidencia().catch(notificarError)})();
setInterval(()=>{if(!document.hidden&&!procesando)refrescarTodo()},15000);
