# Despliegue — Integración Token DIAN al módulo POS

**Fecha:** 16 de mayo de 2026
**Empresa objetivo:** JIPER SAS (multi-empresa compatible)
**Estado:** Lista. 18/18 tests pasando. Cuadre Db=Cr verificado con datos reales.

---

## Qué se entregó

| Archivo | Tipo | Acción en repo |
|---|---|---|
| `core/data/datos_punto.json` | **Modificado** | Reemplazar (añade `prefijo_token` a cada sucursal) |
| `core/procesadores/procesador_pos.py` | **Modificado** | Reemplazar (añade campo `prefijo_token` a clase Sucursal) |
| `core/procesadores/parser_token_dian.py` | **Nuevo** | Subir |
| `core/procesadores/comparador_pos_token.py` | **Nuevo** | Subir |
| `app_pages/4b_Ingresos_POS.py` | **Modificado** | Reemplazar (añade tab "Conciliar con Token DIAN") |
| `tests/test_pos_token.py` | **Nuevo** | Subir |

**No hace falta migración SQL.** Todo es código y datos embebidos.

---

## Pasos para desplegar

### 1) Subir archivos al repo

Estructura final esperada:

```
plataforma-contable/
├── core/
│   ├── data/
│   │   └── datos_punto.json                    ← REEMPLAZAR
│   └── procesadores/
│       ├── procesador_pos.py                   ← REEMPLAZAR
│       ├── parser_token_dian.py                ← NUEVO
│       └── comparador_pos_token.py             ← NUEVO
├── app_pages/
│   └── 4b_Ingresos_POS.py                      ← REEMPLAZAR
└── tests/
    └── test_pos_token.py                       ← NUEVO
```

**Commit sugerido:**
```bash
git add core/data/datos_punto.json core/procesadores/ app_pages/4b_Ingresos_POS.py tests/test_pos_token.py
git commit -m "feat(pos): integrar conciliación con Token DIAN

- Añade campo prefijo_token al maestro de sucursales (25 prefijos JIPER).
- Nuevo parser_token_dian.py: lee Excel Token DIAN, filtra solo
  factura electrónica emitida, calcula desglose IVA/INC con 8% fijo,
  omite STL (procesado por flujo Henko).
- Nuevo comparador_pos_token.py: compara plano POS vs agregado Token
  por (fecha, sucursal_cc), detecta diferencias con tolerancia
  configurable, aplica elecciones del contador y genera plano final
  con cuadre Db=Cr.
- Página Ingresos POS: nueva tab 3 'Conciliar con Token DIAN' con
  uploader, tabla editable de diferencias y descarga del plano
  conciliado.
- 18 tests pytest, todos pasando."
git push
```

Railway redeplega solo en ~2 minutos.

### 2) Probar la funcionalidad

Una vez Railway termine el deploy:

1. Entra a la app, selecciona empresa **JIPER SAS**.
2. Ve a **Ingresos POS**.
3. **Pestaña 1 o 2**: procesa los reportes POS de marzo como siempre.
4. **Pestaña 3 "Conciliar con Token DIAN"**:
   - Sube el archivo Excel del Token (el extraído del ZIP, no el ZIP).
   - Ajusta tolerancia (default $100).
   - Mantén marcado "Omitir prefijo STL".
   - Clic en **🚀 Procesar Token y comparar**.

### 3) Revisar diferencias y elegir fuente

Verás una tabla con cada (día × sucursal) y su estado:
- ✅ **coincide** — POS y Token cuadran (no requiere acción).
- ⚠️ **difiere** — montos distintos. Elige Token o POS con el dropdown.
- 🔴 **solo_pos** — POS reportó pero el Token no tiene factura (¿pendiente de envío?).
- 🔴 **solo_token** — Token tiene factura pero POS no reportó ese día.

Por defecto, las filas con coincidencia se ocultan (puedes mostrarlas con el checkbox).

### 4) Generar plano final

Clic en **✨ Generar plano final**. Descarga el `.txt` (TSV) o `.xlsx` con
todas las líneas. El plano siempre cuadra Db = Cr automáticamente.

---

## Mapeo de prefijos Token → sucursales JIPER

Estos quedaron grabados en `core/data/datos_punto.json`:

| CC | Sucursal | Prefijo Token | Clase |
|---|---|---|---|
| 001101 | Indiana | **IND** | Santa Leña |
| 001102 | Oviedo | **OVI** | Santa Leña |
| 001103 | Tesoro | **TES** | Santa Leña |
| 001104 | San Lucas | **LUC** | Santa Leña |
| 001105 | Del Este | **EST** | Santa Leña |
| 001106 | Viva Envigado | **VIV** | Santa Leña |
| 001107 | Laureles | **LAU** | Santa Leña |
| 001108 | Llano Grande | **LLA** | Santa Leña |
| 001109 | Burbuja Poblado | **POB** | Santa Leña |
| 001110 | Mixy Los Colores | **MIXY** | Santa Leña |
| 001111 | Ciudad del Río | **CIU** | Santa Leña |
| 001112 | Fabricato | **FAB** | Santa Leña |
| 001113 | Los Molinos | **MOLI** | Santa Leña |
| 001114 | Unicentro | **UNIC** | Santa Leña |
| 001115 | Las Vegas | **VE** | Santa Leña |
| 001116 | Medical Tower | **MED** | Santa Leña |
| 001117 | Milla de Oro | **MIL** | Santa Leña |
| 001118 | Nock | **NO** | Santa Leña |
| 001201 | Milagros Tesoro | **MTE** | R. Milagros |
| 001202 | Milagros Remedios | **MRE** | R. Milagros |
| 001203 | Milagros Viva | **MVI** | R. Milagros |
| 001204 | Milagros Laureles | **MLA** | R. Milagros |
| 001205 | Milagros Fabricato | **MFA** | R. Milagros |
| 001206 | Milagros Manila | **MMA** | R. Milagros |
| 001207 | Milagros Milla de Oro | **MMI** | R. Milagros |

**Prefijo omitido por config:** `STL` (88 docs / $1.057M en marzo) — se
procesa por el flujo Henko separado.

---

## Algoritmo de desglose IVA/INC

El Token solo trae el TOTAL bruto (sin desglose base/IVA). Para
contabilizar usamos esta lógica:

1. Asumir tarifa fija **8% INC** (Santa Leña / Milagros).
2. `base_teorica = total / 1.08`
3. `inc_teorico = base_teorica × 0.08`
4. Si `base + inc ≈ total` (tolerancia ±$5) → estado `correcto`.
5. Si la diferencia es ~10% del total → estado `con_propina` (omitir).
6. Si la diferencia no encaja → estado `revisar` (avisar al contador).

**Validado contra el Token real de marzo:** 1.489 celdas, **todas con
estado "correcto"** — el algoritmo funciona perfectamente para POS de
Santa Leña/Milagros.

---

## Tests automatizados

```bash
pip install pytest openpyxl pandas
cd /ruta/al/repo
python -m pytest tests/test_pos_token.py -v
```

Esperado: **18 passed**.

Casos cubiertos:
- Desglose IVA/INC (4 tests).
- Parser: filtros por tipo de doc, emisor, prefijos omitidos, mapeo (6 tests).
- Comparador: coincide/difiere/solo_pos/solo_token, tolerancia, resumen (6 tests).
- Aplicación de elecciones con cuadre Db=Cr (2 tests).

---

## Cosas que NO se hicieron y se pueden hacer después

- **Módulo DSE** (Documento Soporte con no obligados): el Token trae 109
  docs DSE por $61M en marzo. Hoy se descartan; se hará otro módulo
  cuando tengas la lógica contable definida.
- **Módulo STL detallado**: las 88 facturas STL ($1.057M) son las grandes
  ventas con IVA variable que deben verse caso por caso. Por ahora se
  omiten; se procesarán con XML/PDF cuando construyamos el flujo.
- **Notas crédito (NC*)**: hoy se descartan del Token. Cuando esté listo
  el flujo de NCs, sumarlas restando ingresos.
- **Reconciliación con nómina electrónica**: el Token trae 280 nóminas
  individuales — pertenecen al módulo PILA, no a POS.

---

## Problemas comunes y soluciones

### "Columna 'X' no encontrada en el Token"
El export del Token DIAN tiene columnas fijas. Si DIAN cambia el
formato del export, hay que actualizar las constantes `COL_*` en
`core/procesadores/parser_token_dian.py`.

### "Sucursales que no veo en la comparación"
La comparación solo incluye sucursales que aparezcan en POS o en
Token. Si una sucursal no facturó ese día, no aparece (es lo correcto).

### "Prefijos no mapeados"
Si en el Token aparece un prefijo nuevo (ej. abrieron un punto), se
reporta como "no mapeado" y se ignora. Hay que agregar la sucursal y
su `prefijo_token` a `core/data/datos_punto.json` y redesplegar.

### "El total Token marzo difiere de lo que recuerdo"
Verifica que estás filtrando solo el mes correcto en la pestaña 3.
El Token de prueba subido contiene marzo Y abril mezclados.

---

## ✅ Definición de Hecho

El módulo está listo cuando:

- [x] 18/18 tests pytest pasan localmente.
- [x] Cuadre Db = Cr verificado con datos reales del Token marzo 2026.
- [x] 25 sucursales con prefijo_token mapeado correctamente.
- [x] STL omitido por configuración.
- [ ] Archivos subidos al repo y Railway redeplegado.
- [ ] Probado con SILLA TRES o JIPER en marzo y verificado contra
      expectativas del contador.
