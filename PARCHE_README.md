# Parche consolidado — JIPER (mayo 2026)

Este parche junta:

- **Bloque 1**: terceros nuevos desde XMLs + propinas en POS
- **Bloque 2**: nueva página unificada Descargador XML DIAN

⚠️ El menú principal (`Home.py`) NO se simplifica. Todas las herramientas
existentes siguen visibles (Caja Menor, Token DIAN, Nómina, Provisiones,
Ventas C13, PILA, RADIAN, Exógena, Renta, IVA, Retención, Saludables,
Panel Admin, Configuración). Solo se AGREGA un nuevo ítem en "Asistente
Contable": **📥 Descargador XML DIAN**.

## Cómo aplicar

Descomprime el ZIP encima del repo y commit. Reemplaza los archivos
existentes (sin borrar ninguno) y agrega los archivos nuevos.

---

## Bloque 1 — Terceros desde XMLs y propinas POS

### 1.1 Descarga de terceros nuevos desde XMLs DIAN

- `core/procesadores/procesador_dian_xml.py` — `DocumentoDIAN` ahora extrae del
  emisor: `direccion`, `ciudad`, `codigo_ciudad` (DANE), `email`, `telefono`,
  `actividad_economica` (CIIU). Los campos van al final del dataclass para no
  romper la firma posicional.

- `core/procesadores/agregador_terceros_xml.py` (**NUEVO**)
  - `construir_maestro_desde_resultados(resultados)`: agrupa emisores únicos.
  - `detectar_nits_nuevos(maestro, historico, nits_extra)`: filtra NITs nuevos.

- `core/procesadores/exportador_nits_siigo.py` — `construir_fila_siigo` acepta
  `codigo_ciudad` del XML (más confiable que adivinar por nombre).

### 1.2 Propinas en plano POS

Fórmula del usuario, aplicada solo cuando hay INC > 0:
```
base_inc = INC / 0.08
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
Cuenta default propinas: `28150505` (PUC JIPER).
CC propina = CC de la sucursal (como en histórico real).

---

## Bloque 2 — Nueva página `5b_Descargador_XML.py`

Página unificada que reemplaza el flujo manual de subir ZIPs descargados con
extensión Chrome. Aparece como `📥 Descargador XML DIAN` en la sección
"Asistente Contable" del menú principal, **al lado** de las demás herramientas.

Flujo:

```
1️⃣  Subir Excel del Token DIAN
    → detecta fechas, tipos de documentos y prefijos automáticamente

2️⃣  Elegir qué descargar
    📥 RECIBIDOS                    📤 EMITIDOS
    Checkboxes por tipo:            Multiselect de prefijos:
    ☑ Factura electronica           ☑ STL — 15 docs
    ☑ Nota credito                  ☑ DSE — 8 docs
    ☑ Documento Soporte             ☐ VIV — 50 docs
    ☐ Application response (off)    ☐ IND — 30 docs
    ☐ Nomina Individual (off)

3️⃣  Pegar Token URL → ⬇️ Descargar
    Descarga paralela en bloques de 500 con barra de progreso

4️⃣  Procesar XMLs
    → Plano contable por empresa (TXT/CSV/Excel)
    → Plano de TERCEROS NUEVOS para Siigo (20 columnas)
```

**Decisiones de diseño:**
- Application response y Nomina Individual **OFF por default** (no contables).
- Prefijos **STL** y **DSE** sugeridos por default (los más usados en JIPER).
- El procesamiento es post-descarga (no automático) para revisar el dictamen.

---

## Cambio en `Home.py`

Diff mínimo — solo se agrega el registro de la nueva página y se incluye en
el sidebar de "Asistente Contable". Todas las demás herramientas siguen
en su lugar:

```diff
+asistente_xml_descargador = st.Page(
+    "app_pages/5b_Descargador_XML.py",
+    title="Descargador XML DIAN",
+    icon="📥",
+    url_path="descargador-xml",
+)

 nav = st.navigation(
     {
         ...
         "🤖 Asistente Contable": [
             asistente_caja,
             asistente_token_dian,
             asistente_nomina,
             asistente_prov,
             asistente_ventas_c13,
             asistente_pos,
             asistente_pila,
+            asistente_xml_descargador,
         ],
         "📊 Herramientas Tributarias": [...],
         "⚙️ Sistema": [...],
     },
 )
```

---

## Archivos modificados

```
Home.py                                             (+11 líneas, 0 removidas)
app_pages/4b_Ingresos_POS.py                        (sin cambios)
app_pages/5b_Descargador_XML.py                     (NUEVO)
app_pages/5a_DIAN_XML.py                            (modificado del turno anterior)
core/data/datos_punto.json                          (+cta_propinas)
core/procesadores/procesador_dian_xml.py            (+campos extendidos emisor)
core/procesadores/procesador_pos.py                 (+lógica propinas)
core/procesadores/exportador_nits_siigo.py          (+codigo_ciudad)
core/procesadores/agregador_terceros_xml.py         (NUEVO)
datos_punto.json                                    (+cta_propinas)
tests/test_pos_propinas.py                          (NUEVO — 6 tests)
tests/test_agregador_terceros_xml.py                (NUEVO — 7 tests)
tests/test_filtros_descargador.py                   (NUEVO — 7 tests)
```

## Tests

Total: **38 tests pasan**, 0 regresiones.

## Cómo se ve el menú después del parche

```
📊 Plataforma Contable
├── 🏠 Inicio
├── 🤖 Asistente Contable
│   ├── 💵 Caja Menor
│   ├── 📥 Procesar Token DIAN
│   ├── 💼 Nómina
│   ├── 📝 Provisiones
│   ├── 🛍️ Ventas C13
│   ├── 🧾 Ventas POS
│   ├── 📎 PILA
│   └── 📥 Descargador XML DIAN          ← NUEVO
├── 📊 Herramientas Tributarias
│   ├── 📑 RADIAN Acuses DIAN
│   ├── 📑 Información Exógena
│   ├── 📝 Declaración de Renta
│   ├── 💸 IVA y reteIVA
│   ├── 🧾 Retención en la Fuente
│   └── 🥤 Impuestos Saludables
└── ⚙️ Sistema
    ├── 🛡️ Panel Admin
    └── ⚙️ Configuración
```
