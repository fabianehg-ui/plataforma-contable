# CÓMO SUBIR — Estructura de catálogos por defecto (INTEGRAL)

Monta PUC, terceros, municipios, CIIU y calendario por defecto en toda empresa.
Fecha: 18-jul-2026.

## 1. Correr en Supabase (SQL Editor → pegar → Run, en orden)

1. Si aún no lo hiciste: `015_terceros.sql` y `016_conceptos_iva_retencion.sql`.
2. **`db/migrations/017_catalogos_plantilla_y_siembra.sql`** — crea las plantillas
   (PUC 372 ctas, comprobantes, tipos IVA/retención, conceptos, terceros base),
   el **directorio global de terceros**, la función `cn_inicializar_empresa()` y
   el **trigger** que siembra cada empresa nueva. Idempotente.
3. **`db/migrations/018_municipios_global.sql`** — siembra 1.092 municipios DANE.

## 2. Archivos de código

| Archivo | Estado | Qué hace |
|---|---|---|
| `db/migrations/017_...sql` | **NUEVO** | Plantillas + directorio + función + trigger. |
| `db/migrations/018_...sql` | **NUEVO** | Municipios DANE globales. |
| `core/contable/inicializar.py` | **NUEVO** | `inicializar_empresa(sb,id)`, `buscar_directorio(sb,nit)`, `listar_directorio`. |
| `app_pages/0_Panel_Admin.py` | **MOD** | Sección **🌱 Inicializar catálogos** por empresa. |

## 3. Inicializar las empresas existentes

En **🛡️ Panel Admin → 🌱 Inicializar catálogos por defecto**, elige JIPER y
CASA UNOTRES y pulsa **Inicializar** (las creadas antes del trigger). Idempotente.

## Resultado

- Toda **empresa nueva** nace con PUC, comprobantes, conceptos y terceros base
  (por el trigger).
- **Municipios, CIIU, calendario y valores anuales** son globales: se consultan.
- Al digitar un **NIT** conocido, `cn_directorio_terceros` permite autocompletar
  el nombre (servicio listo; se puede enganchar en la UI de Captura/Maestros).

## Notas

- La función está protegida: si 015/016 no están aplicadas, omite esas secciones
  sin fallar; corre esas migraciones y vuelve a inicializar para completarlas.
- Ver `ESTRUCTURA_CATALOGOS.md` para el diseño completo (global vs plantilla).
