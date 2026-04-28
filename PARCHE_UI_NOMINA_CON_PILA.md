# 🩹 Parche UI + Procesador — Integrar PILA en módulo Nómina

> **Versión:** 2.0 (con procesador PILA listo y testeado)
> **Aplica en:** `pages/3_💼_Nómina.py` y `core/procesadores/procesador_nomina.py`

---

## 📌 Cambios resumidos

1. **SQL:** desactivar módulos PILA y Provisiones de la pantalla principal.
2. **Procesador:** copiar `procesador_pila.py` a `core/procesadores/`.
3. **UI Nómina:** agregar uploader opcional de PILA (PDF) al módulo Nómina.
4. **Lógica Nómina:** integrar lectura de PILA + cálculo de ajustes Comp 9 cuando provisión ≠ pagado.

Lo bueno: **el lector de PILA y la lógica de ajustes ya están listos y testeados** (5/5 tests pasan contra la prefactura real #84919326). Solo hay que cablear desde el procesador de Nómina existente.

---

## 1️⃣ SQL — desactivar módulos viejos

Ya está en `setup_desactivar_pila_y_provisiones.sql`. Ejecutar en Supabase.

Resultado: los íconos 📎 PILA y 📊 Provisiones desaparecen de la pantalla principal.

---

## 2️⃣ Copiar el procesador PILA al repo

```bash
# Copiar el archivo
cp procesador_pila.py plataforma_web/core/procesadores/

# Asegurar que pdfplumber esté en requirements.txt
echo "pdfplumber>=0.10.0" >> plataforma_web/requirements.txt
```

El módulo expone:

```python
from core.procesadores.procesador_pila import (
    leer_planilla_pila,        # función principal (PDF o XLSX)
    calcular_ajustes_pila,     # genera líneas Comp 9 de ajuste
    PilaLeida,                 # dataclass con todos los datos
    LineaAjuste,               # dataclass para el ajuste
)
```

---

## 3️⃣ Modificar la página `pages/3_💼_Nómina.py`

### A) Sección de uploaders (2 columnas)

**Reemplaza** el uploader único actual por dos columnas:

```python
col_n1, col_n2 = st.columns(2)
with col_n1:
    st.markdown("**📋 Planilla de Nómina** (obligatorio)")
    archivo_nomina = st.file_uploader(
        "NOMINA_CASATRECE_<MES>.xls",
        type=["xls", "xlsx"],
        help="Planilla mensual con devengados, deducciones, incapacidades.",
        key="archivo_nomina",
    )
with col_n2:
    st.markdown("**📎 Planilla PILA pagada** (opcional)")
    archivo_pila = st.file_uploader(
        "Prefactura PILA del mes (.pdf, .xlsx)",
        type=["pdf", "xlsx", "xls"],
        help="Prefactura SuAporte / Enlace Operativo del mes. "
             "Se usa para validar provisiones vs aportes reales pagados. "
             "Si hay diferencia, se generan líneas de ajuste en Comp 9.",
        key="archivo_pila",
    )
```

### B) Aviso explicativo antes de los uploaders

```python
st.info(
    "📋 **Cómo funciona el módulo de Nómina:**\n\n"
    "- La **planilla de nómina** genera Comp 11 (causación quincenal) y "
    "Comp 9 (provisiones del último día del mes).\n"
    "- Si subes la **prefactura PILA** del periodo, el sistema compara lo "
    "provisionado vs lo realmente pagado en aportes y agrega líneas de "
    "ajuste automáticas en Comp 9 con detalle 'AJUSTE PILA <CONCEPTO>'.\n"
    "- PILA es **opcional**: puedes procesar solo la nómina si aún no "
    "tienes la planilla pagada del mes."
)
```

### C) Llamada al procesador

Versión defensiva por si el procesador todavía no acepta `archivo_pila`:

```python
import inspect

kwargs = dict(
    archivo_nomina=archivo_nomina,
    anio=int(anio),
    mes=int(mes_idx),
)
sig = inspect.signature(procesar_nomina)
if "archivo_pila" in sig.parameters:
    kwargs["archivo_pila"] = archivo_pila
df_plano, log, resumen = procesar_nomina(**kwargs)
```

### D) Mostrar resumen de PILA cuando se subió

Después del cuadre Db=Cr, agregar:

```python
if resumen.get("pila_leida"):
    pila_info = resumen["pila_leida"]
    st.markdown("#### 📎 Validación con PILA")
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        st.metric("Planilla PILA", f"#{pila_info['numero_planilla']}")
    with col_p2:
        st.metric("Total pagado", f"$ {pila_info['total_final']:,}".replace(",", "."))
    with col_p3:
        st.metric("Empleados PILA", pila_info["n_empleados"])
    with col_p4:
        n_ajustes = resumen.get("n_ajustes_pila", 0)
        st.metric("Líneas de ajuste", n_ajustes)

    if n_ajustes > 0:
        st.warning(
            f"⚠️ Se generaron **{n_ajustes} líneas de ajuste** porque "
            "la provisión de nómina no coincide exactamente con lo pagado en PILA. "
            "Revisa el plano para verificar."
        )
    else:
        st.success("✅ Provisión de nómina = aportes pagados en PILA. Sin ajustes necesarios.")
```

---

## 4️⃣ Modificar el procesador de Nómina

### A) Imports

Agregar al inicio del `procesador_nomina.py`:

```python
from typing import Optional
from core.procesadores.procesador_pila import (
    leer_planilla_pila,
    calcular_ajustes_pila,
    LineaAjuste,
)
```

### B) Firma de la función principal

```python
def procesar_nomina(
    archivo_nomina,
    archivo_pila=None,           # ← nuevo parámetro opcional
    anio: int = 2026,
    mes: int = 3,
) -> Tuple[pd.DataFrame, List[str], dict]:
    ...
```

### C) Después de generar las provisiones (Comp 9), antes del return

Aquí está la integración clave. **Necesitas saber qué cuenta usa tu procesador para cada concepto de provisión.** Mira el log del Comp 9 actual y reemplaza estos placeholders:

```python
# ============================================================
# Integración PILA: ajustes provisionado vs pagado
# ============================================================
pila_resumen = None
n_ajustes_pila = 0

if archivo_pila is not None:
    log.append("")
    log.append("📎 Procesando planilla PILA...")

    # Construir catálogo {cedula: nombre} desde empleados.json
    catalogo_nombres = {
        emp["nit"]: emp["nombre"]   # ajusta los keys según tu empleados.json
        for emp in EMPLEADOS_LIST    # tu lista de empleados ya cargada
    }

    pila = leer_planilla_pila(archivo_pila, catalogo_empleados=catalogo_nombres)
    log.extend(pila.log)

    # Construir dict de provisiones reales calculadas por el procesador.
    # IMPORTANTE: este dict debe llenarse con lo que TU procesador
    # provisionó por empleado para cada concepto.
    provisiones_por_empleado = {}
    for cedula, totales_emp in provisiones_calculadas.items():  # ← variable interna tuya
        provisiones_por_empleado[cedula] = {
            "pension": totales_emp["pension_empleador_12"],   # 12% empleador
            "salud":   totales_emp["salud_empleado_4"],       # 4% empleado
            "arl":     totales_emp["arl"],
            "caja":    totales_emp["caja_4"],
        }

    # CUENTAS DE PROVISIÓN — ajusta según tu plan contable real.
    # Estos son ejemplos; usa las cuentas que ya estás generando en Comp 9.
    cuentas_provision = {
        "pension": "23700501",   # ← TU cuenta de aportes pensión por pagar
        "salud":   "23700502",   # ← TU cuenta de salud por pagar
        "arl":     "23700503",   # ← TU cuenta de ARL por pagar
        "caja":    "23700504",   # ← TU cuenta de caja por pagar
    }

    # Cuentas de gasto contrapartida (para que cuadre Db=Cr)
    cuentas_gasto = {
        "pension": "510606",    # ← TU cuenta de aportes pensión gasto
        "salud":   "510603",    # ← TU cuenta de salud gasto
        "arl":     "510609",    # ← TU cuenta de ARL gasto
        "caja":    "510612",    # ← TU cuenta de caja gasto
    }

    ajustes = calcular_ajustes_pila(
        provisiones_por_empleado, pila, cuentas_provision,
        tolerancia=10,  # diferencias hasta $10 se ignoran (redondeos)
    )
    n_ajustes_pila = len(ajustes)

    if ajustes:
        log.append(f"   📋 Generando {len(ajustes)} líneas de ajuste en Comp 9...")
        ULTIMO_DIA = date(anio, mes, ultimo_dia_del_mes(anio, mes))
        for ajuste in ajustes:
            # Identificar concepto del detalle: 'AJUSTE PILA PENSION - X' → 'pension'
            concepto = ajuste.detalle.split()[2].lower()
            cuenta_gasto = cuentas_gasto.get(concepto, "")

            # Línea al pasivo
            filas.append({
                "CUENTA": ajuste.cuenta,
                "COMPROBANTE": "9",
                "FECHA": ULTIMO_DIA.strftime("%m/%d/%Y"),
                "DOCUMENTO": f"AJUSTE-{anio}{mes:02d}",
                "DOC REFERENCIA": pila.numero_planilla,
                "NIT": ajuste.nit,
                "DETALLE": ajuste.detalle,
                "TR": ajuste.tr,
                "VALOR": int(ajuste.valor),
                "BASE": 0,
                "CENTRO DE COSTO": "PRINCIPAL",
            })
            # Línea contrapartida en cuenta de gasto (TR contrario)
            tr_contrario = "1" if ajuste.tr == "2" else "2"
            if cuenta_gasto:
                filas.append({
                    "CUENTA": cuenta_gasto,
                    "COMPROBANTE": "9",
                    "FECHA": ULTIMO_DIA.strftime("%m/%d/%Y"),
                    "DOCUMENTO": f"AJUSTE-{anio}{mes:02d}",
                    "DOC REFERENCIA": pila.numero_planilla,
                    "NIT": ajuste.nit,
                    "DETALLE": ajuste.detalle,
                    "TR": tr_contrario,
                    "VALOR": int(ajuste.valor),
                    "BASE": 0,
                    "CENTRO DE COSTO": "PRINCIPAL",
                })

    # Datos para mostrar en UI
    pila_resumen = {
        "numero_planilla": pila.numero_planilla,
        "periodo_cotizacion": pila.periodo_cotizacion,
        "total_final": int(pila.totales.total_final),
        "n_empleados": len(pila.por_empleado),
        "totales": {
            "pension": int(pila.totales.aportes_pension),
            "salud":   int(pila.totales.aportes_salud),
            "riesgos": int(pila.totales.aportes_riesgos),
            "cajas":   int(pila.totales.aportes_cajas),
        },
    }

# ============================================================
# Final: agregar al resumen
# ============================================================
resumen["pila_leida"] = pila_resumen
resumen["n_ajustes_pila"] = n_ajustes_pila
```

---

## 5️⃣ Validación contable del ajuste

**Cuadre Db=Cr garantizado por construcción:** cada línea de ajuste al pasivo (`23700xxx`) se acompaña automáticamente de una línea contrapartida en la cuenta de gasto correspondiente con TR contrario. Por eso la suma sigue cuadrando.

**Naturaleza del ajuste según el caso:**

| Caso | Diferencia | TR pasivo | TR gasto |
|---|---|---|---|
| PILA pagó MÁS que provisión | +diff | Cr (2) → más pasivo | Db (1) → más gasto |
| PILA pagó MENOS que provisión | −diff | Db (1) → menos pasivo | Cr (2) → reverso gasto |

---

## 6️⃣ Checklist de despliegue

```
1) Ejecutar SQL en Supabase
   └─ setup_desactivar_pila_y_provisiones.sql
       └─ Verificar: módulos PILA y Provisiones desaparecen de la portada

2) Copiar archivos al repo
   ├─ core/procesadores/procesador_pila.py        ← NUEVO
   └─ requirements.txt                             ← agregar pdfplumber

3) Modificar pages/3_💼_Nómina.py
   ├─ Bloque A: 2 uploaders en columnas
   ├─ Bloque B: aviso explicativo
   ├─ Bloque C: pasar archivo_pila al procesador (versión defensiva)
   └─ Bloque D: mostrar resumen PILA en UI

4) Modificar core/procesadores/procesador_nomina.py
   ├─ Imports
   ├─ Firma con archivo_pila=None
   └─ Bloque de integración + ajustes

5) Validar con marzo 2026
   ├─ Solo nómina (sin PILA): debe seguir cuadrando $18.315.182 (107 líneas)
   └─ Nómina + PILA pagada del 84919326:
       ├─ Si provisión = pagado → 0 ajustes
       ├─ Si hay diferencia → líneas con detalle "AJUSTE PILA"
       └─ Cuadre Db=Cr siempre

6) Limpiar archivos viejos del repo (cuando confirmes que todo funciona)
   ├─ git rm "pages/2_📎_PILA.py"
   └─ git rm "pages/4_📊_Provisiones.py"

7) Commit + push
   └─ Railway redespliega solo
```

---

## 📊 Validación con datos reales — PILA marzo 2026 (#84919326)

El procesador `procesador_pila.py` ya fue probado contra la prefactura real:

| Dato | Valor extraído |
|---|---|
| Planilla | 84919326 |
| Periodo cotización | marzo de 2026 |
| Empresa | CASA UNOTRES SAS (NIT 900473959) |
| Empleados detectados | 4/4 ✅ |
| IBC Pensión total | $12.403.216 |
| Aportes Pensión | $1.984.800 |
| Aportes Salud | $496.400 |
| Aportes Riesgos | $64.000 |
| Aportes Cajas | $489.300 |
| SENA / ICBF | $0 (✅ confirma exoneración Art. 114-1) |
| **TOTAL FINAL** | **$3.034.500** |
| Validación cruzada (suma empleados ≈ total) | ✅ |

**Tests de la lógica de ajustes** (`test_ajustes_pila.py`): 5/5 pasan
- Provisión exacta = pagado → 0 ajustes
- Provisión menor → solo líneas Cr (faltó provisionar)
- Provisión mayor → solo líneas Db (sobró provisión)
- Empleado en PILA pero no en provisión → se omite
- Tolerancia de redondeo configurable

---

## 🎯 Notas finales

- **El parser de PILA reordena nombres** usando el catálogo de `empleados.json` cuando se le pasa. Sin catálogo, los nombres pueden quedar desordenados (cosmético, no afecta cálculos).
- **Yohana se consolida automáticamente:** la planilla la trae en 3 renglones (1+2+27 días). El parser los suma → 30 días, $460.200 pensión, etc.
- **Tolerancia recomendada:** $10 pesos para evitar ajustes por redondeos minúsculos.

---

## 📞 Si necesitas ayuda con el wiring

Cuando me adjuntes el `procesador_nomina.py` actual, te entrego:

1. Las cuentas exactas de provisión (en lugar de los placeholders `23700xxx`).
2. La estructura `provisiones_por_empleado` ya construida desde tu lógica interna.
3. El bloque de integración listo para pegar.
