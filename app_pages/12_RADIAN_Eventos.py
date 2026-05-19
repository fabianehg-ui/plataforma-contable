"""
app_pages/10_RADIAN_Eventos.py

Placeholder de la UI para emisión de eventos RADIAN (030/032/033).

El backend ya está en core/dian_pt/ pero falta:
  - UI para registrar credenciales DIAN de cada empresa (vault)
  - UI para subir Excel del Token y filtrar facturas a acusar
  - UI para disparar envíos masivos
  - UI para consultar estado de envíos por TrackId
  - UI para ver auditoría de envíos

Cuando esté la UI completa, este archivo se reemplaza.
"""
import streamlit as st


st.title("📨 RADIAN Eventos — Emisión de Acuses")
st.caption(
    "Envío de eventos RADIAN (030 Acuse de recibo, 032 Recibo del bien, "
    "033 Aceptación expresa) ante DIAN."
)

st.warning(
    "🚧 **Módulo en desarrollo**\n\n"
    "El backend técnico está construido en `core/dian_pt/` (3.497 líneas):\n"
    "- Manejo de certificado .p12 ✅\n"
    "- Cálculo CUDE de eventos ✅\n"
    "- Generación XML UBL 2.1 ✅\n"
    "- Firma XAdES-EPES ✅\n"
    "- Cliente SOAP a DIAN ✅\n"
    "- Vault cifrado AES-256 multi-empresa ✅\n"
    "- Auditoría JSONL ✅\n"
    "- Orquestador multi-tenant ✅\n\n"
    "**Pendiente:**\n"
    "1. Conseguir certificado digital .p12 real de cada empresa cliente.\n"
    "2. Solicitar habilitación de Recepción Electrónica a DIAN.\n"
    "3. Pasar el set de pruebas DIAN (escenarios).\n"
    "4. Construir esta interfaz Streamlit cuando lo anterior esté listo.\n\n"
    "Ver `core/dian_pt/README.md` para detalles del proceso."
)

st.markdown("---")

with st.expander("ℹ️ Cómo funcionará este módulo cuando esté disponible"):
    st.markdown("""
    **Paso 1 — Configuración (una sola vez por empresa):**
    - Subir certificado digital `.p12` de la empresa.
    - Ingresar PIN del software (de DIAN).
    - Ingresar Clave técnica (de DIAN).
    - El sistema cifra todo y lo guarda en `core/data/empresas/{NIT}/credenciales_dian.enc`.
    
    **Paso 2 — Emisión masiva:**
    - Subir Excel del Token DIAN.
    - Filtrar recibidas con medio pago 02 (crédito).
    - Ver qué facturas ya tienen acuse y cuáles no.
    - Seleccionar las que faltan y emitir los 3 eventos (030, 032, 033) para cada una.
    
    **Paso 3 — Seguimiento:**
    - Ver track-id de DIAN por cada envío.
    - Consultar estado de envíos previos.
    - Descargar auditoría mensual de operaciones.
    """)

with st.expander("🔧 Uso temporal vía script Python (mientras esté la UI)"):
    st.code("""
from core.dian_pt import ServicioDIAN
import os

# Inicializar
servicio = ServicioDIAN(master_password=os.environ["DIAN_MASTER_PWD"])

# Registrar cliente (una sola vez)
servicio.registrar_cliente(
    nit="901038325",
    razon_social="JIPER SAS",
    p12_bytes=open("jiper.p12", "rb").read(),
    p12_password="...",
    software_id="aa20f88a-390b-4b48-8e2b-60560f126a36",
    software_security_code="86818",
    clave_tecnica="fc8eac422eba16e22ffd8c6f94b3f40a6e38162c",
    ambiente="habilitacion",
)

# Enviar acuse 030
from datetime import datetime, timezone, timedelta
tz = timezone(timedelta(hours=-5))

resultado = servicio.enviar_evento(
    nit_cliente="901038325",
    tipo_evento="030",
    cufe_factura="<CUFE del proveedor>",
    numero_factura="FE-12345",
    fecha_factura=datetime(2026, 3, 15, tzinfo=tz),
    monto_factura=1500000,
    nit_proveedor="800111222",
    dv_proveedor="3",
    razon_social_proveedor="PROVEEDOR SAS",
)
print(f"Track ID: {resultado.track_id}")
""", language="python")
