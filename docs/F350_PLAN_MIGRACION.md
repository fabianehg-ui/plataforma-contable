# Plan de migración: BorradorFácil 350 → Plataforma web

Este documento describe cómo migrar el programa de escritorio
**BorradorFácil 350 v2.1.5** al módulo web "Retención en la Fuente"
de la plataforma multiempresa.

La migración se hace **por etapas** porque es un trabajo grande. Cada
sesión deja la plataforma estable y agrega funcionalidad incremental.

---

## Diseño general

### Modelo de datos (multiempresa)

```
public.empresas                  ← ya existe en tu plataforma
        │
        ├─ public.f350_empresa_config        (1:1)
        ├─ public.f350_terceros              (1:N)
        ├─ public.f350_historial_ciiu        (1:N)
        └─ public.f350_declaraciones         (1:N)
                    │
                    ├─ public.f350_movimientos_declaracion       (1:N)
                    └─ public.f350_subcuentas_autorretencion     (1:N)

public.f350_catalogo_ciiu        ← catálogo global compartido
public.f350_uvt_historico        ← catálogo global compartido
```

### Acceso
- **Habilitación por empresa:** se usa la tabla `modulos_empresa` existente.
- **Permisos:** RLS que valida `es_admin_de_empresa(empresa_id)` o
  `es_superadmin()` antes de leer/escribir cualquier dato.
- **Catálogos (CIIU, UVT):** lectura libre para autenticados,
  escritura solo súper admin.

### Carpetas en el repo

```
plataforma-contable/
├── app_pages/
│   └── 10_Retencion_Fuente.py           ← página principal (se sustituye en cada etapa)
├── core/
│   └── f350/                             ← lógica pura reutilizable
│       ├── __init__.py
│       ├── clasificador.py               ← clasificar_concepto_detallado()
│       ├── parser_contai.py              ← parsear_auxiliar(), parsear_balance()
│       ├── casillas.py                   ← mapeo de casillas F350
│       ├── autorretencion.py             ← cálculo sobre cuenta 4
│       └── pdf_f350.py                   ← generación del PDF estilo DIAN
├── db/
│   └── migrations/
│       └── 011_modulo_retencion_fuente_f350.sql   ← script creado en sesión 1
├── descargables/
│   └── borrador_facil_350/
│       └── BorradorFacil350_v2.1.5.zip   ← versión de escritorio
└── docs/
    └── F350_PLAN_MIGRACION.md             ← este archivo
```

---

## Sesión 1 — Preparar (HOY, ya hecho)

**Objetivo:** dejar todo armado para arrancar la migración con calma.

### Entregables
- ✅ Script SQL para crear las 8 tablas en Supabase con RLS
  (`011_modulo_retencion_fuente_f350.sql`).
- ✅ Página inicial `10_Retencion_Fuente.py` con descarga del .exe y
  aviso normativo.
- ✅ Versión de escritorio v2.1.5 (clasificador mejorado) lista para
  subir a `descargables/`.
- ✅ Este documento de plan.

### Tareas que debes hacer tú
1. **Subir el script SQL al repo** (carpeta `db/migrations/`).
2. **Ejecutar el script en Supabase** (SQL Editor → New query → pegar
   y Run). Verificar al final con la consulta de verificación.
3. **Subir el zip de BorradorFácil** a `descargables/borrador_facil_350/`.
4. **Subir la página inicial** a `app_pages/10_Retencion_Fuente.py`
   (reemplaza el archivo vacío que hay).
5. **Habilitar el módulo** a tus empresas-cliente desde
   Configuración → Módulos.

### Para verificar que la etapa quedó bien
- En Supabase, `SELECT table_name FROM information_schema.tables WHERE
  table_name LIKE 'f350_%'` devuelve 8 filas.
- Al entrar al módulo Retención en la Fuente, ves el aviso normativo y
  el botón de descarga.
- Tus clientes pueden descargar el `.zip` desde el navegador.

---

## Sesión 2 + 3 + 4 — Módulo completo (HECHO en una sola corrida, 16-may-2026)

Estas tres sesiones se combinaron en una sola entrega.

**Objetivo:** módulo F350 completamente funcional desde el web — catálogo,
configuración, parseo de PDFs, clasificación, autorretención, persistencia y
generación del PDF F350.

### Entregables hechos

#### Lógica pura — `core/f350/` (8 archivos)
- ✅ `__init__.py` — API pública del paquete.
- ✅ `nit_utils.py` — `inferir_tipo_persona`, `calcular_dv`, `formato_nit`,
  `formato_moneda`. Extraído del .exe sin cambios de lógica.
- ✅ `casillas.py` — `MAPEO_CASILLAS_F350`, `AUTORRET_CASILLAS_F350`,
  `CONCEPTOS_ORDEN_F350`, `obtener_casillas_f350`.
- ✅ `clasificador.py` — `REGLAS_CODIGO_PUC` (~30 prefijos PUC),
  `REGLAS_PATRON_COMBINADO` (~50 patrones), `REGLAS_PALABRA_CLAVE` (~20).
  Funciones `clasificar_concepto_detallado` y `clasificar_concepto_por_cuenta`.
- ✅ `parser_contai.py` — **adaptado para recibir bytes/file-like** (no solo
  rutas como el .exe). Helper `_abrir_pdf(fuente)` con `io.BytesIO`.
  Parsers de auxiliar y balance con los mismos regex del .exe v2.1.5.
- ✅ `autorretencion.py` — `calcular_autorretencion_cuenta_4`,
  `calcular_autorretencion_por_subcuentas` (permite excluir subcuentas),
  `aproximar_a_miles` (regla DIAN Art. 577 ET, usa Decimal/ROUND_HALF_UP).
- ✅ `pdf_f350.py` — **adaptado para devolver bytes** si `ruta=None`
  (necesario para `st.download_button`). Layout estilo DIAN con marca de
  agua "BORRADOR".
- ✅ `procesador.py` — **orquestador puro** `procesar_declaracion()` que
  combina parseo + clasificación + casillas + autorretención. No toca
  Supabase.

#### Capa de servicios — `core/f350/servicios.py`
- ✅ Catálogos: `listar_ciiu`, `obtener_tarifa_vigente` (vía RPC SQL),
  `obtener_uvt`.
- ✅ Configuración: `leer_config_empresa`, `guardar_config_empresa`,
  `registrar_cambio_ciiu`, `historial_ciiu`.
- ✅ Declaraciones: `listar_declaraciones`, `crear_declaracion`
  (idempotente vía UNIQUE empresa+anio+mes), `obtener_declaracion`,
  `actualizar_totales_declaracion`, `cambiar_estado_declaracion`,
  `eliminar_declaracion`.
- ✅ Movimientos: `guardar_movimientos` (borra+inserta en lotes de 500),
  `listar_movimientos`, `actualizar_movimiento`.
- ✅ Subcuentas: `guardar_subcuentas`, `listar_subcuentas`.

#### Migración SQL — `db/migrations/012_f350_catalogo_ciiu_tarifas.sql`
- ✅ Carga 50 CIIU más usados por PYMES colombianas con tarifas del
  **Dec. 0572/2025 marcadas como SUSPENDIDO** desde el 7-may-2026
  (`vigencia_hasta='2026-05-07'`).
- ✅ Duplica los mismos CIIU con `tarifa NULL` y `vigencia_desde='2026-05-08'`
  con normativa "Dec. 0261/2023 + 0242/2024 — Pendiente cargar tarifa
  oficial". La UI obliga a configurar tarifa manual hasta que se carguen.
- ✅ Función SQL `f350_tarifa_vigente(codigo, fecha)` con
  `GRANT EXECUTE TO authenticated`.

#### Página Streamlit — `app_pages/10_Retencion_Fuente.py` (reemplaza placeholder)
- ✅ 4 pestañas: **Declaraciones**, **Nueva declaración**, **Configuración**,
  **Catálogo CIIU**.
- ✅ Tab Declaraciones: listado completo con tabla, ver detalle
  (estado, totales, movimientos con confianza, cambio de estado),
  botón generar PDF con `st.download_button`, eliminación con
  confirmación.
- ✅ Tab Nueva declaración: selector año/mes, cálculo automático de
  tarifa (catálogo o manual), 2 file_uploaders, input subcuentas a
  excluir, vista previa de movimientos clasificados con confianza,
  botón guardar (idempotente).
- ✅ Tab Configuración: form con CIIU, autorretenedor, exonerado 114-1,
  tarifa manual, representante, email, notas. Registra cambios de
  CIIU en historial automáticamente. Muestra tabla de historial.
- ✅ Tab Catálogo CIIU: buscador con filtro por código o nombre.
- ✅ Sidebar: muestra CIIU configurado, flags de autorretenedor/exonerado
  y UVT del año actual.

#### Tests — `tests/test_f350.py`
- ✅ 25 tests cubriendo nit_utils, clasificador, casillas, autorretención
  y PDF (smoke test). Todos pasan en 0.09s.

### Decisión sobre tarifas vigentes
Las tarifas del Dec. 0261/2023 + 0242/2024 (vigentes desde 8-may-2026)
**no se cargaron automáticamente** porque no tengo el listado oficial
verificado. La migración 012 deja placeholders con tarifa NULL para que
la UI obligue al contador a configurar la tarifa manual por empresa
hasta que llegue el listado oficial.

Para cargarlas en el futuro: crear `013_f350_tarifas_dec_0261_2023.sql`
con UPDATEs sobre los registros que tienen `vigencia_desde='2026-05-08'`
y `tarifa_autorretencion IS NULL`.

### Tareas que debes hacer tú para activar todo
1. Subir todos los archivos al repo.
2. Aplicar `012_f350_catalogo_ciiu_tarifas.sql` en Supabase SQL Editor.
3. Reemplazar `app_pages/10_Retencion_Fuente.py` con la versión nueva.
4. Hacer commit y push — Railway redeplega automáticamente.
5. En la app: ir a Configuración → Módulos, habilitar "Retención en
   la Fuente" para tus empresas-cliente.
6. Probar con SILLA TRES marzo 2026 — verificar que los totales
   coinciden con los del .exe.

### Verificación de la sesión
- En Supabase: `SELECT COUNT(*) FROM f350_catalogo_ciiu` debe dar ~100
  filas (50 del 0572 + 50 placeholders 0261/0242).
- `SELECT f350_tarifa_vigente('5611', '2026-01-15')` → `0.0350`
  (vigente Dec. 0572).
- `SELECT f350_tarifa_vigente('5611', '2026-06-01')` → `NULL`
  (placeholder 0261 pendiente).
- En la web: la página F350 muestra 4 pestañas, el aviso normativo
  visible en expander, y se puede crear una empresa, configurarle CIIU,
  procesar un PDF y generar F350.

---

## Sesión 5 (opcional) — Pulir y exportar a Excel

**Objetivo:** mejorar UX y cubrir casos avanzados.

### Posibles mejoras
- Exportar movimientos a Excel.
- Reporte de varios meses (para conciliación anual).
- Edición masiva de terceros (importar listado de NITs con tipo PJ/PN).
- Vista de subcuentas de cuenta 4 con toggle para excluir/incluir cada
  una en el cálculo de autorretención.
- Lectura de cuentas a 6 dígitos sin guiones (mejora prometida).

---

## Reglas que vamos a respetar

1. **Cada sesión deja la plataforma estable.** Si en mitad de una
   sesión algo se rompe, podemos hacer rollback al estado previo.
2. **Lógica pura primero, UI después.** Las funciones de cálculo,
   parseo y clasificación van en `core/f350/` con pruebas. La UI las
   consume.
3. **No se inventan datos.** Si una tarifa no está confirmada en
   fuente oficial, se deja `NULL` y se pide al usuario que la
   configure manualmente.
4. **Cualquier función SQL nueva recibe `GRANT EXECUTE TO authenticated`**
   inmediatamente después de su creación. Lo aprendimos a las malas.

---

## Estimación de tiempo

| Sesión | Tu tiempo | Mi tiempo de generación |
|---|---|---|
| 1 (hoy) | 30 min (subir archivos + ejecutar SQL) | Ya hecho |
| 2 | 1-1.5 h | 1 h |
| 3 | 1-1.5 h | 1.5 h |
| 4 | 1 h | 1 h |
| 5 (opcional) | 1 h | 1 h |

Total: 4-5 horas tuyas distribuidas en 3-4 semanas si quieres ir sin
prisa.
