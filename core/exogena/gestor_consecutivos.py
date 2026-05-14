"""
Gestor de consecutivos y envíos para Información Exógena DIAN.

Maneja:
  - Consulta del siguiente consecutivo sugerido por (empresa, año, formato, tipo_envío)
  - Registro de envío después de generar el XML
  - Historial de envíos para trazabilidad

Tipos de envío DIAN (campo `rr` del nombre de archivo):
  '01' — Inicial
  '02' — Fracción
  '03' — Reemplazo
  '04' — Corrección

Uso típico:
    from gestor_consecutivos import (
        GestorConsecutivos, TIPO_ENVIO_INICIAL,
    )
    
    gc = GestorConsecutivos(supabase_client)
    
    # 1. Consultar sugerencia ANTES de generar
    info = gc.siguiente_consecutivo(empresa_id, 2025, '1001', '01')
    # info = {'ultimo_usado': 5, 'siguiente': 6}
    
    # 2. El usuario puede aceptar 6 o cambiar a otro
    consecutivo_elegido = 6  # o el que decida el contador
    
    # 3. Generar XML con ese consecutivo (ver generador_xml_v2)
    # ... xml = generar_xml_f1001(cabecera, registros)
    
    # 4. Registrar el envío DESPUÉS de generar con éxito
    envio_id = gc.registrar_envio(
        empresa_id=empresa_id,
        ano_gravable=2025,
        formato='1001', version='10', tipo_envio='01',
        consecutivo=consecutivo_elegido,
        nombre_archivo='Dmuisca_10011020260100000006.xml',
        cantidad_registros=21, valor_total=148_032_690,
    )
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import hashlib


# ================================================================
# Constantes — Tipos de envío DIAN
# ================================================================

TIPO_ENVIO_INICIAL    = '01'
TIPO_ENVIO_FRACCION   = '02'
TIPO_ENVIO_REEMPLAZO  = '03'
TIPO_ENVIO_CORRECCION = '04'

TIPOS_ENVIO_DESC = {
    '01': 'Inicial',
    '02': 'Fracción',
    '03': 'Reemplazo',
    '04': 'Corrección',
}

TIPOS_ENVIO_VALIDOS = set(TIPOS_ENVIO_DESC.keys())


# ================================================================
# Dataclasses
# ================================================================

@dataclass
class SugerenciaConsecutivo:
    """Sugerencia de consecutivo a usar al generar un XML."""
    empresa_id: str
    ano_gravable: int
    formato: str
    tipo_envio: str
    ultimo_usado: int           # 0 si nunca se ha generado
    siguiente: int              # ultimo_usado + 1
    es_primer_envio: bool       # True si ultimo_usado == 0


@dataclass
class EnvioRegistrado:
    """Información del envío que acaba de registrarse."""
    envio_id: int
    empresa_id: str
    ano_gravable: int
    formato: str
    version: str
    tipo_envio: str
    consecutivo: int
    nombre_archivo: str
    cantidad_registros: int
    valor_total: float
    fecha_generacion: datetime
    hash_md5: Optional[str] = None


# ================================================================
# Gestor principal
# ================================================================

class GestorConsecutivos:
    """
    Maneja la persistencia de consecutivos e historial de envíos
    contra Supabase usando las funciones SQL del módulo:
      - exogena_siguiente_consecutivo()
      - exogena_registrar_envio()
    """

    def __init__(self, supabase_client):
        """
        Args:
            supabase_client: cliente Supabase ya autenticado.
                             Puede ser None para modo offline (testing).
        """
        self.sb = supabase_client

    # ------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------

    def siguiente_consecutivo(
        self,
        empresa_id: str,
        ano_gravable: int,
        formato: str,
        tipo_envio: str = TIPO_ENVIO_INICIAL,
    ) -> SugerenciaConsecutivo:
        """
        Consulta el siguiente consecutivo sugerido para esta combinación.
        NO incrementa el contador — solo sugiere.
        
        Args:
            empresa_id: UUID de la empresa
            ano_gravable: 2025, 2024, etc.
            formato: '1001', '1003', '1005', etc.
            tipo_envio: '01', '02', '03', '04'
        
        Returns:
            SugerenciaConsecutivo con ultimo_usado y siguiente.
        """
        self._validar_tipo_envio(tipo_envio)
        
        if self.sb is None:
            # Modo offline / sin BD: siempre sugiere 1
            return SugerenciaConsecutivo(
                empresa_id=empresa_id, ano_gravable=ano_gravable,
                formato=formato, tipo_envio=tipo_envio,
                ultimo_usado=0, siguiente=1, es_primer_envio=True,
            )
        
        # Llamar a la función SQL
        resp = self.sb.rpc('exogena_siguiente_consecutivo', {
            'p_empresa_id': empresa_id,
            'p_ano_gravable': ano_gravable,
            'p_formato': formato,
            'p_tipo_envio': tipo_envio,
        }).execute()
        
        if not resp.data:
            # Función no devolvió nada: primer envío
            return SugerenciaConsecutivo(
                empresa_id=empresa_id, ano_gravable=ano_gravable,
                formato=formato, tipo_envio=tipo_envio,
                ultimo_usado=0, siguiente=1, es_primer_envio=True,
            )
        
        fila = resp.data[0]
        ultimo = int(fila.get('ultimo_usado') or 0)
        siguiente = int(fila.get('siguiente') or (ultimo + 1))
        
        return SugerenciaConsecutivo(
            empresa_id=empresa_id, ano_gravable=ano_gravable,
            formato=formato, tipo_envio=tipo_envio,
            ultimo_usado=ultimo, siguiente=siguiente,
            es_primer_envio=(ultimo == 0),
        )

    def sugerencias_lote(
        self,
        empresa_id: str,
        ano_gravable: int,
        formatos: list[str],
        tipo_envio: str = TIPO_ENVIO_INICIAL,
    ) -> dict[str, SugerenciaConsecutivo]:
        """
        Obtiene sugerencias para una lista de formatos (útil al preparar
        un envío masivo de los 11 formatos para una empresa).
        
        Returns:
            dict {formato: SugerenciaConsecutivo}
        """
        resultado = {}
        for fmt in formatos:
            resultado[fmt] = self.siguiente_consecutivo(
                empresa_id, ano_gravable, fmt, tipo_envio,
            )
        return resultado

    # ------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------

    def registrar_envio(
        self,
        empresa_id: str,
        ano_gravable: int,
        formato: str,
        version: str,
        tipo_envio: str,
        consecutivo: int,
        nombre_archivo: str,
        cantidad_registros: int,
        valor_total: float,
        xml_content: Optional[str] = None,
        archivo_xml_path: Optional[str] = None,
        generado_por: Optional[str] = None,
    ) -> EnvioRegistrado:
        """
        Registra un envío DESPUÉS de generar el XML con éxito.
        Falla si el consecutivo ya fue usado para esa combinación.
        
        Args:
            xml_content: opcional, si se pasa se calcula el hash MD5.
            archivo_xml_path: opcional, ruta del archivo en disco o bucket.
            generado_por: opcional, UUID del usuario que generó.
        
        Returns:
            EnvioRegistrado con el ID del envío.
        
        Raises:
            ValueError: si el consecutivo ya está en uso.
        """
        self._validar_tipo_envio(tipo_envio)
        
        hash_md5 = None
        if xml_content is not None:
            if isinstance(xml_content, str):
                xml_content = xml_content.encode('ISO-8859-1')
            hash_md5 = hashlib.md5(xml_content).hexdigest()
        
        if self.sb is None:
            # Modo offline: devolver objeto sin persistir
            return EnvioRegistrado(
                envio_id=-1,
                empresa_id=empresa_id, ano_gravable=ano_gravable,
                formato=formato, version=version, tipo_envio=tipo_envio,
                consecutivo=consecutivo, nombre_archivo=nombre_archivo,
                cantidad_registros=cantidad_registros, valor_total=valor_total,
                fecha_generacion=datetime.now(), hash_md5=hash_md5,
            )
        
        try:
            resp = self.sb.rpc('exogena_registrar_envio', {
                'p_empresa_id': empresa_id,
                'p_ano_gravable': ano_gravable,
                'p_formato': formato,
                'p_version': version,
                'p_tipo_envio': tipo_envio,
                'p_consecutivo': consecutivo,
                'p_nombre_archivo': nombre_archivo,
                'p_cantidad_registros': cantidad_registros,
                'p_valor_total': float(valor_total),
                'p_hash_md5': hash_md5,
                'p_archivo_xml_path': archivo_xml_path,
                'p_generado_por': generado_por,
            }).execute()
        except Exception as e:
            mensaje = str(e)
            if 'ya fue usado' in mensaje.lower() or 'duplicate' in mensaje.lower():
                raise ValueError(
                    f"El consecutivo {consecutivo} ya fue usado para F{formato} "
                    f"tipo_envío {tipo_envio} en {ano_gravable}. "
                    f"Use uno mayor o cambie el tipo de envío."
                ) from e
            raise
        
        envio_id = resp.data if isinstance(resp.data, int) else (
            resp.data[0] if isinstance(resp.data, list) and resp.data else None
        )
        
        return EnvioRegistrado(
            envio_id=envio_id or -1,
            empresa_id=empresa_id, ano_gravable=ano_gravable,
            formato=formato, version=version, tipo_envio=tipo_envio,
            consecutivo=consecutivo, nombre_archivo=nombre_archivo,
            cantidad_registros=cantidad_registros, valor_total=valor_total,
            fecha_generacion=datetime.now(), hash_md5=hash_md5,
        )

    # ------------------------------------------------------------
    # Consulta de historial
    # ------------------------------------------------------------

    def listar_envios(
        self,
        empresa_id: str,
        ano_gravable: Optional[int] = None,
        formato: Optional[str] = None,
        limite: int = 100,
    ) -> list[dict]:
        """Lista los envíos previos de la empresa, opcionalmente filtrados."""
        if self.sb is None:
            return []
        
        q = self.sb.from_('exogena_envios').select('*').eq('empresa_id', empresa_id)
        if ano_gravable is not None:
            q = q.eq('ano_gravable', ano_gravable)
        if formato is not None:
            q = q.eq('formato', formato)
        q = q.order('fecha_generacion', desc=True).limit(limite)
        
        resp = q.execute()
        return resp.data or []

    # ------------------------------------------------------------
    # Validación interna
    # ------------------------------------------------------------

    @staticmethod
    def _validar_tipo_envio(tipo: str):
        if tipo not in TIPOS_ENVIO_VALIDOS:
            raise ValueError(
                f"Tipo de envío inválido: '{tipo}'. "
                f"Debe ser uno de: {sorted(TIPOS_ENVIO_VALIDOS)} "
                f"({', '.join(f'{k}={v}' for k,v in TIPOS_ENVIO_DESC.items())})"
            )

    @staticmethod
    def validar_consecutivo(consecutivo: int) -> int:
        """Valida que el consecutivo esté en rango aceptado por DIAN (1 a 99999999)."""
        if not isinstance(consecutivo, int) or consecutivo < 1 or consecutivo > 99_999_999:
            raise ValueError(
                f"Consecutivo inválido: {consecutivo}. "
                f"Debe ser entero entre 1 y 99999999."
            )
        return consecutivo
