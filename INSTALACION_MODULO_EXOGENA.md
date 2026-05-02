# Integración del Módulo Exógena al Repo Existente

Este paquete contiene **solo los archivos nuevos o modificados** para integrar el módulo
de Información Exógena DIAN a tu repo `plataforma_reorganizada_fase1_v2`.

Estructura adaptada para encajar exactamente con las convenciones del repo:
- `app/tributarias/exogena.py` reemplaza el placeholder existente
- Lógica del motor en `core/exogena/` (paquete nuevo)
- SQL en `db/migrations/` (subdirectorio nuevo, recomiendo crearlo)
- XSDs incluidos en `core/exogena/xsd/`
- Tests en `tests/exogena/` (carpeta nueva)
- `requirements.txt` agrega `requests`

---

## 📋 Cambios respecto al repo existente

### Archivos nuevos
```
core/exogena/
├── __init__.py
├── clasificador_nits.py
├── cargador_terceros.py
├── cargador_codificacion_nativa.py
├── motor_clasificacion.py
├── validador_xsd.py
├── enriquecimiento/
│   ├── __init__.py
│   ├── base.py
│   ├── apitude.py        ← API paga (esqueleto, requiere credenciales)
│   └── rues.py           ← API gratuita REAL (Confecámaras)
└── xsd/
    ├── 1001.xsd
    └── ... (15 archivos)

db/migrations/
├── 001_exogena_schema.sql              ← tablas del módulo
├── 002_exogena_datos_catalogos_AG2025.sql
└── 003_exogena_datos_puc_AG2025.sql

tests/exogena/
├── test_validador_xsd.py
├── test_motor_clasificacion.py
└── test_enriquecimiento.py

data/exogena/referencia/
└── catalogos_dian.json    ← referencia offline de catálogos DIAN
```

### Archivos modificados
```
app/tributarias/exogena.py    ← reemplaza el placeholder con módulo funcional
requirements.txt               ← agrega 'requests>=2.31.0'
```

---

## 🚀 Pasos de despliegue

### 1. Mergear archivos al repo

Desde la raíz del repo `plataforma_web/`:

```bash
# Copiar el contenido de este paquete
cp -r plataforma_web/core/exogena/        core/
cp -r plataforma_web/db/migrations/       db/
cp -r plataforma_web/tests/               .   # crea tests/ si no existe
cp -r plataforma_web/data/exogena/        data/
cp plataforma_web/app/tributarias/exogena.py  app/tributarias/
cp plataforma_web/requirements.txt        .
```

### 2. Ejecutar migraciones SQL en Supabase

En el SQL Editor de Supabase, en este orden estricto:

```
1. db/migrations/001_exogena_schema.sql              (crea 11 tablas + RLS)
2. db/migrations/002_exogena_datos_catalogos_AG2025.sql  (~2.850 INSERTs)
3. db/migrations/003_exogena_datos_puc_AG2025.sql    (669 cuentas del PUC)
```

> **Importante:** las tablas usan `empresa_id uuid` consistente con `public.empresas(id)` del schema base. Las políticas RLS reusan tu tabla `usuario_empresa` para verificar membresía.

### 3. Actualizar dependencias

```bash
pip install -r requirements.txt
```

Localmente para probar:
```bash
streamlit run Home.py
```

### 4. (Opcional) Configurar API paga Apitude

Si más adelante decides contratar Apitude para enriquecer datos no cubiertos por RUES, agregar a `.streamlit/secrets.toml` o variables de entorno de Railway:

```toml
APITUDE_API_KEY = "tu_clave"
```

El módulo lee `os.getenv("APITUDE_API_KEY")` y solo activa el botón de Apitude si la variable existe.

---

## 🎯 Estrategia de enriquecimiento (como pediste: maximizar gratis)

El módulo prioriza fuentes gratuitas en cascada:

```
┌──────────────────────────────────────────────────────────────┐
│ 1. CACHE en BD propia        Gratis   instantáneo            │
│    └─ TTL 90 días                                            │
└──────────────────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────────┐
│ 2. RUES Confecámaras         GRATIS   ~2 seg                 │
│    └─ Razón social, estado matrícula, cámara                 │
│    └─ Solo jurídicas y comerciantes registrados              │
│    └─ Endpoint: elasticprd.rues.org.co (público)             │
│    └─ Base legal: Ley 1727 de 2014 + Ley 1581 art. 3        │
└──────────────────────────────────────────────────────────────┘
                       ↓ (opcional, requiere credenciales)
┌──────────────────────────────────────────────────────────────┐
│ 3. APITUDE (API DIAN RUT)    PAGO     ~3 seg                 │
│    └─ Datos completos: dirección, email, CIIU                │
│    └─ Cubre naturales y jurídicas                            │
└──────────────────────────────────────────────────────────────┘
```

**RUES es el que aporta valor gratuito real:**
- Para los **2.063 terceros jurídicos** de Rutas del Mar, RUES debería resolver la mayoría
- Devuelve: razón social, organización jurídica (SAS, LTDA, etc.), estado de matrícula, cámara de comercio
- No devuelve: dirección, email, teléfono, representante legal (eso requiere certificado pago o Apitude)

**Para personas naturales** RUES no aplica salvo que estén registradas como comerciantes. Para ellas, los datos quedan como vienen del balance + clasificación por rangos.

---

## 🧪 Verificación post-instalación

Tests de humo:

```bash
# Desde la raíz del repo
PYTHONPATH=. python tests/exogena/test_validador_xsd.py
PYTHONPATH=. python tests/exogena/test_enriquecimiento.py
PYTHONPATH=. python tests/exogena/test_motor_clasificacion.py
```

Todos deberían imprimir `✅ Todos los tests pasaron`.

Test funcional manual:

1. Ingresar a la plataforma con tu usuario.
2. Seleccionar empresa **Rutas del Mar** (o crearla si aún no existe).
3. Ir a **Herramientas Tributarias → Información Exógena**.
4. **Tab "Mapeo nativo"**: subir el archivo `Codificación_Formatos__Dic-31-2025.xlsx`. Debería detectar 124 reglas en 7 formatos (1001, 1003, 1007, 1008, 1009, 1011, 1012). Click en "Guardar".
5. **Tab "Terceros" → "Cargar maestro"**: subir el Excel de NITs. Debería clasificar 2.300 naturales / 2.063 jurídicas. Click "Cargar a BD".
6. **Tab "Terceros" → "Enriquecer (RUES)"**: marcar "✅ Usar RUES", seleccionar "Solo jurídicas", click "Enriquecer". Debería completar nombres y estado de matrícula.

---

## ⏭️ Lo que sigue (fases siguientes en el mismo módulo)

Los tabs **Balance**, **Clasificar**, **Generar XML** y **Envíos** están como placeholders elegantes (`render_proximamente`). Cuando estés listo:

1. **Tab Balance** — parser del balance auxiliar y carga a `exogena_balance`.
2. **Tab Clasificar** — invocación del motor (que ya existe en `motor_clasificacion.py`) y UI de revisión de ambigüedades.
3. **Tab Generar XML** — builder de los XML usando los XSDs como esquema, con validación previa.
4. **Tab Envíos** — histórico de archivos generados con descarga ZIP.

Toda la infraestructura (BD, motor, validador, enriquecimiento) ya está lista. Faltan solo las páginas Streamlit que las orquestan.

---

## 📊 Estadísticas

| Pieza | Cantidad |
|---|---:|
| Migraciones SQL | 3 |
| Módulos Python | 6 (clasificador, cargador terceros, cargador codificación, motor, validador, enriquecimiento) |
| Implementaciones de enriquecimiento | 5 (stub, cascada, caché, RUES real, Apitude esqueleto) |
| XSDs validables | 15 |
| Tests pasando | 16 |
| Validación con datos reales (Rutas del Mar) | 86% movimientos auto-clasificados |

---

## 🛡️ Notas de seguridad

- Todas las tablas tienen RLS habilitado y reusan tu tabla `usuario_empresa` para verificar membresía.
- Los catálogos DIAN y el PUC genérico son lectura pública para usuarios autenticados (no hay PII).
- El caché de enriquecimiento es lectura/escritura para autenticados (los datos son públicos por ley).
- Las tablas con `empresa_id` solo permiten acceso a miembros de esa empresa.
- Las tablas con `periodo_id` validan a través del periodo.
