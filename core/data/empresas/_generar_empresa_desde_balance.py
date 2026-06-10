import sys, io, json, types, re, os, shutil
sys.path.insert(0,'.')
sys.modules['db']=types.ModuleType('db')
m=types.ModuleType('db.supabase_client'); m.get_supabase=lambda:None; m.get_supabase_admin=lambda:None
sys.modules['db.supabase_client']=m
from core.utils import conocimiento_balance as cb
from openpyxl import load_workbook

BAL='/tmp/mapeo.xlsx'
NIT, DV, RAZON, SLUG = '900495853','4','MILAGROS GROUP SAS','900495853_milagros'

# 1) conocimiento (per NIT: nombre, cuentas_gasto, centro_costo_sugerido)
k = cb.procesar_balance(open(BAL,'rb').read())

# 2) mapas cuenta->nombre y cc->nombre (normalizado) leyendo el balance
def norm_cc(x): return str(x or '').strip().replace('-','').replace(' ','')
wb=load_workbook(BAL, read_only=True, data_only=True); ws=wb.active
filas=[list(f) for f in ws.iter_rows(values_only=True)]; wb.close()
enc=[str(c or '').strip().lower() for c in filas[3]]
ci={n:enc.index(n) for n in enc}
c_cta=enc.index('cuenta'); c_nom=enc.index('nombre')
c_cc=enc.index('centro de costos') if 'centro de costos' in enc else None
c_ncc=enc.index('nombre cc') if 'nombre cc' in enc else None
cuenta_nom={}; cc_nom={}
for r in filas[4:]:
    if not r or r[c_cta] is None: continue
    cta=str(r[c_cta]).strip()
    if cta and cta!='#N/A': cuenta_nom.setdefault(cta, str(r[c_nom] or '').strip())
    if c_cc is not None and r[c_cc]:
        ccn=norm_cc(r[c_cc])
        if ccn: cc_nom.setdefault(ccn, str(r[c_ncc] or '').strip() if c_ncc is not None else '')

# 3) mapeo_nits.json
mapeo={}
for nit_norm, info in k['nits'].items():
    cta = info['cuentas_gasto'][0] if info.get('cuentas_gasto') else ''
    if not cta: continue
    cc = info.get('centro_costo_sugerido','') or '001001'
    mapeo[nit_norm]={
        "razon_social": info.get('nombre',''),
        "default": {"cuenta": cta, "centro_costo": cc, "concepto": cuenta_nom.get(cta, info.get('nombre',''))},
        "reglas_item": []
    }
mapeo_json={
  "_comentario": f"Mapeo NIT->cuenta+CC de {RAZON}, generado del balance de prueba.",
  "_fallback_global": {"cuenta":"519095","centro_costo":"001001","concepto":"PENDIENTE DE MAPEO - REVISAR",
                       "_nota":"Se usa cuando el NIT del emisor NO está en el catálogo."},
  "mapeo": mapeo
}

# 4) centros_costo.json
centros_json={"_comentario":f"Centros de costo de {RAZON} (sin guiones).","centros_costo": dict(sorted(cc_nom.items()))}

# 5) empresa.json (molde JIPER)
emp=json.load(open('core/data/empresas/901038325_jiper/empresa.json'))
emp["_comentario"]=f"Configuración base de {RAZON}, generada desde balance. Verificar cuentas IVA/retención con el contador."
emp["nit"]=NIT; emp["dv"]=DV; emp["razon_social"]=RAZON
cc_def = max(cc_nom.items(), key=lambda x: 1)[0] if cc_nom else "001001"
cc_def = "001001" if "001001" in cc_nom else (sorted(cc_nom)[0] if cc_nom else "001001")
emp["cc_default"]=cc_def; emp["cc_default_nombre"]=cc_nom.get(cc_def,"")

# Escribir
base=f'/tmp/stage/core/data/empresas/{SLUG}'
os.makedirs(base, exist_ok=True)
json.dump(emp, open(f'{base}/empresa.json','w'), ensure_ascii=False, indent=2)
json.dump(mapeo_json, open(f'{base}/mapeo_nits.json','w'), ensure_ascii=False, indent=2)
json.dump(centros_json, open(f'{base}/centros_costo.json','w'), ensure_ascii=False, indent=2)

# 6) _empresas_index.json actualizado
idx=json.load(open('core/data/empresas/_empresas_index.json'))
if not any(e['nit']==NIT for e in idx['empresas']):
    idx['empresas'].append({"id":NIT,"nit":NIT,"razon_social":RAZON,"carpeta":SLUG,"activa":True})
os.makedirs('/tmp/stage/core/data/empresas', exist_ok=True)
json.dump(idx, open('/tmp/stage/core/data/empresas/_empresas_index.json','w'), ensure_ascii=False, indent=2)

print("Proveedores mapeados:", len(mapeo))
print("Centros de costo:", len(centros_json['centros_costo']))
print("cc_default:", cc_def, cc_nom.get(cc_def,''))
print("Ejemplos mapeo:")
for kk,vv in list(mapeo.items())[:4]:
    print("  ", kk, "->", vv['default']['cuenta'], vv['default']['centro_costo'], "|", vv['razon_social'][:24])
