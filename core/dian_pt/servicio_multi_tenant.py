"""
core/dian_pt/servicio_multi_tenant.py

Orquestador multi-tenant que une vault + auditoría + módulo dian_pt.

Provee una API simple para que la plataforma envíe eventos a DIAN en
nombre de múltiples empresas clientes, sin que el código de aplicación
tenga que conocer los detalles de firma/SOAP/certificados.

Uso desde la UI/aplicación:

    from core.dian_pt.servicio_multi_tenant import ServicioDIAN

    servicio = ServicioDIAN(master_password="...")

    # Enviar acuse 030 para una factura
    resultado = servicio.enviar_evento(
        nit_cliente="901038325",
        tipo_evento="030",
        cufe_factura="abc...",
        numero_factura="FE-12345",
        fecha_factura=datetime(2026, 3, 15),
        monto_factura=1500000,
        nit_proveedor="800111222",
        dv_proveedor="3",
        razon_social_proveedor="PROVEEDOR SAS",
    )

    if resultado.exitoso:
        print(f"Track ID DIAN: {resultado.track_id}")
    else:
        print(f"Error: {resultado.error}")

El servicio se encarga internamente de:
  1. Cargar credenciales cifradas del cliente desde el vault
  2. Calcular el CUDE del evento
  3. Generar el XML UBL
  4. Firmarlo con XAdES-EPES usando el cert del cliente
  5. Enviar a DIAN con SOAP+WSSecurity
  6. Registrar todo en auditoría
  7. Devolver resultado simplificado
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

from .vault import VaultDIAN, CredencialesDIAN, CredencialesNoEncontradas
from .auditoria import AuditorDIAN
from .cude_calculator import calcular_cude_evento_simple
from .xml_evento_radian import (
    EventoRadian, ParteEvento, FacturaReferida, generar_xml_evento,
    CODIGOS_RECLAMO,
)
from .firmador_xades import firmar_xml
from .cliente_dian_soap import ClienteDIAN, RespuestaDIAN


# Zona horaria Colombia (UTC-5)
TZ_BOGOTA = timezone(timedelta(hours=-5))


# ════════════════════════════════════════════════════════════════════════
# Resultado simplificado
# ════════════════════════════════════════════════════════════════════════

@dataclass
class ResultadoEnvio:
    """Resultado simplificado del envío de un evento."""
    exitoso: bool
    track_id: Optional[str] = None
    cude_evento: Optional[str] = None
    error: Optional[str] = None
    detalle_dian: Optional[dict] = None         # Status DIAN si hay
    xml_enviado_bytes: int = 0
    duracion_segundos: float = 0.0


# ════════════════════════════════════════════════════════════════════════
# Servicio principal
# ════════════════════════════════════════════════════════════════════════

class ServicioDIAN:
    """
    Servicio multi-tenant para envío de eventos RADIAN a DIAN.

    Mantiene en memoria:
      - vault (cifrado en disco)
      - auditor (logs jsonl)

    NO mantiene certificados en memoria — los descifra solo cuando se
    necesitan, los usa, y los descarta.
    """

    def __init__(
        self,
        master_password: str,
        timeout_segundos: int = 60,
        consecutivo_inicial: int = 1,
    ):
        """
        Args:
            master_password: clave para descifrar el vault.
            timeout_segundos: timeout para llamadas HTTP a DIAN.
            consecutivo_inicial: cuando no hay consecutivo persistido, empieza aquí.
        """
        self.vault = VaultDIAN(master_password)
        self.auditor = AuditorDIAN()
        self.timeout = timeout_segundos
        self._consecutivos: dict[str, int] = {}  # nit -> próximo número

    # ════════════════════════════════════════════════════════════════
    # Gestión de clientes
    # ════════════════════════════════════════════════════════════════

    def registrar_cliente(
        self,
        nit: str,
        razon_social: str,
        p12_bytes: bytes,
        p12_password: str,
        software_id: str,
        software_security_code: str,
        clave_tecnica: str,
        ambiente: Literal["habilitacion", "produccion"] = "habilitacion",
    ) -> dict:
        """
        Registra (o actualiza) las credenciales DIAN de un cliente.

        Validaciones:
          - El .p12 abre con la contraseña dada.
          - El NIT del cert coincide con el NIT declarado.
          - Las credenciales DIAN no están vacías.

        Returns:
            dict con info pública del cliente registrado.

        Raises:
            ErrorVault: si la validación falla.
        """
        if not software_id or not software_security_code or not clave_tecnica:
            raise ValueError(
                "software_id, software_security_code y clave_tecnica "
                "son obligatorios"
            )

        creds = CredencialesDIAN(
            nit=nit,
            razon_social=razon_social,
            p12_bytes=p12_bytes,
            p12_password=p12_password,
            software_id=software_id,
            software_security_code=software_security_code,
            clave_tecnica=clave_tecnica,
            ambiente=ambiente,
        )

        # Guardar (esto valida el .p12 y el NIT)
        ruta = self.vault.guardar(creds)

        # Auditar la carga del certificado
        cert = creds.cargar_certificado()
        self.auditor.registrar_carga_certificado(
            nit_cliente=nit,
            huella_sha1=cert.huella_sha1,
            fecha_vencimiento=cert.fecha_vencimiento.isoformat(),
            exitoso=True,
        )

        return {
            "nit": nit,
            "razon_social": razon_social,
            "ambiente": ambiente,
            "fecha_vencimiento_cert": cert.fecha_vencimiento.isoformat(),
            "dias_para_vencer": cert.dias_para_vencer,
            "ruta_almacenamiento": str(ruta),
        }

    def listar_clientes(self) -> list[dict]:
        """Lista todos los clientes registrados (sin descifrar credenciales)."""
        return self.vault.listar_clientes()

    def eliminar_cliente(self, nit: str) -> bool:
        """Elimina las credenciales de un cliente."""
        return self.vault.eliminar(nit)

    # ════════════════════════════════════════════════════════════════
    # Envío de eventos
    # ════════════════════════════════════════════════════════════════

    def enviar_evento(
        self,
        nit_cliente: str,
        tipo_evento: Literal["030", "031", "032", "033"],
        cufe_factura: str,
        numero_factura: str,
        fecha_factura: datetime,
        monto_factura: float,
        nit_proveedor: str,
        dv_proveedor: str,
        razon_social_proveedor: str,
        codigo_reclamo: Optional[str] = None,
        num_evento: Optional[str] = None,
    ) -> ResultadoEnvio:
        """
        Envía un evento RADIAN a DIAN en nombre del cliente.

        Args:
            nit_cliente: NIT de la empresa que emite el evento (adquiriente).
                          Debe estar registrado vía registrar_cliente().
            tipo_evento: "030", "031", "032" o "033".
            cufe_factura: CUFE SHA-384 de la factura recibida.
            numero_factura: número/folio de la factura (ej. "FE-12345").
            fecha_factura: fecha de emisión de la factura original.
            monto_factura: total bruto de la factura.
            nit_proveedor: NIT del proveedor que emitió la factura.
            dv_proveedor: dígito de verificación del proveedor.
            razon_social_proveedor: nombre del proveedor.
            codigo_reclamo: solo para evento 031. "01" a "04".
            num_evento: consecutivo del evento. Si None, se autogenera.

        Returns:
            ResultadoEnvio con track_id si fue exitoso, error si no.
        """
        inicio = datetime.now()

        # 1) Cargar credenciales del cliente
        try:
            creds = self.vault.cargar(nit_cliente)
        except CredencialesNoEncontradas as e:
            self.auditor.registrar_error(
                nit_cliente=nit_cliente,
                mensaje="Credenciales no encontradas",
                detalle=str(e),
            )
            return ResultadoEnvio(
                exitoso=False,
                error=f"Cliente {nit_cliente} no registrado en la plataforma",
            )

        # 2) Determinar consecutivo
        if num_evento is None:
            num_evento = str(self._proximo_consecutivo(nit_cliente))

        # 3) Determinar datos del adquiriente desde las credenciales
        cert = creds.cargar_certificado()
        dv_cliente = self._calcular_dv(nit_cliente)

        emisor = ParteEvento(
            nit=nit_cliente,
            dv=dv_cliente,
            razon_social=creds.razon_social,
        )
        receptor = ParteEvento(
            nit=nit_proveedor,
            dv=dv_proveedor,
            razon_social=razon_social_proveedor,
        )
        factura = FacturaReferida(
            numero=numero_factura,
            cufe=cufe_factura,
            fecha_emision=fecha_factura,
            monto_total=monto_factura,
        )

        # 4) Calcular CUDE
        ahora = datetime.now(TZ_BOGOTA).replace(microsecond=0)
        ambiente_codigo = "1" if creds.ambiente == "produccion" else "2"

        try:
            cude = calcular_cude_evento_simple(
                num_evento=num_evento,
                fecha_emision=ahora,
                nit_adquiriente=nit_cliente,
                nit_proveedor=nit_proveedor,
                clave_tecnica=creds.clave_tecnica,
                ambiente=creds.ambiente,
            )
        except ValueError as e:
            self.auditor.registrar_error(
                nit_cliente=nit_cliente,
                mensaje="Error calculando CUDE",
                detalle=str(e),
            )
            return ResultadoEnvio(exitoso=False, error=f"Error CUDE: {e}")

        # 5) Generar XML
        # En modo "puente" (no PT comercial), el cliente es su propio software
        # provider — usa SU NIT y SUS credenciales DIAN
        evento = EventoRadian(
            tipo_evento=tipo_evento,
            num_evento=num_evento,
            cude=cude,
            fecha_emision=ahora,
            emisor=emisor,
            receptor=receptor,
            factura=factura,
            software_id=creds.software_id,
            software_security_code=creds.software_security_code,
            clave_tecnica=creds.clave_tecnica,
            proveedor_tecnologico_nit=nit_cliente,  # El cliente es su propio provider
            proveedor_tecnologico_dv=dv_cliente,
            ambiente=ambiente_codigo,
            codigo_reclamo=codigo_reclamo,
        )

        try:
            xml_sin_firma = generar_xml_evento(evento)
        except ValueError as e:
            self.auditor.registrar_error(
                nit_cliente=nit_cliente,
                mensaje="Error generando XML",
                detalle=str(e),
            )
            return ResultadoEnvio(exitoso=False, error=f"Error XML: {e}")

        # 6) Firmar
        try:
            xml_firmado = firmar_xml(xml_sin_firma, cert)
        except Exception as e:
            self.auditor.registrar_error(
                nit_cliente=nit_cliente,
                mensaje="Error firmando XML",
                detalle=str(e),
            )
            return ResultadoEnvio(exitoso=False, error=f"Error firma: {e}")

        # 7) Enviar
        cliente_soap = ClienteDIAN(
            certificado=cert,
            ambiente=creds.ambiente,
            timeout=self.timeout,
        )
        respuesta = cliente_soap.enviar_evento(xml_firmado)

        # 8) Registrar en auditoría
        self.auditor.registrar_envio_evento(
            nit_cliente=nit_cliente,
            tipo_evento=tipo_evento,
            xml_enviado=xml_firmado,
            exitoso=respuesta.exitoso,
            track_id=respuesta.track_id,
            cude_evento=cude,
            cufe_factura=cufe_factura,
            http_status=respuesta.http_status,
            status_dian=respuesta.status_code,
            error_detalle=respuesta.error_message,
        )

        # 9) Construir resultado
        duracion = (datetime.now() - inicio).total_seconds()

        return ResultadoEnvio(
            exitoso=respuesta.exitoso,
            track_id=respuesta.track_id,
            cude_evento=cude,
            error=respuesta.error_message,
            detalle_dian={
                "status_code": respuesta.status_code,
                "status_description": respuesta.status_description,
                "status_message": respuesta.status_message,
                "es_valido": respuesta.es_valido,
            } if respuesta.exitoso else None,
            xml_enviado_bytes=len(xml_firmado),
            duracion_segundos=round(duracion, 2),
        )

    def consultar_estado(
        self,
        nit_cliente: str,
        track_id: str,
    ) -> dict:
        """
        Consulta el estado de un envío previo.

        Returns:
            dict con estado, fechas y errores si hay.
        """
        try:
            creds = self.vault.cargar(nit_cliente)
        except CredencialesNoEncontradas:
            return {"error": f"Cliente {nit_cliente} no registrado"}

        cert = creds.cargar_certificado()
        cliente_soap = ClienteDIAN(cert, ambiente=creds.ambiente)
        resultado = cliente_soap.consultar_estado(track_id)

        # Auditar la consulta
        self.auditor.registrar_consulta(
            nit_cliente=nit_cliente,
            track_id=track_id,
            estado=resultado.estado,
            exitoso=True,
        )

        return {
            "track_id": resultado.track_id,
            "estado": resultado.estado,
            "fecha_recepcion": resultado.fecha_recepcion,
            "fecha_procesamiento": resultado.fecha_procesamiento,
            "es_valido": resultado.es_valido,
            "errores": resultado.errores or [],
        }

    # ════════════════════════════════════════════════════════════════
    # Helpers
    # ════════════════════════════════════════════════════════════════

    def _proximo_consecutivo(self, nit: str) -> int:
        """
        Devuelve el próximo consecutivo para un cliente.

        NOTA: por ahora es en memoria. En producción debe persistirse
        en una tabla SQLite o similar para sobrevivir a reinicios y para
        garantizar atomicidad multi-thread.
        """
        actual = self._consecutivos.get(nit, 0)
        actual += 1
        self._consecutivos[nit] = actual
        return actual

    @staticmethod
    def _calcular_dv(nit: str) -> str:
        """
        Calcula el dígito de verificación DIAN para un NIT.

        Algoritmo oficial DIAN: multiplicación por pesos predefinidos
        y módulo 11.
        """
        if not nit or not nit.isdigit():
            return "0"

        pesos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
        # NIT al revés, multiplicar cada dígito por el peso correspondiente
        suma = 0
        for i, digito in enumerate(reversed(nit)):
            if i >= len(pesos):
                break
            suma += int(digito) * pesos[i]

        residuo = suma % 11
        if residuo == 0:
            return "0"
        elif residuo == 1:
            return "1"
        else:
            return str(11 - residuo)
