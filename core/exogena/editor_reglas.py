"""
Editor de Reglas — Backend
==========================

CRUD sobre las reglas del motor de exógena, distinguiendo:
    - Capa 1 (global): exogena_puc_generico — reglas universales por código de cuenta
    - Capa 3 (override por empresa): exogena_mapeo_manual — excepciones por empresa

NO toca Capa 2 (exogena_mapeo_empresa) porque esa viene del archivo de Codificación
del software contable y se administra desde el upload masivo.

Jerarquía del motor (no se modifica): Capa 3 > Capa 2 > Capa 1.

Cada operación de escritura:
    1. Lee el estado anterior (para el log)
    2. Aplica el cambio
    3. Registra en exogena_reglas_log
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Any

# Type hint solo - en runtime no se usa, solo para IDE
try:
    from supabase import Client
except ImportError:
    Client = Any  # type: ignore


# ============================================================================
# Modelos de datos
# ============================================================================

@dataclass
class ReglaVista:
    """Una regla tal como se muestra en el editor (unificada de las 3 capas)."""
    codigo_cuenta: str
    nombre_cuenta: str
    formato_dian: Optional[str]
    concepto_dian: Optional[int]
    descripcion_concepto: str
    capa: int  # 1, 2 o 3
    capa_nombre: str  # 'Global', 'Mapeo nativo', 'Override empresa'
    nit: Optional[str] = None  # Solo para Capa 3 cuando aplica
    excluir: bool = False
    motivo_exclusion: Optional[str] = None
    nota: Optional[str] = None
    activo: bool = True
    año_gravable: int = 2025
    modificado_en: Optional[datetime] = None
    modificado_por: Optional[str] = None
    # ID interno por capa (para edición/eliminación)
    id_capa1: Optional[int] = None
    id_capa3: Optional[int] = None


@dataclass
class ResultadoOperacion:
    """Resultado uniforme de cualquier operación de escritura."""
    ok: bool
    mensaje: str
    regla_resultante: Optional[dict] = None
    log_id: Optional[int] = None


# ============================================================================
# Lecturas — vista unificada por formato/concepto
# ============================================================================

def listar_formatos_con_reglas(
    sb: Client,
    año_gravable: int = 2025,
) -> list[dict]:
    """
    Lista los formatos DIAN que tienen al menos una regla activa en Capa 1.
    Devuelve: [{formato_dian, conteo}, ...] ordenado por formato.
    """
    res = sb.table('exogena_puc_generico') \
        .select('formato_dian') \
        .eq('año_gravable', año_gravable) \
        .eq('activo', True) \
        .not_.is_('formato_dian', 'null') \
        .execute()

    conteo: dict[str, int] = {}
    for row in res.data or []:
        f = row.get('formato_dian')
        if f:
            conteo[f] = conteo.get(f, 0) + 1

    return [
        {'formato_dian': f, 'conteo': c}
        for f, c in sorted(conteo.items())
    ]


def listar_conceptos_de_formato(
    sb: Client,
    formato_dian: str,
    año_gravable: int = 2025,
) -> list[dict]:
    """
    Lista los conceptos DIAN disponibles para un formato dado, desde el catálogo oficial.
    Útil para los dropdowns de edición.

    Nota: la columna real en BD se llama 'codigo_concepto' pero la mapeamos
    a 'concepto_dian' en la salida para que el resto del código sea consistente.

    Devuelve: [{concepto_dian, descripcion}, ...]
    """
    res = sb.table('exogena_cat_concepto_formato') \
        .select('codigo_concepto, descripcion') \
        .eq('formato_dian', formato_dian) \
        .eq('año_gravable', año_gravable) \
        .order('codigo_concepto') \
        .execute()

    return [
        {
            'concepto_dian': r['codigo_concepto'],
            'descripcion': r.get('descripcion', ''),
        }
        for r in (res.data or [])
    ]


def listar_reglas_por_formato(
    sb: Client,
    formato_dian: str,
    empresa_id: Optional[str] = None,
    año_gravable: int = 2025,
    incluir_overrides: bool = True,
) -> list[ReglaVista]:
    """
    Lista todas las reglas que mapean a un formato dado.
    
    Si empresa_id se da y incluir_overrides=True, también incluye los overrides
    de Capa 3 que apuntan a ese formato para esa empresa.

    Las reglas se devuelven ordenadas por concepto y luego por código de cuenta.
    """
    reglas: list[ReglaVista] = []

    # --- Capa 1 (global) ---
    res1 = sb.table('exogena_puc_generico') \
        .select('*') \
        .eq('año_gravable', año_gravable) \
        .eq('formato_dian', formato_dian) \
        .eq('activo', True) \
        .order('concepto_dian') \
        .order('codigo_cuenta') \
        .execute()

    for r in res1.data or []:
        reglas.append(ReglaVista(
            codigo_cuenta=r['codigo_cuenta'],
            nombre_cuenta=r.get('nombre_cuenta', ''),
            formato_dian=r['formato_dian'],
            concepto_dian=r.get('concepto_dian'),
            descripcion_concepto=r.get('descripcion_concepto', '') or '',
            capa=1,
            capa_nombre='Global',
            nota=r.get('nota'),
            activo=r.get('activo', True),
            año_gravable=r['año_gravable'],
            modificado_en=r.get('modificado_en'),
            modificado_por=r.get('modificado_por'),
            id_capa1=r.get('id'),
        ))

    # --- Capa 3 (override por empresa) ---
    if empresa_id and incluir_overrides:
        res3 = sb.table('exogena_mapeo_manual') \
            .select('*') \
            .eq('año_gravable', año_gravable) \
            .eq('formato_dian', formato_dian) \
            .eq('empresa_id', empresa_id) \
            .order('concepto_dian') \
            .order('codigo_cuenta') \
            .execute()

        for r in res3.data or []:
            reglas.append(ReglaVista(
                codigo_cuenta=r['codigo_cuenta'],
                nombre_cuenta=r.get('nombre_cuenta', '') or '',
                formato_dian=r['formato_dian'],
                concepto_dian=r.get('concepto_dian'),
                descripcion_concepto=r.get('descripcion_concepto', '') or '',
                capa=3,
                capa_nombre='Override empresa',
                nit=r.get('nit'),
                excluir=r.get('excluir', False),
                motivo_exclusion=r.get('motivo_exclusion'),
                nota=r.get('nota'),
                año_gravable=r['año_gravable'],
                modificado_en=r.get('modificado_en'),
                modificado_por=r.get('modificado_por'),
                id_capa3=r.get('id'),
            ))

    return reglas


def buscar_cuenta(
    sb: Client,
    termino: str,
    empresa_id: Optional[str] = None,
    año_gravable: int = 2025,
) -> list[ReglaVista]:
    """
    Busca una cuenta por código (exacto o prefijo) o por nombre (substring).
    Devuelve TODAS las apariciones en las 3 capas para que el usuario vea
    el panorama completo (incluyendo Capa 2 que es de solo lectura).

    Si hay regla en múltiples capas, se devuelven todas — la UI muestra
    cuál capa gana según jerarquía Capa 3 > Capa 2 > Capa 1.
    """
    termino = termino.strip()
    if not termino:
        return []

    reglas: list[ReglaVista] = []
    es_codigo = termino.replace('.', '').isdigit()

    # --- Capa 1 (global) ---
    q1 = sb.table('exogena_puc_generico') \
        .select('*') \
        .eq('año_gravable', año_gravable) \
        .eq('activo', True)

    if es_codigo:
        q1 = q1.like('codigo_cuenta', f'{termino}%')
    else:
        q1 = q1.ilike('nombre_cuenta', f'%{termino}%')

    res1 = q1.order('codigo_cuenta').limit(100).execute()

    for r in res1.data or []:
        reglas.append(ReglaVista(
            codigo_cuenta=r['codigo_cuenta'],
            nombre_cuenta=r.get('nombre_cuenta', '') or '',
            formato_dian=r.get('formato_dian'),
            concepto_dian=r.get('concepto_dian'),
            descripcion_concepto=r.get('descripcion_concepto', '') or '',
            capa=1,
            capa_nombre='Global',
            nota=r.get('nota'),
            activo=r.get('activo', True),
            año_gravable=r['año_gravable'],
            modificado_en=r.get('modificado_en'),
            modificado_por=r.get('modificado_por'),
            id_capa1=r.get('id'),
        ))

    # --- Capa 2 (mapeo nativo - solo lectura, por rangos) ---
    if empresa_id and es_codigo:
        # Buscamos rangos que contengan el código
        res2 = sb.table('exogena_mapeo_empresa') \
            .select('*') \
            .eq('año_gravable', año_gravable) \
            .eq('empresa_id', empresa_id) \
            .eq('activo', True) \
            .lte('cuenta_inicial', termino) \
            .gte('cuenta_final', termino) \
            .execute()

        for r in res2.data or []:
            reglas.append(ReglaVista(
                codigo_cuenta=f"[{r['cuenta_inicial']}-{r['cuenta_final']}]",
                nombre_cuenta=f"Rango Capa 2: {termino} aplica",
                formato_dian=r.get('formato_dian'),
                concepto_dian=r.get('concepto_dian'),
                descripcion_concepto=r.get('descripcion_concepto', '') or '',
                capa=2,
                capa_nombre='Mapeo nativo',
                año_gravable=r['año_gravable'],
            ))

    # --- Capa 3 (override por empresa) ---
    if empresa_id:
        q3 = sb.table('exogena_mapeo_manual') \
            .select('*') \
            .eq('año_gravable', año_gravable) \
            .eq('empresa_id', empresa_id)

        if es_codigo:
            q3 = q3.like('codigo_cuenta', f'{termino}%')

        res3 = q3.limit(100).execute()
        for r in res3.data or []:
            reglas.append(ReglaVista(
                codigo_cuenta=r['codigo_cuenta'],
                nombre_cuenta=r.get('nombre_cuenta', '') or '',
                formato_dian=r.get('formato_dian'),
                concepto_dian=r.get('concepto_dian'),
                descripcion_concepto=r.get('descripcion_concepto', '') or '',
                capa=3,
                capa_nombre='Override empresa',
                nit=r.get('nit'),
                excluir=r.get('excluir', False),
                motivo_exclusion=r.get('motivo_exclusion'),
                nota=r.get('nota'),
                año_gravable=r['año_gravable'],
                modificado_en=r.get('modificado_en'),
                modificado_por=r.get('modificado_por'),
                id_capa3=r.get('id'),
            ))

    return reglas


# ============================================================================
# Escrituras — Capa 1 (global)
# ============================================================================

def editar_regla_global(
    sb: Client,
    id_capa1: int,
    formato_nuevo: Optional[str],
    concepto_nuevo: Optional[int],
    descripcion_nueva: str,
    usuario: str,
    motivo: str = '',
    año_gravable: int = 2025,
) -> ResultadoOperacion:
    """
    Edita una regla de Capa 1. Lee el estado anterior, lo guarda en log,
    y aplica el cambio.
    """
    # Leer estado anterior
    prev = sb.table('exogena_puc_generico') \
        .select('*') \
        .eq('id', id_capa1) \
        .single() \
        .execute()

    if not prev.data:
        return ResultadoOperacion(False, f'No se encontró la regla id={id_capa1}')

    formato_anterior = prev.data.get('formato_dian')
    concepto_anterior = prev.data.get('concepto_dian')
    codigo_cuenta = prev.data.get('codigo_cuenta')

    # Aplicar cambio
    update_data = {
        'formato_dian': formato_nuevo,
        'concepto_dian': concepto_nuevo,
        'descripcion_concepto': descripcion_nueva,
        'modificado_en': datetime.now(timezone.utc).isoformat(),
        'modificado_por': usuario,
    }

    sb.table('exogena_puc_generico') \
        .update(update_data) \
        .eq('id', id_capa1) \
        .execute()

    # Log
    log = _registrar_log(
        sb=sb,
        usuario=usuario,
        empresa_id=None,
        capa=1,
        accion='editar' if formato_anterior == formato_nuevo else 'mover',
        codigo_cuenta=codigo_cuenta,
        formato_anterior=formato_anterior,
        concepto_anterior=concepto_anterior,
        formato_nuevo=formato_nuevo,
        concepto_nuevo=concepto_nuevo,
        motivo=motivo,
    )

    return ResultadoOperacion(
        ok=True,
        mensaje=f'Regla global actualizada: {codigo_cuenta} → {formato_nuevo}/{concepto_nuevo}',
        log_id=log,
    )


def crear_regla_global(
    sb: Client,
    codigo_cuenta: str,
    nombre_cuenta: str,
    formato_dian: str,
    concepto_dian: int,
    descripcion_concepto: str,
    naturaleza: str,
    usuario: str,
    motivo: str = '',
    nota: Optional[str] = None,
    año_gravable: int = 2025,
) -> ResultadoOperacion:
    """Crea una nueva regla en Capa 1 (global). Útil para cuentas no-PUC."""
    # Validar que no exista
    existe = sb.table('exogena_puc_generico') \
        .select('id') \
        .eq('codigo_cuenta', codigo_cuenta) \
        .eq('año_gravable', año_gravable) \
        .execute()

    if existe.data:
        return ResultadoOperacion(
            False,
            f'Ya existe una regla global para la cuenta {codigo_cuenta}. Usa "Editar" en su lugar.'
        )

    insert_data = {
        'codigo_cuenta': codigo_cuenta,
        'nombre_cuenta': nombre_cuenta,
        'formato_dian': formato_dian,
        'concepto_dian': concepto_dian,
        'descripcion_concepto': descripcion_concepto,
        'naturaleza': naturaleza,
        'nota': nota,
        'activo': True,
        'año_gravable': año_gravable,
        'modificado_en': datetime.now(timezone.utc).isoformat(),
        'modificado_por': usuario,
    }

    res = sb.table('exogena_puc_generico').insert(insert_data).execute()

    log = _registrar_log(
        sb=sb,
        usuario=usuario,
        empresa_id=None,
        capa=1,
        accion='crear',
        codigo_cuenta=codigo_cuenta,
        formato_anterior=None,
        concepto_anterior=None,
        formato_nuevo=formato_dian,
        concepto_nuevo=concepto_dian,
        motivo=motivo,
    )

    return ResultadoOperacion(
        ok=True,
        mensaje=f'Regla global creada: {codigo_cuenta} → {formato_dian}/{concepto_dian}',
        log_id=log,
    )


def desactivar_regla_global(
    sb: Client,
    id_capa1: int,
    usuario: str,
    motivo: str = '',
) -> ResultadoOperacion:
    """
    Desactiva (activo=false) una regla global. NO la elimina físicamente
    para preservar trazabilidad histórica.
    """
    prev = sb.table('exogena_puc_generico') \
        .select('*') \
        .eq('id', id_capa1) \
        .single() \
        .execute()

    if not prev.data:
        return ResultadoOperacion(False, f'No se encontró la regla id={id_capa1}')

    sb.table('exogena_puc_generico') \
        .update({
            'activo': False,
            'modificado_en': datetime.now(timezone.utc).isoformat(),
            'modificado_por': usuario,
        }) \
        .eq('id', id_capa1) \
        .execute()

    log = _registrar_log(
        sb=sb,
        usuario=usuario,
        empresa_id=None,
        capa=1,
        accion='eliminar',
        codigo_cuenta=prev.data['codigo_cuenta'],
        formato_anterior=prev.data.get('formato_dian'),
        concepto_anterior=prev.data.get('concepto_dian'),
        formato_nuevo=None,
        concepto_nuevo=None,
        motivo=motivo,
    )

    return ResultadoOperacion(
        ok=True,
        mensaje=f'Regla global desactivada: {prev.data["codigo_cuenta"]}',
        log_id=log,
    )


# ============================================================================
# Escrituras — Capa 3 (override por empresa)
# ============================================================================

def crear_o_actualizar_override(
    sb: Client,
    empresa_id: str,
    codigo_cuenta: str,
    nombre_cuenta: str,
    formato_dian: Optional[str],
    concepto_dian: Optional[int],
    descripcion_concepto: str,
    usuario: str,
    nit: Optional[str] = None,
    excluir: bool = False,
    motivo_exclusion: Optional[str] = None,
    nota: Optional[str] = None,
    motivo: str = '',
    año_gravable: int = 2025,
) -> ResultadoOperacion:
    """
    Crea o actualiza un override en Capa 3 para una empresa.
    Si excluir=True, formato_dian y concepto_dian deben ser None.
    """
    # Validación
    if excluir and (formato_dian or concepto_dian):
        return ResultadoOperacion(
            False,
            'Una regla con excluir=true no puede tener formato/concepto.'
        )

    # Buscar si ya existe override
    q = sb.table('exogena_mapeo_manual') \
        .select('*') \
        .eq('empresa_id', empresa_id) \
        .eq('codigo_cuenta', codigo_cuenta) \
        .eq('año_gravable', año_gravable)

    if nit:
        q = q.eq('nit', nit)
    else:
        q = q.is_('nit', 'null')

    existing = q.execute()

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        'empresa_id': empresa_id,
        'codigo_cuenta': codigo_cuenta,
        'nombre_cuenta': nombre_cuenta,
        'formato_dian': formato_dian,
        'concepto_dian': concepto_dian,
        'descripcion_concepto': descripcion_concepto,
        'nit': nit,
        'excluir': excluir,
        'motivo_exclusion': motivo_exclusion,
        'nota': nota,
        'año_gravable': año_gravable,
        'modificado_en': now,
        'modificado_por': usuario,
    }

    if existing.data:
        prev = existing.data[0]
        sb.table('exogena_mapeo_manual') \
            .update(payload) \
            .eq('id', prev['id']) \
            .execute()
        accion = 'editar'
        formato_anterior = prev.get('formato_dian')
        concepto_anterior = prev.get('concepto_dian')
    else:
        payload['creado_en'] = now
        sb.table('exogena_mapeo_manual').insert(payload).execute()
        accion = 'crear'
        formato_anterior = None
        concepto_anterior = None

    log = _registrar_log(
        sb=sb,
        usuario=usuario,
        empresa_id=empresa_id,
        capa=3,
        accion=accion,
        codigo_cuenta=codigo_cuenta,
        formato_anterior=formato_anterior,
        concepto_anterior=concepto_anterior,
        formato_nuevo=formato_dian,
        concepto_nuevo=concepto_dian,
        motivo=motivo,
        metadata={'nit': nit, 'excluir': excluir} if (nit or excluir) else None,
    )

    return ResultadoOperacion(
        ok=True,
        mensaje=f'Override {accion}: {codigo_cuenta} → {formato_dian or "EXCLUIDA"}/{concepto_dian or ""}',
        log_id=log,
    )


def eliminar_override(
    sb: Client,
    id_capa3: int,
    usuario: str,
    motivo: str = '',
) -> ResultadoOperacion:
    """Elimina un override de Capa 3 (la cuenta vuelve a regirse por Capa 1/2)."""
    prev = sb.table('exogena_mapeo_manual') \
        .select('*') \
        .eq('id', id_capa3) \
        .single() \
        .execute()

    if not prev.data:
        return ResultadoOperacion(False, f'No se encontró el override id={id_capa3}')

    sb.table('exogena_mapeo_manual') \
        .delete() \
        .eq('id', id_capa3) \
        .execute()

    log = _registrar_log(
        sb=sb,
        usuario=usuario,
        empresa_id=prev.data.get('empresa_id'),
        capa=3,
        accion='eliminar',
        codigo_cuenta=prev.data['codigo_cuenta'],
        formato_anterior=prev.data.get('formato_dian'),
        concepto_anterior=prev.data.get('concepto_dian'),
        formato_nuevo=None,
        concepto_nuevo=None,
        motivo=motivo,
    )

    return ResultadoOperacion(
        ok=True,
        mensaje=f'Override eliminado: {prev.data["codigo_cuenta"]}',
        log_id=log,
    )


# ============================================================================
# Log de auditoría
# ============================================================================

def _registrar_log(
    sb: Client,
    usuario: str,
    empresa_id: Optional[str],
    capa: int,
    accion: str,
    codigo_cuenta: str,
    formato_anterior: Optional[str],
    concepto_anterior: Optional[int],
    formato_nuevo: Optional[str],
    concepto_nuevo: Optional[int],
    motivo: str = '',
    metadata: Optional[dict] = None,
) -> Optional[int]:
    """Inserta un registro en exogena_reglas_log. No falla si el log falla."""
    try:
        res = sb.table('exogena_reglas_log').insert({
            'usuario': usuario,
            'empresa_id': empresa_id,
            'capa': capa,
            'accion': accion,
            'codigo_cuenta': codigo_cuenta,
            'formato_anterior': formato_anterior,
            'concepto_anterior': concepto_anterior,
            'formato_nuevo': formato_nuevo,
            'concepto_nuevo': concepto_nuevo,
            'motivo': motivo or None,
            'metadata': metadata,
        }).execute()
        return res.data[0]['id'] if res.data else None
    except Exception as e:
        # Log no debe romper la operación principal
        print(f'⚠️ No se pudo registrar log: {e}')
        return None


def listar_log_reciente(
    sb: Client,
    limit: int = 50,
    empresa_id: Optional[str] = None,
) -> list[dict]:
    """Devuelve los últimos N cambios para mostrar en el panel de auditoría."""
    q = sb.table('exogena_reglas_log').select('*').order('fecha', desc=True).limit(limit)
    if empresa_id:
        # Incluye cambios globales (empresa_id NULL) + los de esta empresa
        q = q.or_(f'empresa_id.is.null,empresa_id.eq.{empresa_id}')
    return (q.execute().data or [])
