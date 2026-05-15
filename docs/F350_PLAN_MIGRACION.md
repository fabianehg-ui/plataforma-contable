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

## Sesión 2 — Catálogos y configuración por empresa

**Objetivo:** poder configurar empresas-cliente para el F350 desde el web.

### Entregables a crear
1. **Tarifas de autorretención vigentes** (Dec. 0261/2023 + 0242/2024)
   cargadas en `f350_catalogo_ciiu` con `vigencia_desde='2026-05-08'`.
2. **Lógica pura** extraída a `core/f350/`:
   - `clasificador.py` (mover desde el .exe, ya está mejorado en v2.1.5)
   - `casillas.py` (mapeo F350)
3. **Nueva página `10_Retencion_Fuente.py`** con:
   - Selección de empresa (filtrada por permisos del usuario)
   - Sección "Configuración F350" — CIIU, autorretenedor, exonerado
     114-1
   - Lectura/escritura en `f350_empresa_config`
   - Historial de cambios de CIIU
4. **Catálogo CIIU visible** desde la página (para que el contador
   pueda buscar el código por nombre de actividad).

### Tareas que debes hacer tú (cuando arranquemos)
1. Pasarme el listado oficial de tarifas vigentes Dec. 0261/2023 +
   0242/2024 (o me lo busco en fuentes oficiales).
2. Aplicar el script SQL de carga de tarifas.
3. Probar configurar una empresa de prueba.

---

## Sesión 3 — Carga de PDFs y procesamiento

**Objetivo:** poder cargar los PDFs de Contai por web y ver el resultado
del procesamiento.

### Entregables
1. **`core/f350/parser_contai.py`** — funciones para leer auxiliar y
   balance desde bytes (no desde archivo, porque Streamlit recibe el
   PDF como upload).
2. **`core/f350/autorretencion.py`** — cálculo sobre cuenta 4 con
   selección automática de tarifa según fecha de la declaración.
3. **Nueva página `10_Retencion_Fuente.py`** con:
   - Lista de declaraciones existentes (filtrada por empresa)
   - Botón "Nueva declaración" → selección de mes/año
   - Subida de PDFs (`st.file_uploader`)
   - Vista previa de movimientos clasificados
   - Botón "Procesar y guardar"
   - Guarda en `f350_declaraciones` y `f350_movimientos_declaracion`

### Verificación
- Subir los PDFs de marzo 2026 de SILLA TRES.
- Comparar contra los totales conocidos:
  - Retenciones a terceros (20 movs): $12.388.012
  - Autorretención 1.1% sobre cuenta 4: $7.993.164
  - Total: $20.381.176

---

## Sesión 4 — Generación del F350 y revisión

**Objetivo:** generar el PDF del F350 y permitir revisión visual.

### Entregables
1. **`core/f350/pdf_f350.py`** — generador del PDF estilo DIAN con
   marca de agua.
2. **Página `10_Retencion_Fuente.py`** con:
   - Ficha de Diligenciamiento con valores por casilla y botones
     "Copiar" al lado de cada uno.
   - Pestaña "Movimientos" con filtro por estado y confianza
     (resaltar los de confianza media/baja en color).
   - Posibilidad de reclasificar manualmente un movimiento.
   - Botón "📄 Generar PDF F350" → descarga del PDF.
   - Botón "Marcar como presentada" → cambia estado a 'Presentada'.

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
