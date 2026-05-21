"""
app_pages/11_Factura_Electronica.py

Placeholder de la UI para emisión de facturas electrónicas (FE).

El backend ya está en core/dian_fe/ pero falta:
  - UI para crear/editar facturas
  - UI para emitir notas crédito y notas débito
  - Extender cliente SOAP con SendBillSync
  - UI para ver historial de facturas emitidas

Cuando esté la UI completa, este archivo se reemplaza.
"""
import streamlit as st


st.title("🧾 Facturación Electrónica DIAN")
st.caption(
    "Emisión de Facturas Electrónicas de Venta (FE), Notas Crédito y Notas Débito "
    "como software propio ante DIAN."
)

st.warning(
    "🚧 **Módulo en desarrollo**\n\n"
    "El backend técnico inicial está construido en `core/dian_fe/` (1.517 líneas):\n"
    "- Modelos: Factura, LineaFactura, ParteFE, Resolucion ✅\n"
    "- Cálculo CUFE (SHA-384 con campos DIAN) ✅\n"
    "- Generación XML UBL 2.1 con DianExtensions ✅\n"
    "- Cálculo automático SoftwareSecurityCode ✅\n"
    "- QR Code para validación pública DIAN ✅\n"
    "- Integración con firmador XAdES de `core/dian_pt/` ✅\n\n"
    "**Pendiente:**\n"
    "1. Generador de Notas Crédito (`xml_nota_credito.py`)\n"
    "2. Generador de Notas Débito (`xml_nota_debito.py`)\n"
    "3. Cliente SOAP con método `SendBillSync` para facturas\n"
    "4. Pasar el set de habilitación DIAN (50 escenarios)\n"
    "5. Esta interfaz Streamlit\n\n"
    "Ver `core/dian_fe/README.md` para detalles del proceso."
)

st.markdown("---")

st.markdown("### Configuración JIPER ya almacenada")

col1, col2 = st.columns(2)
with col1:
    st.markdown("""
    **Datos software propio:**
    - Software ID: `aa20f88a-390b-4b48-8e2b-60560f126a36`
    - PIN del SW: `86818`
    - Clave técnica: `fc8eac422eba16e22ffd8c6f94b3f40a6e38162c`
    - TestSetId: `fa0e4d06-89cf-4b88-ad9f-542bef612d32`
    """)
with col2:
    st.markdown("""
    **Resolución de numeración:**
    - Número: 18760000001
    - Prefijo: SETP
    - Rango: 990000000 - 995000000
    - Vigencia: 19/01/2019 - 19/01/2030
    """)

st.markdown("### Set de pruebas DIAN")
st.info(
    "**Estado actual:** En proceso\n\n"
    "**Documentos requeridos:** 30 Facturas Electrónicas + 10 Notas Crédito + 10 Notas Débito = 50 documentos\n\n"
    "Para pasar el set, cada documento debe ser aceptado por DIAN tras envío al "
    "ambiente de habilitación. DIAN tiene una pantalla de avance que muestra qué "
    "escenarios faltan."
)

with st.expander("🔧 Uso temporal vía script Python"):
    st.code("""
from core.dian_fe import (
    Factura, LineaFactura, ParteFE, Resolucion, MedioPago, ImpuestoLinea,
    calcular_cufe_desde_factura, generar_xml_factura,
    TIPO_DOC_NIT, ORG_JURIDICA, ORG_NATURAL, RESP_IVA,
    FORMA_PAGO_CONTADO, MEDIO_PAGO_EFECTIVO,
)
from core.dian_pt import cargar_p12, firmar_xml
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# 1) Resolución JIPER
resolucion = Resolucion(
    numero="18760000001",
    prefijo="SETP",
    rango_desde=990000000,
    rango_hasta=995000000,
    fecha_desde=datetime(2019, 1, 19),
    fecha_hasta=datetime(2030, 1, 19),
    clave_tecnica="fc8eac422eba16e22ffd8c6f94b3f40a6e38162c",
)

# 2) Emisor JIPER
jiper = ParteFE(
    numero_documento="901038325", dv="1",
    tipo_documento_id=TIPO_DOC_NIT, razon_social="JIPER SAS",
    tipo_organizacion=ORG_JURIDICA, responsabilidades=[RESP_IVA],
    direccion="CALLE 50 # 50-50", municipio_codigo="05001",
)

# 3) Adquiriente
cliente = ParteFE(
    numero_documento="222222222222",
    tipo_documento_id=TIPO_DOC_NIT,
    razon_social="CONSUMIDOR FINAL",
    tipo_organizacion=ORG_NATURAL,
)

# 4) Construir factura
tz = timezone(timedelta(hours=-5))
factura = Factura(
    folio=990000001,
    fecha_emision=datetime(2026, 5, 19, 12, 30, tzinfo=tz),
    resolucion=resolucion,
    emisor=jiper,
    adquiriente=cliente,
    lineas=[
        LineaFactura(
            numero_linea=1, codigo_producto="HAM-001",
            descripcion="Hamburguesa de la casa",
            cantidad=Decimal("2"),
            precio_unitario=Decimal("25000"),
            impuestos=[ImpuestoLinea.inc_8_porciento(Decimal("50000"))],
        ),
    ],
    software_id="aa20f88a-390b-4b48-8e2b-60560f126a36",
    software_security_code="86818",
    clave_tecnica="fc8eac422eba16e22ffd8c6f94b3f40a6e38162c",
    ambiente="2",
)

factura.calcular_totales()
factura.cufe = calcular_cufe_desde_factura(factura)

xml = generar_xml_factura(factura)
cert = cargar_p12("jiper.p12", "<password>")
xml_firmado = firmar_xml(xml, cert)
""", language="python")
