# Parche consolidado — JIPER (mayo 2026)

Este parche junta dos bloques de trabajo:

- **Bloque 1** (del turno anterior): terceros nuevos desde XMLs + propinas en POS
- **Bloque 2** (este turno): simplificación del menú + descargador XML unificado

## Cómo aplicarlo

Descomprime el ZIP encima del repo y commit. Los archivos NUEVOS se crean y los
existentes se reemplazan. NO se borra nada del repo — las páginas viejas siguen
en `app_pages/` pero ya no aparecen en el menú.

---

## Bloque 1 — Terceros desde XMLs y propinas POS

### 1.1 Descarga de terceros nuevos desde XMLs DIAN

- `core/procesadores/procesador_dian_xml.py` — `DocumentoDIAN` ahora extrae del
  emisor: `direccion`, `ciudad`, `codigo_ciudad` (DANE), `email`, `telefono`,
  `actividad_economica` (CIIU). Los campos van al final del dataclass para no
  romper la firma posicional.

- `core/procesadores/agregador_terceros_xml.py` (**NUEVO**)
  - `construir_maestro_desde_resultados(resultados)`: agrupa emisores únicos
    detectados en los XMLs. Cuando un NIT aparece varias veces, rellena
    campos vacíos del existente con info del documento nuevo (NO sobrescribe).
  - `detectar_nits_nuevos(maestro, historico, nits_extra)`: devuelve el set de
    NITs que NO están en el histórico de compras ni en `mapeo_nits.json` de la
    empresa.

- `core/procesadores/exportador_nits_siigo.py` — `construir_fila_siigo` ahora
  acepta `codigo_ciudad` directo del XML (más confiable que adivinar por nombre).

### 1.2 Propinas en plano POS

Fórmula del usuario, aplicada solo cuando hay INC > 0:
```
base_inc = INC / 0.08              (base teórica del impuesto al consumo)
propina  = Final - base_inc - INC
```

Asiento POS (4 líneas si hay propina, 3 si no):
```
Db CUENTA DE CAJA   = Final
Cr CTA BASE V       = base_inc       (= INC/0.08 si hay propina, si no = Neto)
Cr CTA ICO          = INC
Cr CTA PROPINAS     = propina        (solo si > $2)
```

Cuadre Db=Cr garantizado por construcción.

- Tolerancia: si propina ≤ 2 pesos, se trata como redondeo (asiento de 3 líneas).
- Sin INC: lógica clásica intacta.
- `cta_propinas` por sucursal (columna opcional `CTA PROPINAS` en DATOS PUNTO).
  Default global: `28150505` (PUC JIPER).
- CC propina = CC sucursal (como en el histórico real de JIPER).

---

## Bloque 2 — Simplificación + descargador unificado

### 2.1 `Home.py` simplificado

El menú visible se redujo a 2 módulos:

```
📊 Plataforma Contable
├── 🏠 Inicio
└── 🤖 Asistente Contable
    ├── 🧾 Ventas POS
    └── 📥 Descargador XML DIAN  (NUEVO)
```

Las páginas ocultas (no borradas) siguen en `app_pages/`:
Caja Menor, Compras DIAN, Token DIAN standalone, Nómina, Provisiones,
Ventas C13, PILA, DIAN XML (5a — ya integrado al nuevo), Configuración,
Panel Admin, RADIAN, Exógena, Renta, IVA, Retención, Saludables.

Para reactivar alguna: agregarla a la sección `🤖 Asistente Contable` en
`Home.py` (líneas 138-152).

### 2.2 Nueva página `5b_Descargador_XML.py`

Flujo de 4 pasos:

```
1️⃣  Subir Excel del Token DIAN
    → detecta automáticamente fechas, tipos y prefijos disponibles

2️⃣  Elegir qué descargar
    📥 RECIBIDOS                    📤 EMITIDOS
    Checkboxes por tipo:            Multiselect de prefijos:
    ☑ Factura electronica           [STL ⊠] [DSE ⊠] [VIV ☐] [IND ☐]
    ☑ Nota credito                  (sugerido: STL + DSE)
    ☑ Documento Soporte
    ☐ Application response (off)
    ☐ Nomina Individual (off)

3️⃣  Pegar Token URL → ⬇️ Descargar
    Descarga paralela en bloques de 500 con barra de progreso

4️⃣  Procesar XMLs
    → Plano contable por empresa (TXT/CSV/Excel)
    → Plano de TERCEROS NUEVOS para Siigo (20 columnas)
```

**Decisiones de diseño:**
- Usa el Excel del Token como **referencia**: de ahí salen los CUFEs.
- Application response y Nomina Individual están **OFF por default**
  (no son contables).
- Para emitidos los prefijos **STL** y **DSE** vienen sugeridos por default
  (lo más usado históricamente en JIPER).
- El procesamiento es post-descarga, no se hace automático al final de la
  descarga para que el usuario revise el dictamen antes.

---

## Archivos modificados

```
Home.py                                             (REESCRITO)
app_pages/4b_Ingresos_POS.py                        (sin cambios — sigue activo)
app_pages/5b_Descargador_XML.py                     (NUEVO)
app_pages/5a_DIAN_XML.py                            (modificado — queda oculto)
core/data/datos_punto.json                          (modificado — +cta_propinas)
core/procesadores/procesador_dian_xml.py            (modificado — campos extendidos emisor)
core/procesadores/procesador_pos.py                 (modificado — lógica propinas)
core/procesadores/exportador_nits_siigo.py          (modificado — codigo_ciudad)
core/procesadores/agregador_terceros_xml.py         (NUEVO)
datos_punto.json                                    (modificado — +cta_propinas)
tests/test_pos_propinas.py                          (NUEVO — 6 tests)
tests/test_agregador_terceros_xml.py                (NUEVO — 7 tests)
tests/test_filtros_descargador.py                   (NUEVO — 7 tests)
```

## Tests

Total: **38 tests nuevos** (todos pasan), 0 regresiones.

- `test_pos_propinas.py` — 6 tests: sin propina, con propina, tolerancia,
  sin INC, múltiples sucursales/días, CC correcto.
- `test_agregador_terceros_xml.py` — 7 tests del agregador y detector de NITs nuevos.
- `test_filtros_descargador.py` — 7 tests del paso 2 (detección de tipos,
  prefijos, defaults, consolidado).

Los 18 tests preexistentes (`test_pos_token.py`) siguen pasando.

## Notas de seguridad / migración

1. **Las páginas ocultas no se borraron**: si necesitas reactivar una, edita
   `Home.py` y agrega su `st.Page` al diccionario de navegación.
2. **El flujo viejo de Token DIAN sigue accesible vía URL directa**:
   `/procesar-token-dian` aunque no aparezca en el sidebar (las páginas
   registradas en Streamlit siguen siendo navegables por URL si conoces el path).
   Si quieres bloquear acceso directo también, comenta los st.Page de las
   páginas ocultas — pero eso podría romper sesiones activas.
3. **Los tests preexistentes de exógena fallan** (`test_conciliacion_enriquecida`,
   `test_editor_reglas`) pero esos fallos son anteriores a este parche
   (verificado contra el repo base sin tocar). No es regresión.
