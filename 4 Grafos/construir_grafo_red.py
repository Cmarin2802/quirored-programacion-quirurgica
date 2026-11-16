"""Modelo de compatibilidad de la red quirúrgica H1/H2/H3.
Se ejecuta en Python 3 con networkx y matplotlib.
Los arcos de compatibilidad no son reservas y NO garantizan disponibilidad temporal.
"""
from pathlib import Path
from collections import Counter, defaultdict
import csv, json, math
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch

BASE=Path(__file__).resolve().parent.parent
DATA=BASE/'01_Datos'
OUT=BASE/'02_Grafo'
OUT.mkdir(parents=True,exist_ok=True)

def leer(nombre):
    with (DATA/nombre).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f,delimiter=';'))
def csv_out(name,rows,keys):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        wr=csv.DictWriter(f,delimiter=';',fieldnames=keys);wr.writeheader();wr.writerows(rows)

casos=leer('cirugias_red.csv')
hospitales=leer('hospitales_red.csv')
personal=leer('personal_red.csv')
salas=leer('salas_red.csv')
equipos=leer('equipos_instrumental_red.csv')
postop=leer('postoperatorio_red.csv')
puntos=leer('puntos_viales_red.csv')
rutas=leer('conexiones_red.csv')

G=nx.DiGraph()

def nodo(nid,tipo,nombre,hospital='',origen='SIMULADO_RED_2026_20',**extra):
    if nid in G:raise ValueError(f'ID duplicado: {nid}')
    G.add_node(nid,ID_NODO=nid,TIPO_NODO=tipo,NOMBRE_VISIBLE=nombre,HOSPITAL_ID=hospital,ORIGEN=origen,**extra)

def arco(u,v,relacion,tiempo_min=''):
    if u==v:raise ValueError(f'Autoarista prohibida {u}')
    if not G.has_node(u) or not G.has_node(v):raise ValueError(f'Extremo no existente {u} -> {v}')
    if G.has_edge(u,v):
        antiguo=G[u][v]['RELACION']
        if antiguo=='HOSPITAL_SOLICITANTE' and relacion=='HOSPITAL_CANDIDATO':
            G[u][v]['RELACION']='SOLICITANTE_Y_CANDIDATO';return
        if antiguo!=relacion:raise ValueError(f'Colision de arista {u}->{v}: {antiguo} vs {relacion}')
        return
    G.add_edge(u,v,ORIGEN_ID=u,DESTINO_ID=v,RELACION=relacion,TIEMPO_MIN_SIM=tiempo_min)

# 1. Nodos
for h in hospitales:nodo(h['HOSPITAL_ID'],'HOSPITAL',h['NOMBRE_VISIBLE'],h['HOSPITAL_ID'])
for r in puntos:nodo(r['NODO_VIAL_ID'],'PUNTO_VIAL',r['NOMBRE'])
for proc,nombre in [('CESAREA','Cesarea'),('ONCO_ALTA_COMPLEJIDAD','Cirugia oncologica de alta complejidad')]:nodo('PROC_'+proc,'PROCEDIMIENTO',nombre)
for source,nombre in [('GORE_SAN_MARTIN_CNV','GORE San Martin'),('INEN_CIRUGIA_ALTA_COMPLEJIDAD','INEN')]:nodo('FUENTE_'+source,'FUENTE_REAL',nombre,origen='FUENTE_PUBLICA')
for r in personal:nodo(r['ID_PERSONAL'],'PERSONAL',r['NOMBRE_VISIBLE'],r['HOSPITAL_ID'],r['ORIGEN'],ROL=r['ROL'],ESPECIALIDAD=r['ESPECIALIDAD'])
for r in salas:nodo(r['ID_SALA'],'SALA',r['NOMBRE_VISIBLE'],r['HOSPITAL_ID'],r['ORIGEN'],TIPO_SALA=r['TIPO_SALA'])
for r in equipos:nodo(r['ID_RECURSO'],r['CATEGORIA'],r['NOMBRE_VISIBLE'],r['HOSPITAL_ID'],r['ORIGEN'],COMPATIBILIDAD=r['TIPO_COMPATIBILIDAD'])
for r in postop:nodo(r['ID_RECURSO_POSTOP'],'POSTOP',r['NOMBRE_VISIBLE'],r['HOSPITAL_ID'],r['ORIGEN'],TIPO_POSTOP=r['TIPO'])
for c in casos:nodo(c['CASO_ID'],'CIRUGIA',c['CASO_ID'],c['HOSPITAL_SOLICITANTE'],'HISTORICO_DERIVADO_MAS_SIMULADO',PROCEDIMIENTO=c['TIPO_PROCEDIMIENTO'],CASO_ID_TB1=c['CASO_ID_TB1'])

# 2. Pertenencia y red vial
for records,key in [(personal,'ID_PERSONAL'),(salas,'ID_SALA'),(equipos,'ID_RECURSO'),(postop,'ID_RECURSO_POSTOP')]:
 for r in records:arco(r['HOSPITAL_ID'],r[key],'CONTIENE_RECURSO')
for r in rutas:arco(r['ORIGEN_NODO'],r['DESTINO_NODO'],'CONEXION_VIAL',r['TIEMPO_MIN_SIM'])

# 3. Indexacion por hospital
P=defaultdict(list);S=defaultdict(list);E=defaultdict(list);PO=defaultdict(list)
for r in personal:P[r['HOSPITAL_ID']].append(r)
for r in salas:S[r['HOSPITAL_ID']].append(r)
for r in equipos:E[r['HOSPITAL_ID']].append(r)
for r in postop:PO[r['HOSPITAL_ID']].append(r)

# 4. Candidatos espaciales + especialidad; la temporalidad se valida al programar.
for c in casos:
 id=c['CASO_ID'];proc=c['TIPO_PROCEDIMIENTO'];requested=c['POSTOP_REQUERIDO_SIM']
 arco(id,'PROC_'+proc,'REQUIERE_PROCEDIMIENTO')
 arco(id,'FUENTE_'+c['FUENTE_REAL'],'PROVIENE_DE_FUENTE')
 arco(id,c['HOSPITAL_SOLICITANTE'],'HOSPITAL_SOLICITANTE')
 for h in hospitales:
  hid=h['HOSPITAL_ID']; staff=P[hid]; rooms=S[hid]; devices=E[hid]; beds=PO[hid]
  specialist='GINECO_OBSTETRICIA' if proc=='CESAREA' else 'CIRUGIA_ONCOLOGICA'
  roomtypes={'OBSTETRICA','FLEXIBLE'} if proc=='CESAREA' else {'ONCOLOGICA','FLEXIBLE'}
  eqtypes={'NEONATAL','ANESTESIA','CESAREA'} if proc=='CESAREA' else {'ONCOLOGIA','ANESTESIA','ONCO_ALTA_COMPLEJIDAD'}
  surg=[r for r in staff if r['ROL']=='CIRUJANO' and r['ESPECIALIDAD']==specialist]
  anest=[r for r in staff if r['ROL']=='ANESTESIOLOGO']
  instru=[r for r in staff if r['ROL']=='INSTRUMENTISTA']
  circ=[r for r in staff if r['ROL']=='CIRCULANTE']
  limpi=[r for r in staff if r['ROL']=='LIMPIEZA']
  neo=[r for r in staff if r['ROL']=='NEONATOLOGO'] if proc=='CESAREA' else []
  compatible_rooms=[r for r in rooms if r['TIPO_SALA'] in roomtypes and r['ACTIVA']=='True']
  eqs=[r for r in devices if r['TIPO_COMPATIBILIDAD'] in eqtypes and r['ACTIVO']=='True']
  postop_cands=[r for r in beds if r['TIPO']==requested and r['ACTIVO']=='True']
  # Requerimientos minimos: existencia de profesionales de roles basicos, sala,
  # equipo de anestesia, juego instrumental especifico, y cupo de destino.
  required_eq='CESAREA' if proc=='CESAREA' else 'ONCO_ALTA_COMPLEJIDAD'
  has_needed=(surg and anest and instru and circ and limpi and compatible_rooms and postop_cands
              and any(e['TIPO_COMPATIBILIDAD']=='ANESTESIA' for e in eqs)
              and any(e['TIPO_COMPATIBILIDAD']==required_eq for e in eqs))
  if not has_needed:continue
  arco(id,hid,'HOSPITAL_CANDIDATO')
  role_groups=[(surg,'CANDIDATO_CIRUJANO'),(anest,'CANDIDATO_ANESTESIOLOGO'),(instru,'CANDIDATO_INSTRUMENTISTA'),(circ,'CANDIDATO_CIRCULANTE'),(limpi,'CANDIDATO_LIMPIEZA'),(neo,'CANDIDATO_NEONATOLOGO')]
  for records,rel in role_groups:
   for r in records:arco(id,r['ID_PERSONAL'],rel)
  for r in compatible_rooms:arco(id,r['ID_SALA'],'CANDIDATO_SALA')
  for r in eqs:arco(id,r['ID_RECURSO'],'CANDIDATO_EQUIPO' if r['CATEGORIA']=='EQUIPO' else 'CANDIDATO_INSTRUMENTAL')
  for r in postop_cands:arco(id,r['ID_RECURSO_POSTOP'],'CANDIDATO_POSTOP')

# 5. Archivos canonicos
node_columns=['ID_NODO','TIPO_NODO','NOMBRE_VISIBLE','HOSPITAL_ID','ORIGEN','ROL','ESPECIALIDAD','TIPO_SALA','COMPATIBILIDAD','TIPO_POSTOP','PROCEDIMIENTO','CASO_ID_TB1']
edge_columns=['ORIGEN_ID','DESTINO_ID','RELACION','TIEMPO_MIN_SIM']
node_rows=[{key:d.get(key,'') for key in node_columns} for nid,d in G.nodes(data=True)]
edge_rows=[{key:d.get(key,'') for key in edge_columns} for u,v,d in G.edges(data=True)]
csv_out('grafo_nodos_red.csv',node_rows,node_columns)
csv_out('grafo_aristas_red.csv',edge_rows,edge_columns)

# 6. Validaciones globales y por solicitud
assert len(casos)==1500
assert len(G.nodes)==len(node_rows)
assert len(G.edges)==len(edge_rows)
assert len([n for n,a in G.nodes(data=True) if a['TIPO_NODO']=='CIRUGIA'])==1500
assert nx.number_weakly_connected_components(G)==1, 'La red no queda débilmente conectada'
for c in casos:
 out=[(v,d['RELACION']) for _,v,d in G.out_edges(c['CASO_ID'],data=True)]
 assert any(rel in ('HOSPITAL_CANDIDATO','SOLICITANTE_Y_CANDIDATO') for v,rel in out),f"Sin hospital candidato: {c['CASO_ID']}"
 assert sum(rel in ('HOSPITAL_SOLICITANTE','SOLICITANTE_Y_CANDIDATO') for v,rel in out)==1
# Ninguna arista a recursos de un hospital incompatible con el caso: candidato hospital requerido.
for c in casos[:]:
 candidates={v for _,v,d in G.out_edges(c['CASO_ID'],data=True) if d['RELACION'] in ('HOSPITAL_CANDIDATO','SOLICITANTE_Y_CANDIDATO')}
 for _,v,d in G.out_edges(c['CASO_ID'],data=True):
  if d['RELACION'].startswith('CANDIDATO_') and d['RELACION']!='HOSPITAL_CANDIDATO':
   assert G.nodes[v]['HOSPITAL_ID'] in candidates

counts=Counter(d['TIPO_NODO'] for _,d in G.nodes(data=True))
relcounts=Counter(d['RELACION'] for _,_,d in G.edges(data=True))
summary={'version':'HITO2_MODELO_RED_V1','nodos':len(G),'aristas':G.number_of_edges(),'componentes_debiles':nx.number_weakly_connected_components(G),'componente_vial':len([n for n,d in G.nodes(data=True) if d['TIPO_NODO'] in ['HOSPITAL','PUNTO_VIAL']]),'por_tipo':dict(counts),'por_relacion':dict(relcounts),'algunas_aristas':edge_rows[:4],'nota':'Las aristas CANDIDATO_ indican compatibilidad estructural, NO disponibilidad temporal ni asignacion definitiva'}
(OUT/'validacion_grafo_red.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('Grafo:',len(G.nodes),'nodos',G.number_of_edges(),'aristas; componentes debiles=',nx.number_weakly_connected_components(G));print('Tipos',dict(counts))

# 7. Visualizacion completa: todos los nodos y aristas, con transparencia.
plt.switch_backend('Agg')
colors={'CIRUGIA':'#B5BEC8','HOSPITAL':'#A6192E','PERSONAL':'#30669B','SALA':'#E89A45','EQUIPO':'#339F85','INSTRUMENTAL':'#59BBA9','POSTOP':'#8854B0','PUNTO_VIAL':'#656B76','FUENTE_REAL':'#2E7D4E','PROCEDIMIENTO':'#3B424A'}
# Posiciones: cirugias en anillo exterior por hospital solicitante, recursos agrupados por hospital.
case_by_h=defaultdict(list)
for c in casos:case_by_h[c['HOSPITAL_SOLICITANTE']].append(c['CASO_ID'])
centers={'H1':(-4.0,1.2),'H2':(4.0,1.2),'H3':(0.0,-4.7)};pos={}
for h,center in centers.items():
 case_ids=case_by_h[h]
 for i,nid in enumerate(case_ids):
  a=2*math.pi*i/len(case_ids);pos[nid]=(center[0]+2.8*math.cos(a),center[1]+2.8*math.sin(a))
 pos[h]=center
 ordinary=[nid for nid,d in G.nodes(data=True) if d['HOSPITAL_ID']==h and d['TIPO_NODO'] not in ['CIRUGIA','HOSPITAL']]
 for i,nid in enumerate(ordinary):
  a=2*math.pi*i/max(1,len(ordinary));pos[nid]=(center[0]+1.0*math.cos(a),center[1]+1.0*math.sin(a))
for j,(nid,data) in enumerate(G.nodes(data=True)):
 if nid in pos:continue
 a=2*math.pi*j/max(1,len(G));pos[nid]=(0.4*math.cos(a),0.4*math.sin(a))
fig,ax=plt.subplots(figsize=(16,11))
segments=[(pos[u],pos[v]) for u,v in G.edges]
ax.add_collection(LineCollection(segments,colors='#738090',linewidths=.18,alpha=.045,zorder=1))
for typ in counts:
 ids=[nid for nid,d in G.nodes(data=True) if d['TIPO_NODO']==typ]
 sz=5 if typ=='CIRUGIA' else 18 if typ not in ('HOSPITAL','PROCEDIMIENTO') else 165
 ax.scatter([pos[n][0] for n in ids],[pos[n][1] for n in ids],s=sz,c=colors.get(typ,'#999999'),alpha=.72,zorder=2,label=f'{typ} ({len(ids)})',rasterized=True)
for h,(x,y) in centers.items():ax.annotate(h,(x,y),xytext=(5,5),textcoords='offset points',weight='bold',fontsize=14,color='#A6192E')
ax.set_aspect('equal');ax.axis('off');ax.set_title(f'Grafo completo H1-H2-H3: {len(G):,} nodos · {G.number_of_edges():,} aristas',fontsize=16,fontweight='bold')
ax.legend(ncol=5,loc='lower center',bbox_to_anchor=(.5,-.035),fontsize=8,frameon=False)
fig.tight_layout();fig.savefig(OUT/'grafo_completo_red.png',dpi=170,bbox_inches='tight');plt.close(fig)

# 8. Subgrafo legible: cirugia -> hospital -> recursos de muestra
caso=next(c for c in casos if c['TIPO_PROCEDIMIENTO']=='CESAREA' and c['HOSPITAL_SOLICITANTE']=='H2')
nid=caso['CASO_ID'];fig,ax=plt.subplots(figsize=(16,8))
subpos={nid:(0,-3.0)}
seleccion=[nid]
label_map={nid:f"Solicitud\n{nid}"}
xcenters={'H1':-5.5,'H2':0,'H3':5.5}
role_wanted=['CANDIDATO_CIRUJANO','CANDIDATO_ANESTESIOLOGO','CANDIDATO_SALA','CANDIDATO_EQUIPO','CANDIDATO_POSTOP']
SG=nx.DiGraph();SG.add_node(nid,**G.nodes[nid])
for h,xx in xcenters.items():
 subpos[h]=(xx,2.8);SG.add_node(h,**G.nodes[h]);seleccion.append(h);label_map[h]=f"Hospital {h}"
 if G.has_edge(nid,h):SG.add_edge(nid,h,**G[nid][h])
 rel_map=defaultdict(list)
 for _,r,d in G.out_edges(nid,data=True):
  if G.nodes[r]['HOSPITAL_ID']==h and d['RELACION'] in role_wanted:
   rel_map[d['RELACION']].append(r)
 for k,rel in enumerate(role_wanted):
  if not rel_map.get(rel):continue
  resource=sorted(rel_map[rel])[0]
  subpos[resource]=(xx+(k-2)*.87,1.0)
  SG.add_node(resource,**G.nodes[resource]);SG.add_edge(h,resource,RELACION='CONTIENE_RECURSO');SG.add_edge(nid,resource,**G[nid][resource]);seleccion.append(resource)
  lab={'CANDIDATO_CIRUJANO':'Cirujano','CANDIDATO_ANESTESIOLOGO':'Anestesia','CANDIDATO_SALA':'Sala','CANDIDATO_EQUIPO':'Equipo','CANDIDATO_POSTOP':'Postop'}[rel]
  label_map[resource]=lab
nx.draw_networkx_edges(SG,subpos,ax=ax,arrows=True,arrowsize=11,alpha=.30,width=1,edge_color='#8993A0')
for typ in set(SG.nodes[x]['TIPO_NODO'] for x in SG.nodes):
 ns=[x for x in SG.nodes if SG.nodes[x]['TIPO_NODO']==typ]
 nx.draw_networkx_nodes(SG,subpos,nodelist=ns,node_size=1050 if typ=='CIRUGIA' else 900 if typ=='HOSPITAL' else 340,node_color=colors.get(typ,'#aaaaaa'),alpha=.94,ax=ax)
nx.draw_networkx_labels(SG,subpos,labels=label_map,font_size=8,font_weight='bold',font_color='#202124',ax=ax)
ax.set_xlim(-8,8);ax.set_ylim(-4.0,3.7);ax.axis('off')
ax.set_title(f"Ejemplo de compatibilidad: {nid} (opciones, NO asignacion confirmada)",fontsize=14,fontweight='bold')
fig.tight_layout();fig.savefig(OUT/'subgrafo_red.png',dpi=160,bbox_inches='tight');plt.close(fig)

# 9. Grafo vial independiente, weighted for shortest path and Prim/MST research (not identical tasks).
V=nx.DiGraph()
for n,data in G.nodes(data=True):
 if data['TIPO_NODO'] in ('HOSPITAL','PUNTO_VIAL'):V.add_node(n)
for u,v,d in G.edges(data=True):
 if d['RELACION']=='CONEXION_VIAL':V.add_edge(u,v,weight=int(d['TIEMPO_MIN_SIM']))
posv={'H1':(-1.7,1.3),'H2':(1.7,1.3),'H3':(0,-1.5),'VIA_01':(-.55,1.75),'VIA_02':(-.65,.7),'VIA_03':(.8,1.5),'VIA_04':(1,.0),'VIA_05':(.5,-1.05),'VIA_06':(-1.25,-.4)}
fig,ax=plt.subplots(figsize=(9,7));nx.draw_networkx_nodes(V,posv,nodelist=[h['HOSPITAL_ID'] for h in hospitales],node_color='#A6192E',node_size=950,ax=ax)
nx.draw_networkx_nodes(V,posv,nodelist=[p['NODO_VIAL_ID'] for p in puntos],node_color='#B7C0CB',node_size=500,ax=ax)
nx.draw_networkx_labels(V,posv,font_size=9,font_weight='bold',font_color='#111111',ax=ax)
und=nx.Graph()
for u,v,d in V.edges(data=True):und.add_edge(u,v,weight=d['weight'])
nx.draw_networkx_edges(und,posv,width=1.6,edge_color='#748293',ax=ax)
nx.draw_networkx_edge_labels(und,posv,edge_labels=nx.get_edge_attributes(und,'weight'),font_size=8,ax=ax)
ax.set_title('Red vial hipotetica (minutos simulados; NO GPS)',fontsize=13,fontweight='bold');ax.axis('off');fig.tight_layout();fig.savefig(OUT/'red_vial_red.png',dpi=165,bbox_inches='tight');plt.close(fig)

# 10. Ejemplo calculado de ruta por Bellman-Ford, NO asignacion clinica
costo,ruta=nx.single_source_bellman_ford(V,'H1',target='H3',weight='weight')
MST=nx.minimum_spanning_tree(und,weight='weight',algorithm='prim')
summary['ejemplo_ruta_H1_H3_min']=costo;summary['ejemplo_ruta_H1_H3_nodos']=ruta
summary['peso_total_arbol_prim_min']=sum(d['weight'] for _,_,d in MST.edges(data=True))
summary['advertencia']='Prim minimiza la suma de la red conectada; Bellman-Ford obtiene un camino minimo de origen a destino. No son equivalentes.'
(OUT/'validacion_grafo_red.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('Bellman-Ford H1→H3',ruta,costo,'min simulados. Prim peso MST=',summary['peso_total_arbol_prim_min'])
