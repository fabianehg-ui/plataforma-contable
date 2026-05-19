# Parche consolidado v6 — JIPER (mayo 2026)

Este parche incluye todo el trabajo acumulado **MÁS** los cambios de este turno:

## 🆕 Cambios de este turno

1. **Renombrar** "Descargador XML DIAN" → **"Contabilidad con XML DIAN"**.
   El nombre refleja mejor que la página no solo descarga, también contabiliza.

2. **Reordenar** el menú Asistente Contable. Ahora queda así:
   ```
   🤖 Asistente Contable
     ├── 📥 Contabilidad con XML DIAN    ← primero (es el principal)
     ├── 💵 Caja Menor
     ├── 💼 Nómina
     ├── 📝 Provisiones
     ├── 🛍️ Ventas C13
     ├── 🧾 Ventas POS
     └── 📎 PILA
   ```

3. **Ocultar** "Procesar Token DIAN" del menú. El archivo
   `app_pages/2_Procesar_Token_DIAN.py` **NO se borra** — solo se quita del
   sidebar. Si en 1-2 meses no se necesita, se puede eliminar definitivamente.

   La URL `/procesar-token-dian` queda inaccesible salvo que alguien la
   conozca y la escriba directo en el navegador.

## Cambio en Home.py

Diff mínimo:

```diff
-asistente_token_dian = st.Page(...)                  # ya no se usa en nav
+asistente_xml_descargador = st.Page(
+    "app_pages/5b_Descargador_XML.py",
+    title="Contabilidad con XML DIAN",                # ← renombrado
+    icon="📥",
+    url_path="contabilidad-xml-dian",
+)

 nav = st.navigation({
     "🤖 Asistente Contable": [
+        asistente_xml_descargador,                    # ← primero
         asistente_caja,
-        asistente_token_dian,                         # ← removido del nav
         asistente_nomina,
         ...
     ],
 })
```

## Todo lo demás se mantiene

- **Bloque 1**: terceros desde XMLs + propinas POS reportes
- **Bloque 2**: nueva página Contabilidad con XML DIAN (antes Descargador XML)
- **Bloque 3**: modo Excel del Token en Ventas POS
- **Bloque 4**: configuración multi-empresa JIPER
- **Bloque 5**: modo solo_pos (sin DSE/STL, orden cronológico, doc=día)

## Tests

**51 tests pasan**, 0 regresiones.

## Menú final

```
📊 Plataforma Contable
├── 🏠 Inicio
├── 🤖 Asistente Contable
│   ├── 📥 Contabilidad con XML DIAN     ← NUEVO NOMBRE, primer lugar
│   ├── 💵 Caja Menor
│   ├── 💼 Nómina
│   ├── 📝 Provisiones
│   ├── 🛍️ Ventas C13
│   ├── 🧾 Ventas POS
│   └── 📎 PILA
├── 📊 Herramientas Tributarias  (intacto)
│   ├── 📑 RADIAN Acuses DIAN
│   ├── 📑 Información Exógena
│   ├── 📝 Declaración de Renta
│   ├── 💸 IVA y reteIVA
│   ├── 🧾 Retención en la Fuente
│   └── 🥤 Impuestos Saludables
└── ⚙️ Sistema  (intacto)
    ├── 🛡️ Panel Admin
    └── ⚙️ Configuración
```

"Procesar Token DIAN" ya no aparece en el menú (oculto, no borrado).
