# Módulo `core/dian_fe` — Facturación Electrónica DIAN

Base de código para emitir Facturas Electrónicas de Venta (FE) ante DIAN
bajo el modo "Software propio". Diseñado inicialmente para JIPER SAS
(restaurante con INC 8%).

## ⚠️ Estado actual

**BASE FUNCIONAL — falta iteración contra DIAN real.**

### Lo que está
- ✅ Modelos de datos completos (Factura, Línea, Parte, Impuesto, Resolución, etc.)
- ✅ Cálculo del CUFE según fórmula oficial DIAN
- ✅ Generación XML UBL 2.1 con estructura DIAN (UBLExtensions, DianExtensions, etc.)
- ✅ Integración con firmador XAdES-EPES del módulo `dian_pt`
- ✅ Soporte de INC 8% y IVA 19% (las tasas que usa JIPER)
- ✅ Helpers `ImpuestoLinea.inc_8_porciento()` / `iva_19_porciento()` / `iva_5_porciento()`

### Lo que falta
- ❌ **Generación de Notas Crédito** (xml_nota_credito.py) — el set pide 10
- ❌ **Generación de Notas Débito** (xml_nota_debito.py) — el set pide 10
- ❌ **Cliente SOAP para SendBillSync** — el módulo SOAP actual es para eventos. Hay que agregar el método para enviar facturas.
- ❌ **Validación contra XSD oficial DIAN** — los facturadores comerciales validan antes de enviar
- ❌ **Manejo de retenciones** (renta, IVA, ICA)
- ❌ **Descuentos globales complejos**
- ❌ **Múltiples tasas de IVA en una misma factura**
- ❌ **Facturas a crédito con planes de pago**
- ❌ **Pasar los 50 escenarios del set de pruebas DIAN**

## Arquitectura

```
core/dian_fe/
├── __init__.py            ← API pública
├── modelos.py             ← Dataclasses: Factura, Linea, Parte, etc.
├── cufe_calculator.py     ← Hash SHA-384 del CUFE
└── xml_factura.py         ← Generador XML UBL 2.1
```

Reusa de `core/dian_pt/`:
- `firmador_xades.py` para firmar el XML
- `vault.py` para credenciales DIAN
- `cliente_dian_soap.py` para enviar (cuando se extienda)

## Datos JIPER ya configurados

| Dato | Valor |
|---|---|
| NIT | 901038325 |
| DV | 1 |
| Razón social | JIPER SAS |
| Régimen | Responsable IVA (O-13, regimen_fiscal 48) |
| CIIU | 5611 (restaurantes) |
| Software ID | aa20f88a-390b-4b48-8e2b-60560f126a36 |
| PIN del SW | 86818 |
| Clave técnica | fc8eac422eba16e22ffd8c6f94b3f40a6e38162c |
| Resolución | 18760000001 |
| Prefijo | SETP |
| Rango | 990000000 - 995000000 |
| Vigencia | 19/01/2019 - 19/01/2030 |
| TestSetId | fa0e4d06-89cf-4b88-ad9f-542bef612d32 |

⚠️ El **TestSetId** debe ir en el header SOAP cuando se envíen documentos
del set de pruebas. Cuando se extienda `cliente_dian_soap.py` con
`SendBillSync` para facturas, agregar este valor en `wcf:fileName` o
header equivalente.

## Plan de iteración con DIAN

### Fase 1 — Antes del primer envío
1. Confirmar que el algoritmo CUFE coincide con un ejemplo del Anexo Técnico
   vigente. (El módulo trae un ejemplo de v1.8 que puede estar desactualizado.)
2. Validar manualmente que el XML pase un validador XSD UBL 2.1 + DIAN.
3. Conseguir el certificado real .p12 de JIPER (Andes / Certicámara / GSE).

### Fase 2 — Primer envío
1. Configurar credenciales reales en el vault:
   ```python
   from core.dian_pt import ServicioDIAN
   servicio = ServicioDIAN(master_password=os.environ["DIAN_MASTER_PWD"])
   servicio.registrar_cliente(
       nit="901038325", razon_social="JIPER SAS",
       p12_bytes=..., p12_password="...",
       software_id="aa20f88a-390b-4b48-8e2b-60560f126a36",
       software_security_code="86818",
       clave_tecnica="fc8eac422eba16e22ffd8c6f94b3f40a6e38162c",
       ambiente="habilitacion",
   )
   ```
2. Crear una factura simple según el primer escenario que dé DIAN.
3. Generar, firmar y enviar.
4. Leer la respuesta de DIAN. Si rechaza, ver Fase 3.

### Fase 3 — Iteración con errores DIAN

Errores comunes y archivo a revisar:

| Código DIAN | Causa típica | Archivo |
|---|---|---|
| FAJ24 / FAK01 | CUFE incorrecto | `cufe_calculator.py` (formato decimal, orden) |
| FAJ58 | Estructura UBL inválida | `xml_factura.py` (namespace, orden tags) |
| FAJ60-FAJ69 | Campo faltante o mal | `xml_factura.py` |
| FAK24-FAK25 | Firma inválida | `firmador_xades.py` (en `core/dian_pt`) |
| FAR16 | WSSecurity inválido | `cliente_dian_soap.py` |
| FAB07 | Cert no autorizado | Verificar registro del certificado en DIAN |
| FAB17 | Software ID/PIN incorrecto | Verificar credenciales DIAN |

### Fase 4 — Pasar los 50 escenarios
DIAN suele exigir variaciones como:
- 1 línea / múltiples líneas
- IVA 19% / 5% / 0% / excluido
- INC 8% (aplica a JIPER por restaurante)
- Con descuento línea / global
- Cliente persona natural / jurídica
- Régimen común / simple
- Contado / crédito
- Con retención en la fuente
- Etc.

Para cada uno: ajustar `modelos.py` y `xml_factura.py` según lo que DIAN
pida. Algunos pueden requerir agregar nuevos campos opcionales que el
módulo actual omite.

## Particularidades importantes

### Sobre el SoftwareSecurityCode

DIAN exige que el campo `<sts:SoftwareSecurityCode>` sea:
```
SHA-384(SoftwareID + PIN + CUFE)
```

donde:
- `SoftwareID` = UUID asignado por DIAN
- `PIN` = software_security_code asignado por DIAN
- `CUFE` = el CUFE de ESTA factura específica

Esto se calcula automáticamente en `xml_factura.py:_agregar_ubl_extensions()`.

### Sobre el QR

El elemento `<sts:QRCode>` debe contener:
```
https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={CUFE}
```

Eso se construye automáticamente en `_construir_url_qr()`.

### Sobre los decimales

DIAN exige formato `XXXX.XX` (2 decimales, punto, sin separador de miles).
El módulo usa `Decimal` internamente y formatea con `quantize(Decimal("0.01"))`.

Cuidado con:
- `Decimal("100") → "100.00"` ✅
- `float(100) → "100.0"` ❌ (no usar floats)

### Sobre las fechas

Formato exigido por DIAN:
- Fecha: `YYYY-MM-DD`
- Hora: `HH:MM:SS-05:00` (con offset Colombia)

## Próximos pasos

Cuando tengas un primer rechazo de DIAN con código de error:
1. Copiar el código y mensaje completo
2. Revisar el archivo correspondiente según la tabla de arriba
3. Ajustar el campo afectado
4. Reintentar
