# Módulo `core/dian_pt` — Proveedor Tecnológico DIAN

Base de código para construir un Proveedor Tecnológico (PT) propio ante DIAN
Colombia. Cubre eventos RADIAN/Recepción Electrónica.

## ⚠️ Estado actual

**NO HABILITADO. Es código BASE para iteración.**

Lo que está aquí:
- ✅ Carga y validación de certificado .p12 (Andes, Certicámara, GSE)
- ✅ Cálculo CUDE de eventos según fórmula DIAN
- ✅ Generación XML UBL 2.1 para eventos 030/031/032/033
- ✅ Firma XAdES-EPES con política DIAN
- ✅ Cliente SOAP con WSSecurity para envío

Lo que falta para producción:
- ❌ Pasar el set de habilitación DIAN (186 escenarios)
- ❌ Validar contra el ambiente real de habilitación
- ❌ Actualizar hash de política de firma al vigente
- ❌ Ajustar elementos UBL según rechazos reales de DIAN
- ❌ Multi-tenant (manejo seguro de varios .p12 de clientes)
- ❌ UI Streamlit y persistencia
- ❌ Sistema de reintentos y cola de envíos
- ❌ Pólizas de cumplimiento + infraestructura

## Arquitectura

```
core/dian_pt/
├── certificado.py        ← Cargar .p12, extraer datos del titular
├── cude_calculator.py    ← Hash SHA-384 según fórmula DIAN
├── xml_evento_radian.py  ← Generar XML UBL 2.1 (030/031/032/033)
├── firmador_xades.py     ← Firma XAdES-EPES + política DIAN
├── cliente_dian_soap.py  ← Cliente SOAP a vpfe.dian.gov.co
└── __init__.py           ← API pública del módulo
```

Flujo de envío:

```
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │ Cargar .p12 │ ─→ │ Calc CUDE   │ ─→ │ Generar XML │
   │ (cert .p12) │    │ (SHA-384)   │    │ (UBL 2.1)   │
   └─────────────┘    └─────────────┘    └──────┬──────┘
                                                 │
                       ┌─────────────────────────┘
                       ▼
                ┌─────────────┐    ┌──────────────┐    ┌────────┐
                │ Firmar XML  │ ─→ │ Envío SOAP   │ ─→ │  DIAN  │
                │ XAdES-EPES  │    │ + WSSecurity │    │        │
                └─────────────┘    └──────────────┘    └────────┘
```

## Plan de iteración con DIAN

### Fase 0: Antes de empezar

1. **Constituir/habilitar la sociedad PT.** Verificar objeto social, patrimonio.
2. **Solicitar habilitación PT a DIAN** vía Portal Tributario. Recibirás:
   - Software ID (UUID)
   - PIN del software (SoftwareSecurityCode)
   - Clave técnica para CUDE/CUFE
3. **Conseguir certificado digital** (Andes/Certicámara/GSE para empresa).
4. **Descargar política de firma vigente** de:
   `https://facturaelectronica.dian.gov.co/politicadefirma/v2/`

### Fase 1: Actualizar este código con datos reales

En `firmador_xades.py`:
```python
# Actualizar al hash REAL de la política PDF vigente
POLITICA_FIRMA_HASH = "<sha256_base64_del_PDF>"
```

Calcular el hash:
```bash
wget https://facturaelectronica.dian.gov.co/politicadefirma/v2/politicadefirmav2.pdf
openssl dgst -sha256 -binary politicadefirmav2.pdf | base64
```

### Fase 2: Pasar el set de habilitación

DIAN entrega un set de **186 escenarios** que el PT debe procesar exitosamente
en ambiente de habilitación. Para eventos RADIAN son aproximadamente 25-30
escenarios.

Para cada escenario:
1. Generar el XML del evento con los datos del escenario.
2. Firmarlo.
3. Enviarlo a `vpfe-hab.dian.gov.co`.
4. Esperar AppResponse de DIAN.
5. Si rechaza: leer el código de error, ajustar código, reintentar.
6. Si acepta: marcar escenario como pasado.

**Errores típicos de DIAN y dónde mirar:**

| Código DIAN | Causa probable | Archivo a revisar |
|---|---|---|
| FAK24, FAK25 | Firma inválida o digest incorrecto | `firmador_xades.py` |
| FAJ58 | Estructura UBL inválida | `xml_evento_radian.py` |
| FAJ60-FAJ69 | Campo obligatorio faltante en UBL | `xml_evento_radian.py` |
| FAK04 | CUDE no coincide con campos del documento | `cude_calculator.py` |
| FAR16 | WSSecurity del header SOAP inválido | `cliente_dian_soap.py` |
| FAB07 | Certificado del titular no autorizado | Verificar registro PT |
| FAB17 | Software ID/SecurityCode incorrectos | Verificar credenciales DIAN |

### Fase 3: Solicitar pase a producción

Cuando los 186 escenarios pasen, DIAN emite resolución autorizando producción.
Después se cambia el endpoint de habilitación a producción y arrancan los
envíos reales.

## Particularidades técnicas que vale la pena conocer

### Sobre la firma XAdES-EPES

DIAN exige tres referencias firmadas en el `<ds:SignedInfo>`:
1. **Documento completo** (URI=""): digest del XML sin la firma misma
   (con `enveloped-signature` transform).
2. **KeyInfo** (URI="#keyinfo-id"): para evitar sustitución de certificado.
3. **SignedProperties** (URI="#signedprops-id"): el Type DEBE ser
   `http://uri.etsi.org/01903#SignedProperties` o DIAN rechaza.

El **SignedProperties** debe contener obligatoriamente:
- `SigningTime` (UTC)
- `SigningCertificate` con `CertDigest` (SHA-256 del .cer DER) y `IssuerSerial`
- `SignaturePolicyIdentifier` con OID + URL + Hash de la política DIAN
- `SignerRole` con ClaimedRole = "supplier"

### Sobre el SOAP envelope

DIAN usa **SOAP 1.2** (no 1.1). Diferencias clave:
- Namespace: `http://www.w3.org/2003/05/soap-envelope`
- Content-Type: `application/soap+xml;charset=UTF-8`
- Header WSA (WS-Addressing) obligatorio: Action, To, MessageID

El header WSSecurity debe firmar **3 elementos**:
- `<s:Body>` (con `wsu:Id`)
- `<wsu:Timestamp>` (con Created + Expires < 5 min)
- `<wsa:To>` (con `wsu:Id="id-To"`)

### Sobre la canonicalización

Usar **C14N exclusiva** (`http://www.w3.org/2001/10/xml-exc-c14n#`), no la
inclusiva. La canonicalización inclusiva ARRASTRA namespaces no usados y DIAN
rechaza con FAK24.

### Sobre el ZIP

El XML del evento se comprime con DEFLATE y se base64-encode antes de
enviarse en `<wcf:contentFile>`. El nombre del archivo dentro del ZIP
debe terminar en `.xml`. DIAN espera **un solo archivo por ZIP**.

## Endpoints DIAN

```
Habilitación: https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc
Producción:   https://vpfe.dian.gov.co/WcfDianCustomerServices.svc

WSDL (para inspección):
  https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc?wsdl
```

## Operaciones del WSDL

| Operación | Para qué |
|---|---|
| `SendBillSync` | Enviar factura electrónica (no aplica a este módulo) |
| `SendBillAsync` | Envío asíncrono masivo |
| `SendTestSetAsync` | Envío del set de habilitación (Fase 2) |
| `SendNominaSync` | Nómina electrónica (no aplica) |
| `SendEventUpdateStatus` | **Enviar evento RADIAN** ← lo que usamos |
| `GetStatus` | Consultar estado de un envío por TrackId |
| `GetStatusZip` | Descargar AppResponse de DIAN |
| `GetNumberingRange` | Consultar resoluciones de numeración |
| `GetExchangeEmail` | Email corporativo del proveedor |

## Códigos de evento

| Código | Nombre | Quién lo emite | Cuándo |
|---|---|---|---|
| 030 | Acuse de recibo de FE | Adquiriente | Al recibir la factura |
| 031 | Reclamo | Adquiriente | Si hay inconsistencias |
| 032 | Recibo del bien/servicio | Adquiriente | Al recibir mercancía |
| 033 | Aceptación expresa | Adquiriente | Para hacer título valor |
| 036 | Aceptación tácita | DIAN (auto) | 3 días sin reclamo |

Para que una FE sea soporte de costos/IVA (Resolución 042/2020 art. 34):
Debe tener al menos **030 + 032 + (033 o 036)**.

## Anexo Técnico DIAN

Versión vigente al momento de este código: **1.9** (Resolución 000165 de 2023).

Revisar la versión actual en:
https://www.dian.gov.co/impuestos/factura-electronica/Paginas/Cara-Tecnica.aspx

**Si DIAN saca 1.10**, los archivos más probablemente impactados son:
- `xml_evento_radian.py` (estructura UBL puede cambiar)
- `firmador_xades.py` (si cambian política de firma o algoritmo)

## Pruebas

El módulo se puede testear sin enviar a DIAN real. Los tests cubren:

```bash
python -m pytest tests/test_dian_pt_certificado.py    # Cargar .p12
python -m pytest tests/test_dian_pt_cude.py           # Fórmula CUDE
python -m pytest tests/test_dian_pt_xml.py            # Estructura XML
python -m pytest tests/test_dian_pt_firma.py          # Firma criptográfica
python -m pytest tests/test_dian_pt_soap.py           # Envelope SOAP
```

Tests pendientes (requieren acceso a habilitación DIAN):
- Envío real al ambiente de habilitación.
- Validación contra los 186 escenarios.

## Costos estimados de habilitación PT (Colombia 2026)

| Item | Costo aprox |
|---|---|
| Certificado digital PT (1 año) | $300k - $500k COP |
| Constitución sociedad si no existe | $1M - $2M COP |
| Pólizas de cumplimiento (anual) | $3M - $8M COP |
| Pólizas de responsabilidad civil | $2M - $5M COP |
| Infraestructura cloud SLA 99.5% (anual) | $12M - $36M COP |
| Consultor externo experto DIAN | $5M - $15M COP |
| Personal soporte 24/7 (mes 1 + setup) | $4M - $8M COP |
| **Total año 1** | **$27M - $74M COP** |

Tiempo total estimado a producción: **6 a 12 meses** desde habilitación.

## Disclaimer

Este código es una **base de partida**, no un producto terminado. Su uso en
producción sin pasar por el proceso formal de habilitación DIAN puede
resultar en:
- Multas por emisión de documentos no válidos.
- Rechazo de soporte de IVA/costos para los clientes.
- Responsabilidad legal solidaria.

Asegúrate de tener acompañamiento legal y técnico apropiado antes de
desplegar a producción.
