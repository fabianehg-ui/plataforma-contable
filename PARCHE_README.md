# Parche v8 — JIPER + PT DIAN Multi-tenant (mayo 2026)

Acumula todo el trabajo previo + sistema multi-tenant completo.

## 🆕 Nuevo en este turno: Multi-tenant

3 archivos nuevos en `core/dian_pt/`:

### `vault.py` (440 líneas)
Almacén cifrado AES-256-GCM de credenciales DIAN por cliente.
- PBKDF2-HMAC-SHA256 con 300k iteraciones.
- Salt único por cliente, nonce único por operación.
- Verifica que NIT del cert coincida con NIT declarado.
- Sobreescritura con basura antes de eliminar (defensa básica).

### `auditoria.py` (353 líneas)
Logs JSONL mensuales de todas las operaciones DIAN.
- Hash SHA-256 del XML enviado (no guarda el XML completo, datos sensibles).
- Consulta filtrada por cliente, tipo, fecha.
- Resumen estadístico mensual por cliente.
- Retención automática NO (DIAN exige 5 años, configurar archivado externo).

### `servicio_multi_tenant.py` (448 líneas)
Orquestador que une vault + auditoría + módulo dian_pt.
API simple para la UI:
```python
servicio = ServicioDIAN(master_password="...")
servicio.registrar_cliente(nit="...", p12_bytes=..., ...)
resultado = servicio.enviar_evento(nit_cliente="...", tipo_evento="030", ...)
```
- Carga creds del vault solo cuando se necesita (no en memoria persistente).
- Auditoría automática de cada operación.
- Calcula DV con algoritmo oficial DIAN.
- Maneja consecutivos por cliente.

## Modelo conceptual

```
Cliente JIPER ─┐
               │
Cliente B ─────┼─→ Tu Plataforma (puente) ──→ DIAN
               │   - Vault cifrado AES-256
Cliente C ─────┘   - Cada cliente con SU certificado
                   - Plataforma solo facilita, no es PT
```

Tu plataforma es **software puente**, NO Proveedor Tecnológico.
Cada cliente:
1. Compra su certificado .p12.
2. Hace su trámite ante DIAN (recibe Software ID + PIN + Clave técnica).
3. Sube sus 5 credenciales a tu plataforma.
4. La plataforma firma con SU certificado y envía a DIAN en su nombre.

**Ventajas vs Modo PT:**
- Sin habilitación de tu empresa ante DIAN.
- Sin pólizas obligatorias.
- Sin SLA 99.5%.
- Tú no eres responsable solidario.

## Estado del módulo `core/dian_pt/`

| Archivo | Líneas | Función |
|---|---|---|
| `__init__.py` | 177 | API pública |
| `certificado.py` | 284 | Cargar .p12 |
| `cude_calculator.py` | 209 | Hash SHA-384 DIAN |
| `xml_evento_radian.py` | 575 | XML UBL 2.1 |
| `firmador_xades.py` | 479 | Firma XAdES-EPES |
| `cliente_dian_soap.py` | 532 | Cliente SOAP+WSSecurity |
| **`vault.py`** | **440** | **🆕 Vault cifrado** |
| **`auditoria.py`** | **353** | **🆕 Logs JSONL** |
| **`servicio_multi_tenant.py`** | **448** | **🆕 Orquestador** |
| **Total** | **3,497** | |

## Validaciones de esta sesión

- ✅ Vault: guardar/cargar/eliminar, multi-tenant, password incorrecta detectada, NIT mismatch detectado.
- ✅ Auditor: registro JSONL, consulta filtrada, resumen estadístico.
- ✅ Orquestador: registro de cliente, pipeline completo (vault→CUDE→XML→firma→envelope), auditoría automática.
- ✅ 51 tests previos pasan, 0 regresiones.

## Lo que TODAVÍA falta para producción

❌ UI Streamlit para registrar/listar/usar clientes.
❌ Persistencia de consecutivos en SQLite (ahora son en memoria).
❌ Página de auditoría para revisar envíos pasados.
❌ Pruebas reales contra ambiente de habilitación DIAN.
❌ Actualizar hash de política de firma DIAN al vigente.
❌ Acompañamiento del consultor DIAN para pasar habilitación cliente por cliente.

## Próximos pasos sugeridos

1. **Antes que nada**: que JIPER se habilite como autofacturador en DIAN
   (es ELLOS quien tramita, no tu plataforma).
2. JIPER recibe sus 5 credenciales DIAN (Software ID, PIN, Clave técnica + RUT con DV + Certificado).
3. Usas el servicio para registrar JIPER en el vault.
4. Primer envío al ambiente de habilitación.
5. Iteras con DIAN hasta que acepte (semanas).
6. Replicar el proceso para cada cliente nuevo.

## Uso desde código (sin UI todavía)

```python
from core.dian_pt import ServicioDIAN
from datetime import datetime, timezone, timedelta

# Master password se configura en variable de entorno
import os
servicio = ServicioDIAN(master_password=os.environ["DIAN_MASTER_PWD"])

# Registrar cliente (una sola vez)
with open("jiper.p12", "rb") as f:
    p12 = f.read()

servicio.registrar_cliente(
    nit="901038325",
    razon_social="JIPER SAS",
    p12_bytes=p12,
    p12_password=os.environ["JIPER_P12_PWD"],
    software_id="...",  # DIAN lo da
    software_security_code="...",  # DIAN lo da
    clave_tecnica="...",  # DIAN la da
    ambiente="habilitacion",
)

# Enviar acuse 030
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
```
