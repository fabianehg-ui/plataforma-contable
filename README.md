# Plataforma Contable Web

Versión web de la aplicación Generador de Plano Contable.
**Multi-empresa, multi-usuario**, con login seguro.

> **Última actualización:** 1 de mayo de 2026
> Incluye: módulo DIAN XML completo con descargador desde portal, motor de mapeo v0.3, refactor multi-empresa del puente motor.

---

## 🧱 Arquitectura

- **Frontend + Backend:** Streamlit (Python)
- **Autenticación:** Supabase Auth (email + contraseña)
- **Base de datos:** Supabase PostgreSQL con Row Level Security
- **Almacenamiento de archivos:** Supabase Storage (bucket `empresas-config` planeado)
- **Hosting:** Railway (recomendado) o Render

---

## 📂 Estructura

```
plataforma_web/
├── Home.py                     # Página de bienvenida (post-login)
├── pages/
│   ├── 1_💵_Caja_Menor.py      # ✅ Funcional
│   ├── 2_🛒_Compras_DIAN.py    # ⏳ Placeholder (legacy del .exe)
│   ├── 3_💼_Nómina.py          # ⏳ Placeholder
│   ├── 4_📝_Provisiones.py     # ⏳ Placeholder
│   ├── 5_📎_PILA.py            # ✅ Funcional
│   ├── 5_📥_DIAN_XML.py        # ✅ Funcional (NUEVO 1-may-2026)
│   └── 6_⚙️_Configuración.py    # 🟡 Tabs en desarrollo
│
├── core/
│   ├── procesadores/
│   │   ├── procesador_caja_menor.py
│   │   ├── procesador_dian_xml.py        # Procesador legacy de XMLs DIAN
│   │   ├── motor_mapeo_v03.py            # Motor de mapeo NIT con aprendizaje BP
│   │   └── puente_motor_v03.py           # ✨ Multi-empresa (refactor 1-may-2026)
│   ├── lectores/
│   │   └── lector_pila.py
│   ├── utils/
│   │   └── configuracion_web.py          # Lee Excel desde bytes (Supabase Storage)
│   └── data/
│       └── empresas/
│           └── 900451388_silla_tres/
│               ├── empresa.json
│               └── mapeo_nits.json       # Catálogo aprendido + reglas manuales
│
├── auth/
│   ├── login.py                # require_auth, login_form, sidebar_user_info
│   └── empresas.py             # require_empresa, require_rol, seleccionar_empresa_sidebar
│
├── db/
│   ├── supabase_client.py      # Cliente único de Supabase (anon + service_role)
│   └── schema.sql              # Esquema completo: empresas, usuario_empresa, RLS
│
├── herramientas/
│   ├── dian_descargador_v03.js          # JS fuente del bookmarklet DIAN
│   ├── dian_descargador_v03_INLINE.txt  # Versión inline para pegar al marcador
│   └── generar_bookmarklet.py           # Generador con tokenizer
│
├── data/
│   ├── cuentas.xlsx            # PUC de referencia (a migrar a Storage)
│   └── mapeos.xlsx             # Reglas de mapeo (a migrar a Storage)
│
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
│
├── requirements.txt
├── Procfile
├── runtime.txt
├── .gitignore
├── DEPLOY.md
├── PLAN_MIGRACION.md           # Plan de 5 fases para multi-empresa real
└── README.md                   # (este archivo)
```

---

## 🚀 Instalación rápida (local)

```bash
# 1. Clonar
git clone <tu-repo>
cd plataforma_web

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate         # Linux/Mac
# venv\Scripts\activate          # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Editar secrets.toml con credenciales de Supabase

# 5. Arrancar
streamlit run Home.py
```

---

## 🌐 Despliegue en la web

Ver **DEPLOY.md** para la guía completa paso a paso.

Resumen:
1. Crear cuenta en Supabase (gratis) y ejecutar `db/schema.sql` en el SQL Editor.
2. Crear cuenta en Railway y conectar el repo de GitHub.
3. Configurar variables de entorno (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`).
4. (Opcional) Conectar dominio propio.

**Costo aproximado:** $0–10 USD/mes.

---

## 📦 Módulos

| Módulo | Estado | Descripción |
|---|---|---|
| **Caja Menor** | ✅ Funcional | Sube Excel de egresos → genera plano contable |
| **PILA** | ✅ Funcional | Sube PDF de planilla → extrae empleados y totales, descarga Excel |
| **DIAN XML** | ✅ Funcional | Sube ZIP con XMLs descargados desde portal DIAN → procesa retenciones, mapea cuentas según PUC de empresa, genera plano |
| Compras DIAN (Excel) | ⏳ Placeholder | Versión legacy basada en Excel del portal DIAN; puede deprecarse a favor de DIAN XML |
| Nómina | ⏳ Pendiente | Placeholder listo |
| Provisiones | ⏳ Pendiente | Placeholder listo |

Cada módulo se migra copiando el procesador del `.exe` original a `core/procesadores/` y creando una página en `pages/` que sigue el patrón:

```python
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_empresa()
# require_rol(['admin', 'operador'])    # opcional
```

---

## 🆕 Módulo DIAN XML (destacado)

Procesa facturas electrónicas descargadas directamente del portal DIAN como XMLs UBL 2.1, sin pasar por el Excel intermedio.

**Flujo:**

1. **Descargar XMLs**: usar el bookmarklet `dian_descargador_v03_INLINE.txt` desde el portal DIAN. Filtra por **fecha de emisión** y descarga un único ZIP con todos los XMLs del rango.
2. **Subir el ZIP** a la página `📥 DIAN XML`.
3. Configurar año, mes, los **3 consecutivos iniciales** (Compras=3, ND=7, NC=12) y la empresa activa.
4. **Procesar**: el sistema clasifica cada factura, calcula retenciones según el motor de mapeo v0.3 (aprendizaje desde BP), aplica retefuente/reteIVA según concepto, ordena por fecha de emisión y genera el plano contable.

**Características técnicas:**

- Motor de mapeo v0.3 con aprendizaje automático del Balance de Prueba.
- Catálogo de NITs editable (`mapeo_nits.json`) con confianza por proveedor.
- Detección automática de tipo de retención (compras 2.5%, servicios 4%/2%, honorarios 11%, fletes 1%, software 3.5%, arrendamiento 3.5%, regalías 2.5%).
- Enrutamiento contextual de impuestos al consumo: telefonía → cuenta de gasto telefónico, otros gastos → cuenta de gasto general, con inventario → cuenta de inventario saludable.
- IBUA, ICUI e impuestos saludables al inventario.
- Reverso correcto de retenciones en notas crédito.
- Soporte multi-empresa via dict `CONFIGS_POR_NIT` en `puente_motor_v03.py` (ver sección Multi-empresa).

---

## 🏢 Multi-empresa

La plataforma está diseñada para múltiples empresas con permisos por usuario.

### Lo que YA funciona

- Tablas `empresas` y `usuario_empresa` con relación N:N y roles (`admin`, `operador`, `consulta`).
- Row Level Security (RLS) en todas las tablas: cada usuario solo ve datos de empresas a las que pertenece.
- Selector de empresa activa en el sidebar.
- Función SQL `crear_empresa_con_admin(nit, razon_social)` que asigna automáticamente al creador como admin.
- Procesador DIAN con configuración por empresa: `puente_motor_v03.py` busca el config en `CONFIGS_POR_NIT` según el NIT.

### Para agregar una empresa nueva

1. **En Supabase**: ejecutar `select crear_empresa_con_admin('900XXXXXX', 'NOMBRE DE LA EMPRESA');`
2. **En `puente_motor_v03.py`**: agregar el config de cuentas de la empresa al dict `CONFIGS_POR_NIT`:

```python
CONFIG_EMPRESA_NUEVA = {
    "_descripcion": "EMPRESA NUEVA — NIT 800999999",
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

3. **Crear carpeta** `core/data/empresas/<NIT>_<slug>/` con `empresa.json` y `mapeo_nits.json` de la nueva empresa.

> **Próximamente (Fase 2):** los configs y archivos `mapeo_nits.json` vivirán en Supabase Storage en lugar del filesystem, y la UI permitirá agregar empresas sin tocar código.

### Lo que falta para multi-empresa real

Ver **PLAN_MIGRACION.md** para el detalle. Resumen de fases:

| Fase | Qué entrega | Estado |
|---|---|---|
| **F1** | DIAN integrado a la plataforma con `empresa_activa()` | 🟡 Mini-paso completado, falta integración Streamlit |
| **F2** | Configs por empresa en Supabase Storage (no filesystem) | ⏳ Pendiente |
| **F3** | UI para que admin suba archivos de configuración | ⏳ Pendiente |
| **F4** | Permisos de módulo por empresa y por usuario | ⏳ Pendiente |
| **F5** | UI para invitar usuarios y asignar permisos | ⏳ Pendiente |

---

## 🛠️ Herramientas auxiliares

### Bookmarklet DIAN (`herramientas/`)

JavaScript que se pega como marcador del navegador y permite descargar todos los XMLs de un rango de fechas desde el portal DIAN como un único ZIP.

**Características:**

- Filtro por fecha de emisión real (no por fecha de recepción DIAN).
- Filtrado client-side redundante: descarta XMLs con fecha fuera del rango pedido.
- Panel flotante con progreso, log y conteo de descartados.
- Genera el ZIP completo en memoria y lo descarga al final.

**Uso:**

1. Abrir `herramientas/dian_descargador_v03_INLINE.txt`.
2. Copiar todo el contenido.
3. En el navegador: Ctrl+Shift+O → crear marcador nuevo → pegar en el campo URL.
4. Ir al portal DIAN, sección "Documentos electrónicos recibidos".
5. Click en el marcador → aparece el panel flotante.
6. Configurar fecha desde / hasta → "Iniciar descarga".

**Para regenerar** (si editás el `.js`):

```bash
python herramientas/generar_bookmarklet.py
# Genera dian_descargador_v03_INLINE.txt actualizado
```

---

## 📝 Comprobantes contables

| Código | Tipo | Uso |
|---|---|---|
| `1` | Factura electrónica (FE) | Compras |
| `2` | Comprobante de egreso (CE) | Pagos |
| `3` | Compras | DIAN XML — facturas |
| `5` | Nota crédito (NC) genérica | |
| `7` | Nota débito (ND) | DIAN XML — débitos |
| `8` | Nómina (NOM) | |
| `9` | Provisiones (PROV) | |
| `12` | Nota crédito DIAN (NC) | DIAN XML — créditos |
| `13` | Caja Menor (CM) | |
| `DS` | Documento soporte | Doc soporte de adquisiciones |

Cada empresa puede personalizar estos códigos en su `empresa.json` (clave `comprobantes`).

---

## 🔐 Roles y permisos (estado actual)

| Rol | Puede |
|---|---|
| **admin** | Todo: ver, procesar, configurar, gestionar usuarios |
| **operador** | Ver y procesar (no configura ni gestiona usuarios) |
| **consulta** | Solo lectura |

> **Próximamente (Fase 4):** permisos granulares por módulo (un usuario puede tener acceso a DIAN XML pero no a Nómina).

---

## 🐛 Reporte de problemas

Template para reportar errores:

```
Acción: [qué intentaste]
Esperado: [qué pensabas que pasaría]
Ocurrió: [qué pasó realmente]
Mensaje de error: [pegar mensaje completo]
Archivo / página: [dónde]
Empresa: [NIT]
```

---

## 📚 Documentación adicional

- **DEPLOY.md** — guía de despliegue paso a paso en Railway.
- **PLAN_MIGRACION.md** — plan de 5 fases para multi-empresa real.
- **db/schema.sql** — esquema completo de la base de datos (con comentarios).

---

## 📜 Changelog

### 1 de mayo de 2026

**Sesión técnica completa de DIAN XML y refactor multi-empresa.**

- ✨ **Nuevo módulo DIAN XML** (`pages/5_📥_DIAN_XML.py`): procesamiento de facturas electrónicas DIAN como XMLs UBL.
- ✨ **Bookmarklet de descarga** desde portal DIAN con filtrado por fecha de emisión y filtrado client-side.
- ✨ **Refactor multi-empresa de `puente_motor_v03.py`**: nueva función `remapear_cuentas_por_empresa()` y dict `CONFIGS_POR_NIT` para soportar múltiples empresas. Función vieja mantenida como alias deprecado.
- 🐛 **Corregido bookmarklet**: `FilterType` cambió de `'3'` (recepción) a `'1'` (emisión).
- 🐛 **Corregido `mapeo_nits.json`**: Atocha y San Ignacio estaban en cuenta `13300501` por bug del aprendizaje BP.
- 🐛 **Corregidas cuentas IVA descontable** según BP de Silla Tres marzo 2026.
- ✨ **Plano ordenado** por fecha de emisión ascendente con renumeración de consecutivos.
- ✨ **3 campos de consecutivo inicial** (Compras, ND, NC) en lugar de uno solo.
- ✨ **Enrutamiento contextual** de impuestos al consumo (telefonía vs gasto general vs inventario).
- ✨ **PLAN_MIGRACION.md** documentando las 5 fases para multi-empresa real.

### Versiones anteriores

Ver historial de Git.
