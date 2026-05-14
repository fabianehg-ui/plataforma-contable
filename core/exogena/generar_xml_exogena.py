"""
Orquestador de generación de XMLs Exógena.

Une el `GestorConsecutivos` con el `generador_xml_v2` para que la UI haga
una sola llamada de alto nivel:

    from generar_xml_exogena import generar_xml_con_consecutivo
    
    resultado = generar_xml_con_consecutivo(
        gestor=gc,
        cabecera_base=cab_base,
        formato='1001',
        registros=lista_de_registros,
        empresa_id=empresa_id,
        consecutivo=None,           # auto-asigna siguiente
        tipo_envio='01',
        confirmar_y_registrar=True,
    )
    
    # resultado tiene:
    #   xml: str            — contenido del XML
    #   nombre_archivo: str — Dmuisca_XXXXXXXXXXX.xml
    #   consecutivo_usado: int
    #   envio_id: int       — ID en la BD
    #   valor_total: float

Flujo típico para la UI:
    1. Usuario selecciona formato + tipo_envio
    2. UI llama `sugerir_consecutivo()` → muestra "Siguiente: 6"
    3. Usuario confirma o cambia
    4. UI llama `generar_xml_con_consecutivo(consecutivo=elegido)`
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Any

from generador_xml_v2 import (
    CabeceraXML, construir_nombre_archivo, guardar_xml,
    generar_xml_f1001, generar_xml_f1003, generar_xml_f1005, generar_xml_f1006,
    generar_xml_f1007, generar_xml_f1008, generar_xml_f1009,
    generar_xml_f1011, generar_xml_f1012, generar_xml_f1647, generar_xml_f2276,
    FORMATOS_CONFIG,
)
from gestor_consecutivos import (
    GestorConsecutivos, SugerenciaConsecutivo, EnvioRegistrado,
    TIPO_ENVIO_INICIAL, TIPOS_ENVIO_VALIDOS, TIPOS_ENVIO_DESC,
)


# ================================================================
# Mapeo formato → función generadora
# ================================================================

GENERADORES = {
    '1001': generar_xml_f1001,
    '1003': generar_xml_f1003,
    '1005': generar_xml_f1005,
    '1006': generar_xml_f1006,
    '1007': generar_xml_f1007,
    '1008': generar_xml_f1008,
    '1009': generar_xml_f1009,
    '1011': generar_xml_f1011,
    '1012': generar_xml_f1012,
    '1647': generar_xml_f1647,
    '2276': generar_xml_f2276,
}


# ================================================================
# Resultado de generar un XML con consecutivo
# ================================================================

@dataclass
class ResultadoGeneracion:
    """Resultado de generar un XML con el sistema de consecutivos."""
    formato: str
    version: str
    tipo_envio: str
    consecutivo_usado: int
    nombre_archivo: str
    xml: str
    cantidad_registros: int
    valor_total: float
    envio_id: Optional[int] = None          # None si no se registró en BD
    ruta_archivo: Optional[Path] = None     # ruta si se guardó en disco
    fecha_generacion: datetime = None


# ================================================================
# API principal
# ================================================================

def sugerir_consecutivo(
    gestor: GestorConsecutivos,
    empresa_id: str,
    ano_gravable: int,
    formato: str,
    tipo_envio: str = TIPO_ENVIO_INICIAL,
) -> SugerenciaConsecutivo:
    """
    Wrapper sobre el gestor — consulta el siguiente consecutivo sugerido.
    Útil para que la UI lo muestre antes de generar.
    """
    return gestor.siguiente_consecutivo(empresa_id, ano_gravable, formato, tipo_envio)


def sugerir_consecutivos_lote(
    gestor: GestorConsecutivos,
    empresa_id: str,
    ano_gravable: int,
    formatos: list[str],
    tipo_envio: str = TIPO_ENVIO_INICIAL,
) -> dict[str, SugerenciaConsecutivo]:
    """
    Consulta consecutivos sugeridos para múltiples formatos a la vez.
    Útil para mostrar al contador la tabla con sugerencias para los 11 formatos.
    """
    return gestor.sugerencias_lote(empresa_id, ano_gravable, formatos, tipo_envio)


def generar_xml_con_consecutivo(
    gestor: GestorConsecutivos,
    empresa_id: str,
    ano_gravable: int,
    formato: str,
    registros: list,
    consecutivo: Optional[int] = None,
    tipo_envio: str = TIPO_ENVIO_INICIAL,
    ano_envio: Optional[int] = None,
    fecha_envio: Optional[datetime] = None,
    fecha_inicial: Optional[date] = None,
    fecha_final: Optional[date] = None,
    ruta_salida: Optional[Path] = None,
    registrar_en_bd: bool = True,
    generado_por: Optional[str] = None,
) -> ResultadoGeneracion:
    """
    Genera un XML completo de un formato con el sistema de consecutivos.
    
    Args:
        gestor: instancia de GestorConsecutivos (con sb=None para modo offline)
        empresa_id: UUID de la empresa
        ano_gravable: año gravable a reportar (ej. 2025)
        formato: '1001', '1003', etc.
        registros: lista de RegistroFXXXX
        consecutivo: si None, usa el sugerido automáticamente; si se pasa, lo usa
        tipo_envio: '01' inicial, '02' fracción, '03' reemplazo, '04' corrección
        ano_envio: año del envío (default: año del año_gravable + 1)
        fecha_envio: datetime del envío (default: now())
        fecha_inicial / fecha_final: período del año gravable (default: 1-ene a 31-dic)
        ruta_salida: si se pasa, guarda el XML en disco
        registrar_en_bd: si True, registra el envío en BD (consume el consecutivo)
        generado_por: UUID del usuario que dispara la generación
    
    Returns:
        ResultadoGeneracion con todo lo necesario para que la UI lo muestre.
    
    Raises:
        ValueError: formato no soportado, consecutivo inválido o ya usado.
    """
    # Validaciones de entrada
    if formato not in GENERADORES:
        raise ValueError(
            f"Formato '{formato}' no soportado. "
            f"Disponibles: {sorted(GENERADORES.keys())}"
        )
    
    if tipo_envio not in TIPOS_ENVIO_VALIDOS:
        raise ValueError(
            f"Tipo de envío inválido: '{tipo_envio}'. "
            f"Debe ser uno de: {sorted(TIPOS_ENVIO_VALIDOS)}"
        )
    
    if not registros:
        raise ValueError(f"No hay registros para generar el F{formato}")
    
    # Asignar consecutivo
    if consecutivo is None:
        sugerencia = gestor.siguiente_consecutivo(
            empresa_id, ano_gravable, formato, tipo_envio
        )
        consecutivo = sugerencia.siguiente
    
    GestorConsecutivos.validar_consecutivo(consecutivo)
    
    # Defaults de fecha
    if ano_envio is None:
        ano_envio = ano_gravable + 1  # ej. 2025 → presentación en 2026
    if fecha_envio is None:
        fecha_envio = datetime.now()
    if fecha_inicial is None:
        fecha_inicial = date(ano_gravable, 1, 1)
    if fecha_final is None:
        fecha_final = date(ano_gravable, 12, 31)
    
    # Construir cabecera
    config = FORMATOS_CONFIG[formato]
    cabecera = CabeceraXML(
        ano_gravable=ano_gravable,
        formato=formato,
        version=config['version'],
        numero_envio=consecutivo,
        fecha_envio=fecha_envio,
        fecha_inicial=fecha_inicial,
        fecha_final=fecha_final,
        tipo_envio=tipo_envio,
    )
    
    # Generar XML
    fn_generar = GENERADORES[formato]
    xml = fn_generar(cabecera, registros)
    
    # Nombre de archivo oficial DIAN
    nombre_archivo = construir_nombre_archivo(
        formato, config['version'], ano_envio, tipo_envio, consecutivo
    )
    
    # Extraer valor total del XML (para registro y trazabilidad)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    valor_total = float(root.find('Cab/ValorTotal').text or 0)
    cantidad_registros = int(root.find('Cab/CantReg').text or len(registros))
    
    # Guardar en disco si se pidió
    ruta_archivo = None
    if ruta_salida is not None:
        ruta_salida = Path(ruta_salida)
        if ruta_salida.is_dir():
            ruta_archivo = ruta_salida / nombre_archivo
        else:
            ruta_archivo = ruta_salida
        guardar_xml(xml, ruta_archivo)
    
    # Registrar en BD
    envio_id = None
    if registrar_en_bd:
        envio = gestor.registrar_envio(
            empresa_id=empresa_id,
            ano_gravable=ano_gravable,
            formato=formato,
            version=config['version'],
            tipo_envio=tipo_envio,
            consecutivo=consecutivo,
            nombre_archivo=nombre_archivo,
            cantidad_registros=cantidad_registros,
            valor_total=valor_total,
            xml_content=xml,
            archivo_xml_path=str(ruta_archivo) if ruta_archivo else None,
            generado_por=generado_por,
        )
        envio_id = envio.envio_id
    
    return ResultadoGeneracion(
        formato=formato,
        version=config['version'],
        tipo_envio=tipo_envio,
        consecutivo_usado=consecutivo,
        nombre_archivo=nombre_archivo,
        xml=xml,
        cantidad_registros=cantidad_registros,
        valor_total=valor_total,
        envio_id=envio_id,
        ruta_archivo=ruta_archivo,
        fecha_generacion=fecha_envio,
    )


def generar_lote_xmls(
    gestor: GestorConsecutivos,
    empresa_id: str,
    ano_gravable: int,
    registros_por_formato: dict,
    consecutivos_elegidos: Optional[dict[str, int]] = None,
    tipo_envio: str = TIPO_ENVIO_INICIAL,
    ano_envio: Optional[int] = None,
    fecha_envio: Optional[datetime] = None,
    ruta_salida: Optional[Path] = None,
    registrar_en_bd: bool = True,
    generado_por: Optional[str] = None,
) -> dict[str, ResultadoGeneracion]:
    """
    Genera los XMLs de TODOS los formatos de un envío en lote.
    
    Args:
        registros_por_formato: dict {formato: [registros]}
            Ej: {'1001': [...], '1005': [...], ...}
        consecutivos_elegidos: dict {formato: consecutivo} opcional.
            Si no se pasa, usa el sugerido automáticamente por formato.
            Ej: {'1001': 6, '1005': 3, '2276': 1}
    
    Returns:
        dict {formato: ResultadoGeneracion}
    """
    consecutivos_elegidos = consecutivos_elegidos or {}
    resultados = {}
    
    for formato, registros in registros_por_formato.items():
        if not registros:
            continue
        
        consec = consecutivos_elegidos.get(formato)  # None si no se especificó
        
        resultados[formato] = generar_xml_con_consecutivo(
            gestor=gestor,
            empresa_id=empresa_id,
            ano_gravable=ano_gravable,
            formato=formato,
            registros=registros,
            consecutivo=consec,
            tipo_envio=tipo_envio,
            ano_envio=ano_envio,
            fecha_envio=fecha_envio,
            ruta_salida=ruta_salida,
            registrar_en_bd=registrar_en_bd,
            generado_por=generado_por,
        )
    
    return resultados
