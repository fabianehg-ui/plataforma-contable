"""
core/dian_fe/servicio_fe.py

Orquestador de emisión de Facturas Electrónicas de Venta (FE).

Análogo a core.dian_pt.ServicioDIAN (que envía eventos RADIAN), pero para
FACTURAS. Reusa del módulo dian_pt las piezas de bajo nivel:
  - VaultDIAN          → credenciales/certificado cifrados por empresa
  - firmar_xml         → firma XAdES-EPES
  - ClienteDIAN        → cliente SOAP (método enviar_factura → SendBillSync)
  - AuditorDIAN        → log de envíos

La dependencia va dian_fe → dian_pt (la correcta). El servicio recibe una
Factura ya construida (con totales calculados) y se encarga del resto.

Uso:

    from core.dian_fe.servicio_fe import ServicioFE
    servicio = ServicioFE(master_password="...")

    resultado = servicio.emitir_factura(nit_emisor="901038325", factura=factura)
    if resultado.exitoso:
        print(resultado.track_id, resultado.cufe)

ADVERTENCIA: igual que el resto del módulo, esto NO está habilitado por DIAN.
Los envíos van a habilitación salvo que la credencial sea de producción.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.dian_pt.vault import VaultDIAN, CredencialesNoEncontradas
from core.dian_pt.auditoria import AuditorDIAN
from core.dian_pt.firmador_xades import firmar_xml
from core.dian_pt.cliente_dian_soap import ClienteDIAN

from .xml_factura import generar_xml_factura
from .cufe_calculator import calcular_cufe_desde_factura


@dataclass
class ResultadoEmisionFE:
    """Resultado simplificado de la emisión de una factura."""
    exitoso: bool
    track_id: Optional[str] = None
    cufe: Optional[str] = None
    numero_factura: Optional[str] = None
    error: Optional[str] = None
    detalle_dian: Optional[dict] = None
    xml_enviado_bytes: int = 0
    duracion_segundos: float = 0.0


class ServicioFE:
    """
    Servicio multi-tenant para emisión de facturas electrónicas a DIAN.

    Comparte el mismo vault y auditor que ServicioDIAN (mismas rutas en disco),
    de modo que las credenciales registradas para eventos RADIAN sirven también
    para facturas. No mantiene certificados en memoria.
    """

    def __init__(self, master_password: str, timeout_segundos: int = 60):
        self.vault = VaultDIAN(master_password)
        self.auditor = AuditorDIAN()
        self.timeout = timeout_segundos

    # --- Gestión de clientes (delega en el vault compartido) -----------
    def listar_clientes(self) -> list[dict]:
        return self.vault.listar_clientes()

    # --- Emisión -------------------------------------------------------
    def emitir_factura(
        self,
        nit_emisor: str,
        factura,
        calcular_cufe_si_falta: bool = True,
    ) -> ResultadoEmisionFE:
        """
        Genera, firma y envía una factura electrónica a DIAN.

        Args:
            nit_emisor: NIT de la empresa emisora. Debe estar registrada en el
                vault (vía ServicioDIAN.registrar_cliente o equivalente).
            factura: instancia de core.dian_fe.Factura con sus totales ya
                calculados (factura.calcular_totales()).
            calcular_cufe_si_falta: si la factura no trae CUFE, lo calcula.

        Returns:
            ResultadoEmisionFE con track_id y cufe si fue aceptada.
        """
        inicio = datetime.now()
        numero = None
        try:
            numero = factura.numero_factura
        except Exception:
            numero = getattr(factura, "cufe", None)

        # 1) Cargar credenciales del emisor
        try:
            creds = self.vault.cargar(nit_emisor)
        except CredencialesNoEncontradas as e:
            self.auditor.registrar_error(
                nit_cliente=nit_emisor,
                mensaje="Credenciales no encontradas (FE)",
                detalle=str(e),
            )
            return ResultadoEmisionFE(
                exitoso=False,
                numero_factura=numero,
                error=f"Emisor {nit_emisor} no registrado en la plataforma",
            )

        cert = creds.cargar_certificado()

        # 2) Completar credenciales DIAN en la factura si vienen vacías
        if not getattr(factura, "software_id", ""):
            factura.software_id = creds.software_id
        if not getattr(factura, "software_security_code", ""):
            factura.software_security_code = creds.software_security_code
        if not getattr(factura, "clave_tecnica", ""):
            factura.clave_tecnica = creds.clave_tecnica
        # ambiente del modelo FE: "1"=prod, "2"=habilitación
        if creds.ambiente == "produccion":
            factura.ambiente = "1"
        else:
            factura.ambiente = "2"

        # 3) Calcular CUFE si falta
        if calcular_cufe_si_falta and not getattr(factura, "cufe", ""):
            try:
                factura.cufe = calcular_cufe_desde_factura(
                    factura, ambiente=creds.ambiente
                )
            except Exception as e:
                self.auditor.registrar_error(
                    nit_cliente=nit_emisor,
                    mensaje="Error calculando CUFE",
                    detalle=str(e),
                )
                return ResultadoEmisionFE(
                    exitoso=False, numero_factura=numero,
                    error=f"Error CUFE: {e}",
                )

        # 4) Generar XML UBL
        try:
            xml_sin_firma = generar_xml_factura(factura)
        except Exception as e:
            self.auditor.registrar_error(
                nit_cliente=nit_emisor,
                mensaje="Error generando XML de factura",
                detalle=str(e),
            )
            return ResultadoEmisionFE(
                exitoso=False, numero_factura=numero, cufe=factura.cufe,
                error=f"Error XML: {e}",
            )

        # 5) Firmar
        try:
            xml_firmado = firmar_xml(xml_sin_firma, cert)
        except Exception as e:
            self.auditor.registrar_error(
                nit_cliente=nit_emisor,
                mensaje="Error firmando factura",
                detalle=str(e),
            )
            return ResultadoEmisionFE(
                exitoso=False, numero_factura=numero, cufe=factura.cufe,
                error=f"Error firma: {e}",
            )

        # 6) Enviar (SendBillSync)
        cliente_soap = ClienteDIAN(
            certificado=cert, ambiente=creds.ambiente, timeout=self.timeout
        )
        nombre = (numero or "factura").replace(" ", "_")
        respuesta = cliente_soap.enviar_factura(
            xml_firmado, nombre_archivo=nombre
        )

        # 7) Auditar (reusa el registro de envío del auditor)
        try:
            self.auditor.registrar_envio_evento(
                nit_cliente=nit_emisor,
                tipo_evento="FE",  # marca de factura electrónica
                xml_enviado=xml_firmado,
                exitoso=respuesta.exitoso,
                track_id=respuesta.track_id,
                cude_evento=factura.cufe,
                cufe_factura=factura.cufe,
                http_status=respuesta.http_status,
                status_dian=respuesta.status_code,
                error_detalle=respuesta.error_message,
            )
        except Exception:
            # No interrumpir el resultado por un fallo de auditoría
            pass

        duracion = (datetime.now() - inicio).total_seconds()
        return ResultadoEmisionFE(
            exitoso=respuesta.exitoso,
            track_id=respuesta.track_id,
            cufe=factura.cufe,
            numero_factura=numero,
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
