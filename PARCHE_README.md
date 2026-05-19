# Parche v9 — JIPER + DIAN PT + DIAN FE (mayo 2026)

Sesión muy extensa que acumuló:
- Trabajo previo (POS, descargador XML, multi-empresa, propinas, plano cronológico)
- Módulo `core/dian_pt/` para eventos RADIAN (3.497 líneas)
- Módulo `core/dian_fe/` para facturas electrónicas (1.517 líneas) **🆕**

## 🆕 Nuevo en este turno: `core/dian_fe/`

Base de código para emitir Facturas Electrónicas de Venta DIAN.

### Archivos nuevos

| Archivo | Líneas | Función |
|---|---|---|
| `__init__.py` | 112 | API pública del módulo |
| `modelos.py` | 498 | Dataclasses: Factura, LineaFactura, ParteFE, Resolucion, ImpuestoLinea, etc. |
| `cufe_calculator.py` | 326 | Hash SHA-384 del CUFE según fórmula DIAN |
| `xml_factura.py` | 581 | Generador XML UBL 2.1 completo |
| `README.md` | ~200 | Documentación técnica |

### Lo que cubre

✅ Modelos de datos para factura JIPER (responsable IVA + INC 8% restaurante)
✅ Cálculo del CUFE con formato decimal correcto
✅ Generación XML UBL 2.1 con todas las extensiones DIAN:
  - UBLExtensions con DianExtensions
  - InvoiceControl (resolución, prefijo SETP, rango)
  - InvoiceSource, SoftwareProvider, AuthorizationProvider
  - SoftwareSecurityCode (SHA-384 del SoftwareID + PIN + CUFE) ← calculado automáticamente
  - QRCode con URL pública DIAN
  - AccountingSupplierParty / AccountingCustomerParty completos
  - TaxTotal, LegalMonetaryTotal, InvoiceLine
  - Placeholder firma XAdES (lo llena el firmador)

### Lo que NO cubre todavía

❌ Notas Crédito (el set pide 10 — falta `xml_nota_credito.py`)
❌ Notas Débito (el set pide 10 — falta `xml_nota_debito.py`)
❌ Cliente SOAP método `SendBillSync` para facturas (el actual es para eventos)
❌ Retenciones (renta, IVA, ICA)
❌ Descuentos globales complejos
❌ Múltiples IVAs en una misma factura
❌ Validación contra XSD oficial DIAN

### Datos JIPER ya configurados

| Dato | Valor |
|---|---|
| NIT / DV | 901038325 / 1 |
| Razón social | JIPER SAS |
| Régimen | Responsable IVA (O-13) |
| CIIU | 5611 (restaurantes) |
| Software ID | aa20f88a-390b-4b48-8e2b-60560f126a36 |
| PIN del SW | 86818 |
| Clave técnica | fc8eac422eba16e22ffd8c6f94b3f40a6e38162c |
| Resolución | 18760000001 SETP 990000000-995000000 |
| TestSetId (vigente) | fa0e4d06-89cf-4b88-ad9f-542bef612d32 |

## Pipeline funcionando (test end-to-end)

```python
from core.dian_fe import Factura, LineaFactura, ParteFE, Resolucion, MedioPago, ImpuestoLinea
from core.dian_fe import calcular_cufe_desde_factura, generar_xml_factura
from core.dian_pt import cargar_p12, firmar_xml

# 1) Construir factura con datos JIPER
factura = Factura(folio=990000001, ...)
factura.calcular_totales()
factura.cufe = calcular_cufe_desde_factura(factura, ambiente="habilitacion")

# 2) Generar XML
xml = generar_xml_factura(factura)
# ✅ XML UBL 2.1 de ~9KB, 16/16 validaciones críticas

# 3) Firmar (reusa el firmador del módulo dian_pt)
cert = cargar_p12("jiper.p12", "pass")
xml_firmado = firmar_xml(xml, cert)
# ✅ XML firmado de ~13KB, firma XAdES-EPES criptográficamente válida

# 4) Enviar: PENDIENTE — extender cliente SOAP con SendBillSync para facturas
```

## Resumen final del trabajo DIAN

```
core/dian_pt/                       3.497 líneas (eventos RADIAN)
  ├── certificado.py
  ├── cude_calculator.py
  ├── xml_evento_radian.py
  ├── firmador_xades.py             ← reutilizado por dian_fe
  ├── cliente_dian_soap.py          ← extensión pendiente para facturas
  ├── vault.py
  ├── auditoria.py
  └── servicio_multi_tenant.py

core/dian_fe/                       1.517 líneas (facturas) 🆕
  ├── modelos.py
  ├── cufe_calculator.py
  └── xml_factura.py

Total módulos DIAN:                 5.014 líneas
```

## Próximos pasos (próxima sesión)

### Antes de la próxima sesión, tú prepara:
1. Descargar **Anexo Técnico DIAN versión vigente** (PDF, ~300 páginas).
   https://www.dian.gov.co/impuestos/factura-electronica/factura-electronica/Paginas/anexos-tecnicos.aspx
2. En el portal DIAN, ver si aparece la **lista de los 50 escenarios** específicos del set.
3. Tener el **.p12 real** de JIPER listo (Andes/Certicámara/GSE).

### En la próxima sesión:
1. Validar CUFE contra ejemplo del Anexo Técnico vigente (puede requerir ajuste).
2. Extender `cliente_dian_soap.py` con método `enviar_factura()` (SendBillSync).
3. Construir generador de Notas Crédito (`xml_nota_credito.py` ~600 líneas).
4. Construir generador de Notas Débito (`xml_nota_debito.py` ~600 líneas).
5. UI Streamlit para registrar credenciales y emitir documentos.
6. Primer envío real al ambiente de habilitación.
7. Iterar contra errores DIAN.

## Validación de esta sesión

- ✅ 51 tests previos pasan (0 regresiones)
- ✅ Pipeline FE end-to-end: modelos → CUFE → XML → firma → OK
- ✅ Test caso JIPER: 2 platos + 1 limonada = $66.000 base + INC 8% = $71.280 total
- ✅ XML de 9.360 bytes con 16/16 validaciones críticas
- ✅ Firma XAdES de 13.753 bytes criptográficamente válida

## ⚠️ Disclaimer importante

Este código es **BASE para iteración contra DIAN**, NO producto terminado.
- El CUFE probablemente requiere ajuste fino contra el ejemplo del Anexo Técnico vigente.
- El XML probablemente fallará en el primer envío con códigos como FAJ60-69 que indican qué campo ajustar.
- La firma puede requerir actualizar el hash de política DIAN.
- El SOAP requiere extensión para `SendBillSync`.

Esperá rechazos de DIAN en los primeros envíos. Cada rechazo te dirá qué archivo ajustar.
