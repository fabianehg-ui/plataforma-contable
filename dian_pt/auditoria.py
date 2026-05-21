"""
core/dian_pt/auditoria.py

Sistema de auditoría de envíos a DIAN por cliente.

Registra cada operación (envío de evento, consulta, error) con:
  - Timestamp UTC
  - NIT del cliente
  - Tipo de operación
  - TrackId DIAN (si aplica)
  - Estado / resultado
  - Hash del XML enviado (para trazabilidad sin guardar el XML completo)

Almacenamiento:
  core/data/auditoria/dian_envios_YYYY-MM.jsonl

Formato: una línea JSON por evento (JSONL) — fácil de:
  - Anexar (append-only)
  - Leer por streaming
  - Importar a herramientas de análisis

⚠️ NO guardamos el XML completo enviado a DIAN (puede contener datos
sensibles). Solo el hash SHA-256 y los metadatos.

Retención:
  - DIAN exige 5 años. El módulo no borra archivos automáticamente.
  - El operador debe configurar política de archivado (zip + storage frío).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal


# ════════════════════════════════════════════════════════════════════════
# Tipos de operación auditables
# ════════════════════════════════════════════════════════════════════════

TIPOS_OPERACION = Literal[
    "envio_evento_030",
    "envio_evento_031",
    "envio_evento_032",
    "envio_evento_033",
    "consulta_estado",
    "carga_certificado",
    "renovacion_certificado",
    "error",
]


# ════════════════════════════════════════════════════════════════════════
# Estructura del registro
# ════════════════════════════════════════════════════════════════════════

@dataclass
class RegistroAuditoria:
    """Una entrada de auditoría."""
    timestamp_utc: str                          # ISO 8601 UTC
    nit_cliente: str                            # NIT de la empresa cliente
    tipo_operacion: str                         # Ver TIPOS_OPERACION
    exitoso: bool
    track_id: Optional[str] = None              # Track ID de DIAN si aplica
    cufe_factura: Optional[str] = None          # CUFE de la factura referida
    cude_evento: Optional[str] = None           # CUDE del evento generado
    xml_hash_sha256: Optional[str] = None       # Hash del XML enviado
    xml_tamaño_bytes: Optional[int] = None
    http_status: Optional[int] = None           # Código HTTP de la respuesta
    status_dian: Optional[str] = None           # StatusCode DIAN
    mensaje: Optional[str] = None               # Mensaje libre
    error_detalle: Optional[str] = None         # Solo si exitoso=False
    metadata: dict = field(default_factory=dict)  # Cualquier extra

    def to_jsonl(self) -> str:
        """Convierte a una línea JSON (sin newline final)."""
        return json.dumps(asdict(self), ensure_ascii=False)


# ════════════════════════════════════════════════════════════════════════
# Auditor
# ════════════════════════════════════════════════════════════════════════

class AuditorDIAN:
    """
    Registra operaciones DIAN en archivos JSONL mensuales.

    Uso:
        auditor = AuditorDIAN()
        auditor.registrar_envio_evento(
            nit_cliente="901038325",
            tipo_evento="030",
            xml_enviado=xml_bytes,
            track_id="abc123",
            exitoso=True,
            cude_evento="def456...",
            cufe_factura="789xyz...",
        )
    """

    def __init__(self, ruta_base: Optional[Path] = None):
        """
        Args:
            ruta_base: directorio donde guardar los logs.
                        Default: core/data/auditoria/
        """
        self.ruta_base = ruta_base or self._ruta_default()
        self.ruta_base.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _ruta_default() -> Path:
        aqui = Path(__file__).resolve()
        return aqui.parent.parent.parent / "core" / "data" / "auditoria"

    def _archivo_actual(self) -> Path:
        """Archivo del mes actual: dian_envios_YYYY-MM.jsonl"""
        ahora = datetime.now(timezone.utc)
        nombre = f"dian_envios_{ahora.strftime('%Y-%m')}.jsonl"
        return self.ruta_base / nombre

    # ════════════════════════════════════════════════════════════════
    # Registro de operaciones
    # ════════════════════════════════════════════════════════════════

    def registrar(self, registro: RegistroAuditoria) -> None:
        """Anexa un registro al archivo del mes actual."""
        archivo = self._archivo_actual()
        with open(archivo, "a", encoding="utf-8") as f:
            f.write(registro.to_jsonl() + "\n")

    def registrar_envio_evento(
        self,
        nit_cliente: str,
        tipo_evento: str,
        xml_enviado: bytes,
        exitoso: bool,
        track_id: Optional[str] = None,
        cude_evento: Optional[str] = None,
        cufe_factura: Optional[str] = None,
        http_status: Optional[int] = None,
        status_dian: Optional[str] = None,
        error_detalle: Optional[str] = None,
        mensaje: Optional[str] = None,
    ) -> RegistroAuditoria:
        """
        Registra un envío de evento RADIAN.

        Calcula automáticamente el hash SHA-256 del XML enviado.
        """
        registro = RegistroAuditoria(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            nit_cliente=nit_cliente,
            tipo_operacion=f"envio_evento_{tipo_evento}",
            exitoso=exitoso,
            track_id=track_id,
            cufe_factura=cufe_factura,
            cude_evento=cude_evento,
            xml_hash_sha256=hashlib.sha256(xml_enviado).hexdigest(),
            xml_tamaño_bytes=len(xml_enviado),
            http_status=http_status,
            status_dian=status_dian,
            error_detalle=error_detalle,
            mensaje=mensaje,
        )
        self.registrar(registro)
        return registro

    def registrar_consulta(
        self,
        nit_cliente: str,
        track_id: str,
        estado: str,
        exitoso: bool = True,
        error_detalle: Optional[str] = None,
    ) -> RegistroAuditoria:
        """Registra una consulta de estado por TrackId."""
        registro = RegistroAuditoria(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            nit_cliente=nit_cliente,
            tipo_operacion="consulta_estado",
            exitoso=exitoso,
            track_id=track_id,
            status_dian=estado,
            error_detalle=error_detalle,
        )
        self.registrar(registro)
        return registro

    def registrar_carga_certificado(
        self,
        nit_cliente: str,
        huella_sha1: str,
        fecha_vencimiento: str,
        exitoso: bool = True,
        error_detalle: Optional[str] = None,
    ) -> RegistroAuditoria:
        """Registra la carga (o renovación) de un certificado."""
        registro = RegistroAuditoria(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            nit_cliente=nit_cliente,
            tipo_operacion="carga_certificado",
            exitoso=exitoso,
            error_detalle=error_detalle,
            metadata={
                "huella_sha1": huella_sha1,
                "fecha_vencimiento": fecha_vencimiento,
            },
        )
        self.registrar(registro)
        return registro

    def registrar_error(
        self,
        nit_cliente: str,
        mensaje: str,
        detalle: Optional[str] = None,
    ) -> RegistroAuditoria:
        """Registra un error genérico."""
        registro = RegistroAuditoria(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            nit_cliente=nit_cliente,
            tipo_operacion="error",
            exitoso=False,
            mensaje=mensaje,
            error_detalle=detalle,
        )
        self.registrar(registro)
        return registro

    # ════════════════════════════════════════════════════════════════
    # Consulta
    # ════════════════════════════════════════════════════════════════

    def consultar_por_cliente(
        self,
        nit_cliente: str,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        tipo_operacion: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict]:
        """
        Devuelve los registros de un cliente filtrados por fecha y tipo.

        Recorre los archivos JSONL del rango. Para volúmenes grandes
        (>100k registros/mes), considera migrar a SQLite.

        Returns:
            Lista de dicts con los registros (los más recientes primero).
        """
        resultados = []

        # Determinar qué meses leer
        if desde is None:
            desde = datetime.now(timezone.utc).replace(day=1)
        if hasta is None:
            hasta = datetime.now(timezone.utc)

        # Recorrer archivos mensuales en el rango
        cursor = desde.replace(day=1)
        while cursor <= hasta:
            archivo = self.ruta_base / f"dian_envios_{cursor.strftime('%Y-%m')}.jsonl"
            if archivo.exists():
                with open(archivo, "r", encoding="utf-8") as f:
                    for linea in f:
                        try:
                            r = json.loads(linea)
                        except json.JSONDecodeError:
                            continue

                        if r.get("nit_cliente") != nit_cliente:
                            continue
                        if tipo_operacion and r.get("tipo_operacion") != tipo_operacion:
                            continue

                        try:
                            ts = datetime.fromisoformat(r["timestamp_utc"])
                            if ts < desde or ts > hasta:
                                continue
                        except (KeyError, ValueError):
                            pass

                        resultados.append(r)
                        if len(resultados) >= limit:
                            return resultados[::-1]

            # Avanzar al siguiente mes
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1)

        # Devolver más recientes primero
        return resultados[::-1]

    def resumen_cliente(
        self,
        nit_cliente: str,
        mes: Optional[str] = None,
    ) -> dict:
        """
        Resumen estadístico de envíos de un cliente en un mes.

        Args:
            nit_cliente: NIT.
            mes: "YYYY-MM" (default: mes actual).
        """
        if mes is None:
            mes = datetime.now(timezone.utc).strftime("%Y-%m")

        archivo = self.ruta_base / f"dian_envios_{mes}.jsonl"
        if not archivo.exists():
            return {"nit": nit_cliente, "mes": mes, "total": 0}

        stats = {
            "nit": nit_cliente,
            "mes": mes,
            "total": 0,
            "exitosos": 0,
            "fallidos": 0,
            "por_tipo": {},
            "primer_envio": None,
            "ultimo_envio": None,
        }

        with open(archivo, "r", encoding="utf-8") as f:
            for linea in f:
                try:
                    r = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if r.get("nit_cliente") != nit_cliente:
                    continue

                stats["total"] += 1
                if r.get("exitoso"):
                    stats["exitosos"] += 1
                else:
                    stats["fallidos"] += 1

                tipo = r.get("tipo_operacion", "desconocido")
                stats["por_tipo"][tipo] = stats["por_tipo"].get(tipo, 0) + 1

                ts = r.get("timestamp_utc")
                if ts:
                    if not stats["primer_envio"] or ts < stats["primer_envio"]:
                        stats["primer_envio"] = ts
                    if not stats["ultimo_envio"] or ts > stats["ultimo_envio"]:
                        stats["ultimo_envio"] = ts

        return stats
