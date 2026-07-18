# Estructura de catálogos por defecto — INTEGRAL

Diseño para montar automáticamente en **toda compañía nueva**: PUC, terceros
(NITs), municipios, actividades económicas (CIIU) y calendario tributario.

## Principio: Global vs Plantilla

Se separa lo que es **único para todas las empresas** de lo que **cada empresa
tiene propio**:

### Nivel A — Catálogos GLOBALES (una sola copia; todas las empresas los leen)

| Catálogo | Tabla | Estado |
|---|---|---|
| Municipios DANE | `cn_municipios` (codigo_dane, nombre, departamento) | Se siembra (1.092) en migración **018** |
| Actividades económicas (CIIU) | vista `cn_actividades_ciiu` sobre `f350_catalogo_ciiu` | Reusa el catálogo CIIU existente |
| Calendario tributario | `cn_calendario_tributario` | Ya global (núcleo 014); datos 2025–2026 |
| Valores anuales (UVT/SMMLV/topes) | `cn_valores_anuales` | Ya global (núcleo 014); 2026 sembrado |
| Directorio de terceros (NITs) | `cn_directorio_terceros` (global) | Nuevo: autocompleta el nombre al digitar un NIT en cualquier empresa |

Estos **no se copian** por empresa: se consultan. "Montarlos por defecto" =
sembrarlos una vez.

### Nivel B — PLANTILLAS que se copian a cada empresa nueva

| Plantilla (global) | Se copia a (por empresa, RLS) |
|---|---|
| `cn_plan_cuentas_plantilla` (372 ctas PUC) | `cn_plan_cuentas` |
| `cn_comprobantes_plantilla` | `cn_comprobantes` |
| `cn_tipos_iva_plantilla` | `cn_tipos_iva` |
| `cn_tipos_retencion_plantilla` | `cn_tipos_retencion` |
| `cn_conceptos_plantilla` | `cn_conceptos` |
| `cn_terceros_base` (bancos, DIAN) | `cn_terceros` |

## Mecanismo de siembra

1. **Función** `public.cn_inicializar_empresa(p_empresa uuid)` (SECURITY DEFINER,
   idempotente con `ON CONFLICT DO NOTHING`): copia todas las plantillas a la
   empresa. Las secciones de 015/016 van protegidas: si aún no corriste esas
   migraciones, se omiten sin error.
2. **Trigger** `cn_after_insert_empresa AFTER INSERT ON empresas`: cada empresa
   nueva se inicializa sola. No hay que tocar el código de creación de empresas.
3. **Botón** en **🛡️ Panel Admin → 🌱 Inicializar catálogos**: para las empresas
   que ya existían antes de esta estructura (JIPER, CASA UNOTRES). Idempotente.

## Terceros / NITs (decisión: directorio global + base mínima)

- `cn_directorio_terceros`: directorio global (sembrado con los NITs reales del
  exógena + bancos). Sirve para **autocompletar** el nombre cuando se digita un
  NIT — en cualquier empresa. No se duplica por empresa.
- `cn_terceros_base`: set mínimo (bancos principales + DIAN) que **sí** se copia
  a cada empresa nueva, para tenerlos listos.
- Servicio `core/contable/inicializar.py` → `buscar_directorio(sb, nit)` y
  `listar_directorio(sb, query)` para el autocompletado (se puede enganchar en
  Captura/Maestros).

## Orden de aplicación en Supabase

1. (si faltan) 015_terceros.sql y 016_conceptos_iva_retencion.sql
2. **017_catalogos_plantilla_y_siembra.sql** ← plantillas + función + trigger + directorio
3. **018_municipios_global.sql** ← municipios DANE
4. En Panel Admin, pulsar **🌱 Inicializar** para JIPER y CASA UNOTRES (las de antes).

## Origen de los datos

PUC (372) y municipios (1.092) extraídos de las bases Btrieve de Contai
(`CNCTCIAL.btv`, `Cnmpios.btv`); directorio de terceros del Formato 1003 del
exógena; valores/calendario de los `.ini` de Contai. La `naturaleza` del PUC se
derivó de la clase (confiable); `maneja_nit`/tipo [C] se marcó en los grupos de
tercero (13, 22, 23, 2365/2367/2368, 2515…).
