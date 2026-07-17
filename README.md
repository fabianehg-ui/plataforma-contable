# INTEGRAL

Plataforma web de **gestión contable integral** (Streamlit + Supabase): nómina, retención en la fuente (F350), conciliación, impuestos y generación de planos contables.

---

## Novedades de la v2.1.5

**Clasificador de conceptos mejorado** con 3 niveles de reglas en orden de confianza:

1. **Código PUC exacto** (alta confianza) — la cuenta 23-65-XX se reconoce automáticamente.
2. **Patrones combinados** (alta) — ej: VIGILANCIA + FISCAL → Honorarios; VIGILANCIA + PRIVADA → Servicios.
3. **Palabras clave individuales** (media confianza).

Cada movimiento ahora reporta también su nivel de confianza, lo que permite identificar fácilmente cuáles requieren revisión manual.

### Casos que ahora se clasifican bien (antes caían a "Otros pagos"):

- VIGILANCIA FISCAL → Honorarios
- CONSULTORIA EN SISTEMAS → Honorarios
- ASESORIA TRIBUTARIA → Honorarios
- REVISORIA FISCAL → Honorarios
- FRANQUICIA → Regalías
- LICENCIA DE USO DE MARCA → Regalías
- TRANSPORTE DE CARGA → Servicios
- MANTENIMIENTO → Servicios
- CAPACITACION → Servicios
- INTERESES DE PRESTAMO → Rendimientos financieros
- PAGOS AL EXTERIOR → Otros pagos (prioridad sobre cualquier otra palabra)

---

## ⚠️ Aviso normativo importante

**El Consejo de Estado suspendió provisionalmente** los artículos 2 al 8 del **Decreto 0572 de 2025** mediante auto del **7 de mayo de 2026**. Desde el **8 de mayo de 2026** aplican las tarifas y bases de los **Decretos 0261/2023 y 0242/2024** (DIAN Comunicado 070 del 08/05/2026).

**Esta versión todavía tiene cargadas las tarifas del Decreto 0572.** Si vas a presentar una declaración con período desde mayo 2026 en adelante, verifica manualmente las tarifas de autorretención por CIIU antes de generar el F350. La actualización de tarifas vigentes está pendiente para una próxima versión.

---

## Flujo del usuario

### 1. Registrar empresa
Menú → `🏢 Empresas` → `+ Nueva empresa`. Datos: NIT, razón social, CIIU, tarifa autorretención.

### 2. Nueva declaración mensual
Menú → `➕ Nueva Declaración` → selecciona empresa + mes + año.

### 3. Cargar los 2 PDFs de Contai
- **Auxiliar de Retefuente**: Reportes → Tributarios → Análisis de % de Retención (resumido)
- **Balance de Prueba**: Reportes → Contables → Balance de Prueba por Cuenta

### 4. Procesar
La app valida NITs (PJ/PN/extranjeros), clasifica cada movimiento al concepto F350, asigna casillas, calcula autorretención sobre cuenta 4.

### 5. Revisar Ficha de Diligenciamiento
Vista consolidada con botones 📋 Copiar al lado de cada valor.

### 6. Exportar PDF del F350
Layout similar al oficial DIAN, con marca de agua "BORRADOR".

### 7. Copiar a Muisca, firmar y presentar
Tienes el PDF al lado + los botones 📋 en la app.

### 8. Marcar como presentada
Queda registro en la BD para papeles de trabajo.

---

## Mapeo de casillas (validado con F350 real)

### Retenciones a título de renta

| Concepto | Base PJ | Ret PJ | Base PN | Ret PN |
|---|---|---|---|---|
| Rentas de trabajo | — | — | 77 | 93 |
| Honorarios | 29 | 42 | 79 | 95 |
| Comisiones | 30 | 43 | 80 | 96 |
| Servicios | 31 | 44 | 81 | 97 |
| Rendimientos financieros | 32 | 45 | 82 | 98 |
| Arrendamientos | 33 | 46 | 83 | 99 |
| Regalías | 34 | 47 | 84 | 100 |
| Dividendos | 35 | 48 | 85 | 101 |
| Compras | 36 | 49 | 86 | 102 |
| Contratos construcción | 38 | 51 | 88 | 104 |
| Loterías rifas | 39 | 52 | 90 | 106 |
| Otros pagos | 41 | 54 | 92 | 108 |

### Autorretenciones

| Concepto | Base | Retención |
|---|---|---|
| Contribuyentes exonerados 114-1 | 59 | 68 |
| Ventas | 60 | 69 |
| Honorarios | 61 | 70 |
| Servicios | 63 | 72 |
| Otros conceptos | 67 | 76 |

### Totales

| Casilla | Concepto |
|---|---|
| 130 | Total retenciones renta y complementario |
| 134 | Total retenciones IVA |
| 136 | Total retenciones |
| 138 | Total retenciones más sanciones |

---

## Instalación

### Una sola vez: Python 3.12
https://www.python.org/downloads/ · Marcar "Add Python to PATH".

### Probar la app
Doble clic en `EJECUTAR_APP.bat` (la primera vez instala pdfplumber + reportlab).

### Generar .exe distribuible
Doble clic en `COMPILAR_APP.bat`. Tarda 8-15 min, genera `dist/BorradorFacil350.exe`.

---

## Límites

- NO presenta ante la DIAN (lo hace el contador en Muisca con IFE).
- NO reemplaza criterio profesional.
- NO se conecta a internet ni a sistemas DIAN.
- La responsabilidad final sobre la declaración es del contador firmante.

Si detectas un concepto mal mapeado, edita la función `clasificar_concepto_por_cuenta()` o el dict `MAPEO_CASILLAS_F350` en el código. Para agregar palabras clave nuevas, ahora basta con añadir entradas a `REGLAS_CODIGO_PUC`, `REGLAS_PATRON_COMBINADO` o `REGLAS_PALABRA_CLAVE` (sin tocar el resto del código).

---

## Historial

- **2.1.5** — Clasificador mejorado con código PUC + patrones combinados + confianza
- 2.1.0 — Exportación PDF estilo DIAN + mapeo corregido
- 2.0.0 — Carga automática de PDFs de Contai + autorretención cuenta 4
- 1.1.0 — Módulo manual con Ficha de Diligenciamiento
- 1.0.0 — CRUD empresas, catálogo CIIU, validación NIT
