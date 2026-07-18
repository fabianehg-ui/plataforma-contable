# CÓMO SUBIR — Conectar TODOS los módulos a la contabilidad central

Amplía "agregar al movimiento del mes" a más módulos y hace que cualquier plano
en orden Contai se cause bien. Fecha: 18-jul-2026. **Sin migración.**

## Qué cambia

- **Normalizador de columnas** (`integracion.normalizar_columnas`): cualquier
  plano en orden Contai se causa aunque sus columnas tengan otros nombres/caso
  (p.ej. el formato *silla tres* de los XML DIAN: "Comprobante", "Fecha", "Doc ref").
- **Nuevos módulos conectados** (opción de causar junto a descargar):
  - **Caja Menor** (`origen = caja_menor`)
  - **Compras DIAN** (`origen = compras_dian`)
  - **Descargador XML** (5b): causa **por empresa** (`r.empresa_id`), correcto
    para su flujo multi-empresa (`origen = dian_xml`).

## Ya conectados antes (recordatorio)

Nómina, Captura, Cruce (pagos/recaudos), Ventas C13, Compras y Egresos, Bittal,
Bancos y POS. Todo lo causado se ve y se reversa en **🔗 Centro Contable**.

## Casos especiales (a propósito NO se auto-causan a una sola empresa)

- **DIAN XML masivo (5a)**: concatena varias empresas en un solo plano; causar a
  una sola sería incorrecto. Se mantiene como exportador.
- **PILA y Vacaciones**: se consolidan dentro del **plano de nómina** del mes
  (para no duplicar); se causan al guardar la nómina.
- **Siigo a Contai / Siigo Excel**: generan varios archivos .txt para exportar a
  Contai; su causación en INTEGRAL queda como paso siguiente (por archivo).

## Archivos

| Archivo | Estado |
|---|---|
| `core/contable/integracion.py` | **MOD** — `normalizar_columnas`; orígenes caja_menor/compras_dian. |
| `app_pages/1_Caja_Menor.py` | **MOD** — opción causar. |
| `app_pages/2_Compras_DIAN.py` | **MOD** — opción causar. |
| `app_pages/5b_Descargador_XML.py` | **MOD** — causar por empresa. |
| `tests/test_integracion.py` | **MOD** — + pruebas del normalizador. **96 pruebas pasan.** |

Requiere los archivos base del Puente contable. Sin migración.
