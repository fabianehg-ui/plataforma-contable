# Entrega final — sesión 1 mayo 2026
## Plataforma Contable Silla Tres

Este paquete contiene los **archivos definitivos** con todos los cambios trabajados en la sesión.

**Última actualización:** 1 de mayo de 2026 (incluye refactor multi-empresa del puente motor — mini-paso de Fase 1).

---

## Archivos incluidos

| Archivo | Destino en el servidor | ¿Para qué? |
|---|---|---|
| `puente_motor_v03.py` | `core/procesadores/puente_motor_v03.py` | Procesador principal — mapeo, ordenamiento, remapeo de cuentas, **soporte multi-empresa** |
| `mapeo_nits.json` | `core/data/empresas/900451388_silla_tres/mapeo_nits.json` | Catálogo de NITs (con correcciones de Atocha y San Ignacio) |
| `5_📥_DIAN_XML.py` | `pages/5_📥_DIAN_XML.py` | Página de Streamlit con los 3 campos de consecutivo |
| `dian_descargador_v03.js` | (referencia, código fuente) | JS fuente del descargador |
| `dian_descargador_v03_INLINE.txt` | (pegar en el marcador del navegador) | Bookmarklet final con filtro de fecha corregido |
| `generar_bookmarklet.py` | (utilitario, fuera del proyecto) | Script para regenerar el INLINE.txt si editas el .js |
| `RESUMEN_SESION.md` | (documentación) | Resumen ejecutivo para retomar en chat nuevo |
| `PLAN_MIGRACION.md` | (documentación) | Plan de 5 fases para multi-empresa real |

---

## Cambios principales de esta sesión

### 1. Bookmarklet DIAN corregido
- `FilterType: '3'` (recepción DIAN) → `'1'` (emisión real). Antes traía facturas fuera de rango.
- Filtrado client-side redundante: descarta cualquier doc con `IssueDate` fuera del rango pedido.
- `generar_bookmarklet.py` reescrito como tokenizer real que respeta strings y regex.

### 2. NITs corregidos
- Atocha (`900380500`) cambiada a `14350511` con CC `10-04` (estaba en `13300501` por bug del aprendizaje BP).
- San Ignacio (`890933726`) cambiada a `52058402` con CC `10-19` (mismo bug).

### 3. Plano contable mejorado
- Ordenamiento por **fecha de emisión ascendente** y renumeración de consecutivos.
- Cada comprobante (3, 7, 12) lleva su propia secuencia.
- Orden interno: gasto → IVA → IBUA/ICUI/INC → retenciones → proveedor.

### 4. Cuentas correctas según BP de Silla Tres
- IVA descontable compras 19% → `24081007` (antes `24080201`).
- IVA descontable compras 5% → `24081006` (antes `24080203`).
- IVA descontable servicios 19% → `24081303` (antes `24080308`).
- IBUA y ICUI → `14359505` (impuesto saludable, en inventario).
- INC con regla contextual (telefonía → `52159502`, otros gastos → `52159501`, con inventario → `14359505`).
- ReteIVA → `23670515` (Régimen Simple 15%).

### 5. Página Streamlit
- 3 campos separados de consecutivo inicial (Compras, ND, NC) en lugar de uno solo.

### 6. Refactor multi-empresa del puente motor (mini-paso Fase 1) ✨

`puente_motor_v03.py` ahora soporta múltiples empresas. La función central de remapeo de cuentas pasó de hardcodear "Silla Tres" a leer el config aplicable según el NIT.

**Cambios técnicos:**
- Nueva función `remapear_cuentas_por_empresa(resultados, config_override=None)`.
- Dict central `CONFIGS_POR_NIT` que mapea NIT → configuración de cuentas. Hoy solo tiene Silla Tres.
- Helper `obtener_config_empresa(nit, config_override)`.
- Función vieja `remapear_cuentas_silla_tres()` mantenida como **alias deprecado**.
- La llamada interna en `agregar_retenciones_a_resultados()` ahora usa la función nueva.

**Para agregar una empresa nueva:**

```python
# En puente_motor_v03.py:
CONFIG_EMPRESA_NUEVA = {
    "_descripcion": "EMPRESA EJEMPLO — NIT 800999999",
    "iva_compras_19":    "24080501",
    "iva_compras_5":     "24080502",
    "iva_servicios_19":  "24080503",
    "iva_servicios_5":   "24080503",
    "saludable_inventario": "14361001",
    "consumo_gasto":     "51950201",
    "consumo_telefonia": "51950202",
    "mapa_iva_legacy_a_concepto": {
        "24080201": ("compras","19"),
        "24080203": ("compras","5"),
        "24080308": ("servicios","19"),
    },
    "mapa_consumo_legacy": {
        "24080540": "saludable",
        "24080515": "saludable",
        "24080530": "consumo",
    },
}

CONFIGS_POR_NIT = {
    "900451388": CONFIG_SILLA_TRES,
    "800999999": CONFIG_EMPRESA_NUEVA,   # ← nueva entrada
}
```

**Estado de Fase 1:**
- ✓ Mini-paso completado y testeado (5/5 tests)
- ⏳ Falta: integrar a `pages/`, leer empresas desde Supabase, mover configs al bucket `empresas-config`. En chat nuevo siguiendo `PLAN_MIGRACION.md`.

---

## Pasos para desplegar (en orden)

### 1. Reemplazar archivos en el servidor

```bash
cp puente_motor_v03.py core/procesadores/puente_motor_v03.py
cp mapeo_nits.json core/data/empresas/900451388_silla_tres/mapeo_nits.json
cp "5_📥_DIAN_XML.py" pages/5_📥_DIAN_XML.py
# Reiniciar Streamlit (o esperar hot-reload)
```

> **Nota:** el `puente_motor_v03.py` nuevo es **drop-in replacement**. Procesar Silla Tres da exactamente el mismo resultado — el refactor solo añade capacidad multi-empresa sin cambiar el comportamiento actual.

### 2. Actualizar el bookmarklet del navegador

1. Ctrl+Shift+O → editar marcador del descargador DIAN.
2. Borrar el campo URL.
3. Copiar todo el contenido de `dian_descargador_v03_INLINE.txt`.
4. Pegar en el campo URL y guardar.

### 3. Crear cuentas en Siigo (si no existen)

| Código | Nombre | Naturaleza |
|---|---|---|
| `14359505` | Renombrar a "IMPUESTO SALUDABLE 20%" | Activo (inventario) |
| `23670515` | RETEIVA RÉGIMEN SIMPLE 15% | Pasivo (retención practicada) |

### 4. Procesar marzo 2026

1. Re-descargar XMLs del 01-07 marzo con bookmarklet nuevo.
2. Subir el ZIP a la página `📥 DIAN XML`.
3. Configurar año 2026, mes 3, los 3 consecutivos iniciales (Compras, ND, NC), filtro por emisión, empresa Silla Tres.
4. Procesar.

### 5. Validar el resultado

- ✓ Solo facturas del 01 al 07 marzo
- ✓ Ordenado por fecha de emisión ascendente
- ✓ Cada comprobante con su propia secuencia
- ✓ Orden interno: gasto → IVA → IBUA/ICUI/INC → retenciones → proveedor
- ✓ IVA compras 19%/5% en `24081007`/`24081006`
- ✓ IVA servicios 19% en `24081303`
- ✓ IBUA/ICUI en `14359505`
- ✓ INC telefonía en `52159502`, otros gastos en `52159501`
- ✓ ReteIVA en `23670515`
- ✓ Atocha en `14350511` con CC `10-04`
- ✓ San Ignacio en `52058402` con CC `10-19`

---

## Estado de la plataforma

### Lo que YA funciona

- Esquema Supabase completo (tablas `empresas`, `usuario_empresa`, `procesamientos`, `parametros_empresa`) con RLS.
- Auth multi-empresa: `require_auth`, `require_empresa`, `require_rol` (admin/operador/consulta).
- Selector de empresa activa en sidebar.
- Páginas operativas: Caja Menor, Nómina, Provisiones, PILA, Configuración (placeholders en tabs), Compras DIAN (placeholder).
- Class `Configuracion` lista para Supabase Storage.
- Procesador DIAN con refactor multi-empresa listo para conectarse.

### Lo que falta (PLAN_MIGRACION.md tiene el detalle)

| Fase | Qué entrega | Esfuerzo |
|---|---|---|
| **F1** (en progreso) | DIAN integrado a la plataforma web | 1 chat |
| **F2** | Configs por empresa en Supabase Storage | 1 chat |
| **F3** | UI para subir archivos de configuración | 1 chat |
| **F4** | Permisos de módulo por empresa y por usuario | 1 chat |
| **F5** | UI para invitar usuarios | 1 chat |

---

## Pendientes operativos

1. **Revisar NITs con cuenta `13300501`** — posibles bugs como Atocha/San Ignacio:
   - `860027404` (ALLIANZ), `890324177` (VALLE DEL LILI), `890399001` (CÁMARA COMERCIO CALI), `900252083` (REFRIARTIC), `900451388` (SILLA TRES propia), `901451772` (ALLPHA).

2. **Bolsas plásticas** — definir cuenta cuando aparezca código UBL `22`.

3. **`empresa.json` para Silla Tres** — agregar `cuentas_iva_por_concepto_y_tarifa` y `cuentas_reteiva` (mejora para Fase 2).

4. **Reprocesar enero y febrero 2026** con sistema corregido.

---

## Si algo sale mal

Reporta con este template:

```
Acción: [qué intentaste]
Esperado: [qué pensabas que pasaría]
Ocurrió: [qué pasó realmente]
Mensaje de error: [pegar mensaje completo]
Archivo / página: [dónde]
```

Si abrís chat nuevo, pegá `RESUMEN_SESION.md` y/o `PLAN_MIGRACION.md` al inicio.

---

## Para retomar en chat nuevo

**Si vas a procesar más meses con lo que ya está:** no necesitás chat nuevo, este paquete es suficiente.

**Si vas a continuar la migración multi-empresa:**

1. Chat nuevo.
2. Subí: `silla_tres_entrega_final.zip` + `plataforma_contable_web_v2.zip`.
3. Mensaje inicial:

> *"Vengo a continuar la Fase X del PLAN_MIGRACION.md. El mini-paso del refactor de cuentas por empresa ya está completado (ver sección 6 del plan). Subo los archivos de referencia."*
