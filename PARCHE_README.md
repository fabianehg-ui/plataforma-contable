# Parche v7 — JIPER + Módulo PT DIAN (mayo 2026)

Este parche acumula TODO el trabajo anterior + el nuevo módulo
`core/dian_pt` como BASE para Proveedor Tecnológico DIAN propio.

## 🆕 Nuevo en este turno

### Módulo `core/dian_pt/` — Base de Proveedor Tecnológico DIAN

**2.230 líneas** de código nuevas. Estructura:

```
core/dian_pt/
├── __init__.py              151 líneas — API pública del módulo
├── certificado.py           284 líneas — Manejo .p12 (Andes/Certicámara/GSE)
├── cude_calculator.py       209 líneas — Cálculo CUDE eventos (SHA-384)
├── xml_evento_radian.py     575 líneas — Generador XML UBL 2.1
├── firmador_xades.py        479 líneas — Firma XAdES-EPES + política DIAN
├── cliente_dian_soap.py     532 líneas — Cliente SOAP a vpfe.dian.gov.co
└── README.md                ~150 líneas — Doc técnico para iteración
```

### Lo que cubre

✅ Carga de certificados .p12 con manejo de errores específicos
✅ Cálculo CUDE de eventos según fórmula DIAN
✅ Generación XML UBL 2.1 con todas las extensiones DIAN
✅ Firma XAdES-EPES con 3 referencias firmadas + política DIAN
✅ Cliente SOAP con WSSecurity (header firmado) + WSA
✅ Soporta eventos 030 (acuse), 031 (reclamo), 032 (recibo bien), 033 (aceptación)
✅ Habilitación + producción (mismo código, distinto endpoint)
✅ Tests internos pasan: certificado, CUDE, XML, firma criptográfica, SOAP envelope

### Lo que NO cubre todavía

❌ Set de habilitación DIAN (186 escenarios) — proceso formal con DIAN
❌ Pruebas contra ambiente real de habilitación — requiere credenciales DIAN
❌ Multi-tenant (manejo seguro de varios .p12 de empresas distintas)
❌ UI Streamlit para emitir eventos masivos
❌ Sistema de reintentos + cola de envíos persistente
❌ Validación contra XSD oficiales DIAN
❌ Actualización del hash de política de firma (placeholder)

## Validación

✅ 6 archivos sintácticamente correctos
✅ Importable desde `core.dian_pt`
✅ Tests internos OK (firma criptográfica verifica, envelope parseable)
✅ Suite previa: 51 tests pasan, 0 regresiones

## Pasos siguientes (para tu consultor DIAN)

Ver `core/dian_pt/README.md` que tiene:
- Fases del proceso de habilitación
- Errores típicos de DIAN y archivo a revisar para cada uno
- Tabla de costos estimados ($27M-$74M COP año 1)
- Particularidades técnicas (canonicalización, ZIP, SOAP 1.2)
- Códigos de evento y cuándo se emite cada uno

## Lo demás incluido (lo del parche v6)

- Módulo descargador XML DIAN renombrado a "Contabilidad con XML DIAN"
- Ocultado del menú: "Procesar Token DIAN"
- Modo solo_pos en Ventas POS (sin DSE/STL, doc=día, orden cronológico)
- Configuración multi-empresa JIPER
- Filtros del descargador (checkboxes recibidos, multiselect emitidos)
- Propinas POS en ambos modos (Reportes + Token)
- Terceros nuevos desde XMLs (plano Siigo)

## Cómo aplicar

```bash
# Descomprime sobre el repo
unzip -o parche_jiper_v7_dian_pt.zip -d /ruta/plataforma-contable/

# Reinicia Streamlit
streamlit run Home.py

# El módulo nuevo no aparece en UI todavía (es solo backend).
# Puede importarse desde Python:
from core.dian_pt import cargar_p12, generar_xml_evento, firmar_xml, ClienteDIAN
```

## Dependencias nuevas

Si tu venv no las tiene:
```bash
pip install signxml zeep cryptography lxml
```

## Tiempo estimado a producción

- **Hoy:** código BASE listo para iteración (2.230 líneas).
- **+1 mes:** consultor DIAN ajusta para pasar primeros escenarios habilitación.
- **+3 meses:** 186 escenarios pasados, resolución DIAN para producción.
- **+6 meses:** primeros clientes facturando con tu PT.
