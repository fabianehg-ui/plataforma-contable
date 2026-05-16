# Despliegue del módulo F350 — Sesión 2+3+4 completa

**Fecha:** 16 de mayo de 2026
**Estado:** Módulo Retención en la Fuente completamente funcional.

Esta es la guía paso a paso para activar el módulo en producción.
**Léela completa antes de empezar** para que sepas qué esperar en cada paso.

---

## Lo que se entregó

| Tipo | Archivo | Acción |
|---|---|---|
| SQL | `db/migrations/012_f350_catalogo_ciiu_tarifas.sql` | **Aplicar en Supabase** + commit |
| Lógica pura | `core/f350/__init__.py` | Commit |
| Lógica pura | `core/f350/nit_utils.py` | Commit |
| Lógica pura | `core/f350/casillas.py` | Commit |
| Lógica pura | `core/f350/clasificador.py` | Commit |
| Lógica pura | `core/f350/parser_contai.py` | Commit |
| Lógica pura | `core/f350/autorretencion.py` | Commit |
| Lógica pura | `core/f350/pdf_f350.py` | Commit |
| Servicios | `core/f350/servicios.py` | Commit |
| Orquestador | `core/f350/procesador.py` | Commit |
| Tests | `tests/test_f350.py` | Commit |
| **Página** | `app_pages/10_Retencion_Fuente.py` | **Reemplaza el placeholder** + commit |
| Docs | `docs/F350_PLAN_MIGRACION.md` | Commit (actualizado) |

---

## Paso 1 — Aplicar la migración SQL en Supabase

1. Abre tu proyecto Supabase.
2. SQL Editor → **New query**.
3. Pega el contenido completo de `db/migrations/012_f350_catalogo_ciiu_tarifas.sql`.
4. Haz clic en **Run**.
5. Verifica que se aplicó:

```sql
SELECT COUNT(*) AS total,
       COUNT(tarifa_autorretencion) AS con_tarifa,
       COUNT(*) FILTER (WHERE tarifa_autorretencion IS NULL) AS sin_tarifa
FROM public.f350_catalogo_ciiu;
```

Esperado: aprox. **100 filas totales** — 50 con tarifa (Dec. 0572 hasta
7-may-2026) + 50 con NULL (Dec. 0261/0242 pendiente cargar).

Prueba la función auxiliar:

```sql
-- Tarifa vigente en enero 2026 para restaurantes (CIIU 5611)
SELECT public.f350_tarifa_vigente('5611', '2026-01-15');  -- → 0.0350

-- Tarifa vigente en junio 2026 (Dec. 0572 ya suspendido)
SELECT public.f350_tarifa_vigente('5611', '2026-06-01');  -- → NULL
```

---

## Paso 2 — Subir los archivos al repo y hacer push

Estructura final esperada:

```
plataforma-contable/
├── core/
│   └── f350/                          ← 8 archivos nuevos
│       ├── __init__.py
│       ├── nit_utils.py
│       ├── casillas.py
│       ├── clasificador.py
│       ├── parser_contai.py
│       ├── autorretencion.py
│       ├── pdf_f350.py
│       ├── servicios.py
│       └── procesador.py
├── db/migrations/
│   └── 012_f350_catalogo_ciiu_tarifas.sql    ← nuevo
├── app_pages/
│   └── 10_Retencion_Fuente.py         ← REEMPLAZA el placeholder de Sesión 1
├── tests/
│   └── test_f350.py                   ← nuevo
└── docs/
    └── F350_PLAN_MIGRACION.md         ← actualizado (S2+3+4 hechas)
```

**Commit sugerido:**

```bash
git add core/f350/ db/migrations/012_*.sql app_pages/10_Retencion_Fuente.py tests/test_f350.py docs/F350_PLAN_MIGRACION.md
git commit -m "feat(f350): módulo Retención en la Fuente completo

- Lógica pura en core/f350/ (NIT, casillas, clasificador, parser PDFs,
  autorretención, generación PDF)
- Capa de servicios Supabase y orquestador
- Migración 012 con catálogo CIIU (Dec. 0572/2025 marcado suspendido)
- Función SQL f350_tarifa_vigente con GRANT EXECUTE
- Página web con 4 pestañas: Declaraciones, Nueva, Config, Catálogo
- 25 tests pytest, todos pasando

Sesiones 2+3+4 del plan F350 completas."
git push
```

Railway redeplega automáticamente en ~2 minutos.

---

## Paso 3 — Habilitar el módulo a tus empresas-cliente

1. Entra a la app web ya desplegada.
2. Ve a **Configuración → Módulos** (sección admin).
3. Para cada empresa que quiera usar F350, habilita el módulo
   "Retención en la Fuente".

---

## Paso 4 — Configurar la primera empresa de prueba

Recomendación: empieza con SILLA TRES (la que ya conoces los totales).

1. En el sidebar, selecciona la empresa.
2. Ve a la página **Retención en la Fuente** (10).
3. Pestaña **Configuración**:
   - CIIU principal: el de la empresa (búscalo en la pestaña Catálogo CIIU).
   - Marca "¿Es autorretenedor especial?" si aplica.
   - Marca "¿Está exonerado del Art. 114-1?" si aplica.
   - **Tarifa manual:** como la migración 012 deja en NULL las tarifas
     desde 8-may-2026, para declaraciones de **mayo 2026 en adelante**
     deberás poner aquí la tarifa correcta del Dec. 0261/2023 + 0242/2024.
     Para declaraciones de **marzo o abril 2026**, la del catálogo
     (Dec. 0572) se aplicará automáticamente.
   - Guarda.

---

## Paso 5 — Probar una declaración de prueba

1. Pestaña **Nueva declaración**.
2. Selecciona año/mes (ej. 2026 / Marzo).
3. Sube los dos PDFs de Contai (auxiliar + balance).
4. Clic en **Procesar declaración**.
5. Revisa los movimientos clasificados.
6. Clic en **Guardar declaración**.
7. Ve a la pestaña **Declaraciones** y clic en **Generar PDF**.

### Resultados esperados para SILLA TRES marzo 2026
- 20 movimientos parseados.
- Total retenciones a terceros: **$12.388.012** (aproximado a miles).
- Autorretención (1,10% sobre cuenta 4): **$7.993.164**.
- Total declaración: **$20.381.176**.

Si los números difieren, probable causa:
- Tarifa diferente (verifica en la pestaña Configuración).
- Subcuentas excluidas necesarias (la 4295 de ingresos no operacionales
  por ejemplo).

---

## Paso 6 — Cargar las tarifas oficiales Dec. 0261/2023 cuando las tengas

Cuando consigas el listado oficial completo de tarifas del Dec. 0261/2023
+ 0242/2024 (PDF de la DIAN o normograma), crea una nueva migración:

```sql
-- db/migrations/013_f350_tarifas_dec_0261_2023.sql

UPDATE public.f350_catalogo_ciiu
   SET tarifa_autorretencion = 0.0110,
       normativa = 'Dec. 0261/2023 + 0242/2024 (vigente)'
 WHERE codigo = '5611'
   AND vigencia_desde = '2026-05-08'
   AND tarifa_autorretencion IS NULL;

-- (Repetir UPDATE por cada CIIU del listado oficial)
```

Aplícala en Supabase y la UI dejará de pedir tarifa manual para esos CIIU.

---

## Tests automatizados

Si quieres correr los tests localmente:

```bash
pip install pytest pdfplumber reportlab
cd /ruta/al/repo
python -m pytest tests/test_f350.py -v
```

Esperado: **25 passed**.

---

## Estructura del módulo (para referencia futura)

```
┌──────────────────────────────────────────────────────────────┐
│   app_pages/10_Retencion_Fuente.py  (UI Streamlit)           │
│                                                              │
│   Usa: core.f350.servicios   ← capa de datos                 │
│        core.f350.procesador  ← orquestador puro              │
│        core.f350.*           ← funciones de negocio puras    │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│   core/f350/                                                 │
│   ├── nit_utils.py       (NIT y formato)                     │
│   ├── casillas.py        (mapeo F350)                        │
│   ├── clasificador.py    (cuenta → concepto)                 │
│   ├── parser_contai.py   (PDFs → datos)                      │
│   ├── autorretencion.py  (cálculo cuenta 4)                  │
│   ├── pdf_f350.py        (datos → PDF)                       │
│   ├── procesador.py      (orquestador end-to-end)            │
│   └── servicios.py       (Supabase CRUD)                     │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│   Supabase tablas (creadas en migración 011 + 012)           │
│   ├── f350_catalogo_ciiu       (global, ~100 filas)          │
│   ├── f350_uvt_historico       (global, 7 años)              │
│   ├── f350_empresa_config      (1:1 con empresa)             │
│   ├── f350_historial_ciiu      (1:N por empresa)             │
│   ├── f350_declaraciones       (1:N por empresa)             │
│   ├── f350_movimientos_declaracion  (1:N por declaración)    │
│   └── f350_subcuentas_autorretencion (1:N por declaración)   │
└──────────────────────────────────────────────────────────────┘
```

---

## Cosas que NO se hicieron y se pueden hacer después

Estas son la "Sesión 5 opcional" del plan original:

- **Reclasificación manual de movimientos** desde la UI. Hoy se ve
  qué movimientos tienen confianza baja, pero para reasignarles
  concepto hay que actualizar a mano en la BD. Se puede agregar un
  popup en la tabla de Declaraciones.
- **Exportar a Excel** todos los movimientos de una declaración.
- **Reporte multi-mes** para conciliación anual.
- **Importación masiva de terceros** (lista de NITs con tipo PJ/PN
  predefinido).
- **Vista de subcuentas con toggle de inclusión** — hoy se pasan por
  texto separado por comas, podría ser una tabla con checkboxes.

---

## Problemas comunes y soluciones

### "Error procesando los PDFs"
- Verifica que los PDFs vienen de Contai con el formato exacto:
  - Auxiliar: "Análisis de % de Retención e IVA - Resumido".
  - Balance: "Balance de Prueba por Cuenta (Normal)".
- Otros reportes de Contai pueden tener un layout diferente y los
  regex no funcionan.

### "No hay tarifa vigente cargada para el CIIU X"
- Es lo esperado para declaraciones desde 8-may-2026 hasta que cargues
  el Dec. 0261/2023. Solución: configura la tarifa manual en la pestaña
  Configuración.

### El PDF no muestra valores
- Revisa que los movimientos sí se guardaron (ve a Detalle → ver
  movimientos). Si la tabla está vacía, hay que reprocesar.

### Los tests fallan por imports
- Asegúrate de correr `pytest` desde la raíz del repo, no desde `tests/`.

---

## ✅ Definición de Hecho

El módulo F350 está listo si:

- [x] La migración 012 está aplicada en Supabase.
- [x] Los 11 archivos están en el repo y Railway desplegó.
- [x] La página F350 muestra 4 pestañas sin errores.
- [x] Una empresa de prueba se puede configurar (CIIU, autorretenedor).
- [x] Se puede crear una declaración procesando 2 PDFs.
- [x] El PDF F350 se descarga correctamente.
- [x] `pytest tests/test_f350.py` pasa 25/25.

Cuando todo esto esté ✅, las Sesiones 2+3+4 están cerradas oficialmente.
