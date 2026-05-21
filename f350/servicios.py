"""
core/f350/servicios.py — capa de acceso a datos (Supabase) para el módulo F350.

Esta capa encapsula TODAS las consultas a Supabase del módulo. La página
Streamlit consume estas funciones y NO toca directamente las tablas, para
que mañana se pueda cambiar la BD sin tocar la UI.

Funciones:
    Catálogos:
        listar_ciiu(query)
        obtener_tarifa_vigente(codigo_ciiu, fecha)
        obtener_uvt(anio)

    Configuración por empresa:
        leer_config_empresa(empresa_id)
        guardar_config_empresa(empresa_id, data)
        registrar_cambio_ciiu(empresa_id, anterior, nuevo, fecha, motivo, radicado, user_id)
        historial_ciiu(empresa_id)

    Declaraciones:
        listar_declaraciones(empresa_id)
        crear_declaracion(empresa_id, anio, mes, user_id)
        obtener_declaracion(declaracion_id)
        actualizar_totales_declaracion(declaracion_id, totales)
        cambiar_estado_declaracion(declaracion_id, estado)
        eliminar_declaracion(declaracion_id)

    Movimientos:
        guardar_movimientos(declaracion_id, movimientos)
        listar_movimientos(declaracion_id)
        actualizar_movimiento(mov_id, cambios)

    Subcuentas:
        guardar_subcuentas(declaracion_id, subcuentas)
        listar_subcuentas(declaracion_id)
"""

from datetime import date


# =============================================================================
# CATÁLOGOS
# =============================================================================

def listar_ciiu(sb, query=None, limit=50):
    """
    Lista CIIU disponibles con su tarifa más reciente.
    Si se pasa `query`, filtra por código o por nombre de actividad.
    """
    # Tomamos solo las tarifas más nuevas (de cada código por separado).
    # Para simplificar, dejamos que la UI filtre por código/actividad.
    q = sb.table("f350_catalogo_ciiu").select(
        "codigo, actividad_economica, seccion_ciiu, tarifa_autorretencion, "
        "vigencia_desde, vigencia_hasta, normativa"
    )
    if query:
        q = q.or_(f"codigo.ilike.%{query}%,actividad_economica.ilike.%{query}%")
    res = q.order("codigo").limit(limit).execute()
    return res.data or []


def obtener_tarifa_vigente(sb, codigo_ciiu, fecha):
    """
    Devuelve la tarifa vigente para un CIIU en una fecha dada.
    Usa la función SQL `f350_tarifa_vigente` creada en la migración 012.

    Retorna None si no hay tarifa cargada para esa fecha.
    """
    if not codigo_ciiu:
        return None
    fecha_str = fecha.isoformat() if isinstance(fecha, date) else str(fecha)
    try:
        res = sb.rpc(
            "f350_tarifa_vigente",
            {"p_codigo_ciiu": codigo_ciiu, "p_fecha": fecha_str},
        ).execute()
        return res.data  # numeric o None
    except Exception:
        # Fallback: leer directo de la tabla
        res = (
            sb.table("f350_catalogo_ciiu")
              .select("tarifa_autorretencion, vigencia_desde, vigencia_hasta")
              .eq("codigo", codigo_ciiu)
              .lte("vigencia_desde", fecha_str)
              .order("vigencia_desde", desc=True)
              .limit(1)
              .execute()
        )
        if not res.data:
            return None
        row = res.data[0]
        hasta = row.get("vigencia_hasta")
        if hasta and hasta < fecha_str:
            return None
        return row.get("tarifa_autorretencion")


def obtener_uvt(sb, anio):
    """Devuelve el valor de la UVT en pesos para el año dado."""
    res = (
        sb.table("f350_uvt_historico")
          .select("valor_uvt_pesos, resolucion_dian")
          .eq("anio", anio)
          .limit(1)
          .execute()
    )
    if res.data:
        return res.data[0]
    return None


# =============================================================================
# CONFIGURACIÓN POR EMPRESA
# =============================================================================

def leer_config_empresa(sb, empresa_id):
    """
    Devuelve la config F350 de una empresa, o None si nunca se ha guardado.
    """
    res = (
        sb.table("f350_empresa_config")
          .select("*")
          .eq("empresa_id", empresa_id)
          .limit(1)
          .execute()
    )
    return res.data[0] if res.data else None


def guardar_config_empresa(sb, empresa_id, data):
    """
    Upsert de configuración F350.
    `data` es un dict con cualquier subconjunto de:
        ciiu_principal, es_autorretenedor, tarifa_autorretencion_manual,
        exonerado_art_114_1, representante_legal, email_contacto, notas.
    """
    payload = {"empresa_id": empresa_id, **data}
    # `actualizado_en` se actualiza manualmente (la BD no tiene trigger).
    payload["actualizado_en"] = "now()"
    res = (
        sb.table("f350_empresa_config")
          .upsert(payload, on_conflict="empresa_id")
          .execute()
    )
    return res.data[0] if res.data else None


def registrar_cambio_ciiu(
    sb, empresa_id, ciiu_anterior, ciiu_nuevo,
    fecha_vigencia_desde, motivo=None, numero_radicado=None, user_id=None,
):
    """Registra un cambio histórico de CIIU."""
    payload = {
        "empresa_id":           empresa_id,
        "ciiu_anterior":        ciiu_anterior,
        "ciiu_nuevo":           ciiu_nuevo,
        "fecha_vigencia_desde": (
            fecha_vigencia_desde.isoformat()
            if isinstance(fecha_vigencia_desde, date)
            else fecha_vigencia_desde
        ),
        "motivo_cambio":        motivo,
        "numero_radicado_pqr":  numero_radicado,
        "creado_por":           user_id,
    }
    res = sb.table("f350_historial_ciiu").insert(payload).execute()
    return res.data[0] if res.data else None


def historial_ciiu(sb, empresa_id):
    """Devuelve el historial completo de cambios de CIIU de una empresa."""
    res = (
        sb.table("f350_historial_ciiu")
          .select("*")
          .eq("empresa_id", empresa_id)
          .order("fecha_vigencia_desde", desc=True)
          .execute()
    )
    return res.data or []


# =============================================================================
# DECLARACIONES
# =============================================================================

def listar_declaraciones(sb, empresa_id, limit=50):
    """Lista las declaraciones de la empresa, más nuevas primero."""
    res = (
        sb.table("f350_declaraciones")
          .select("*")
          .eq("empresa_id", empresa_id)
          .order("anio", desc=True)
          .order("mes", desc=True)
          .limit(limit)
          .execute()
    )
    return res.data or []


def obtener_declaracion(sb, declaracion_id):
    """Trae una declaración por ID, o None."""
    res = (
        sb.table("f350_declaraciones")
          .select("*")
          .eq("id", declaracion_id)
          .limit(1)
          .execute()
    )
    return res.data[0] if res.data else None


def crear_declaracion(sb, empresa_id, anio, mes, user_id=None):
    """
    Crea una declaración Borrador para empresa-año-mes.
    Si ya existe, retorna la existente (no falla).
    """
    # Intentar leer primero por la restricción UNIQUE (empresa, anio, mes)
    existente = (
        sb.table("f350_declaraciones")
          .select("*")
          .eq("empresa_id", empresa_id)
          .eq("anio", anio)
          .eq("mes", mes)
          .limit(1)
          .execute()
    )
    if existente.data:
        return existente.data[0]

    payload = {
        "empresa_id": empresa_id,
        "anio":       anio,
        "mes":        mes,
        "estado":     "Borrador",
        "creado_por": user_id,
    }
    res = sb.table("f350_declaraciones").insert(payload).execute()
    return res.data[0] if res.data else None


def actualizar_totales_declaracion(sb, declaracion_id, totales):
    """
    Actualiza los totales calculados de la declaración.
    `totales` es un dict con cualquiera de:
        base_autorretencion, valor_autorretencion,
        total_retenciones_renta, total_retenciones_iva,
        total_declaracion, ciiu_aplicado, tarifa_aplicada,
        normativa_aplicada.
    """
    payload = {**totales, "actualizado_en": "now()"}
    res = (
        sb.table("f350_declaraciones")
          .update(payload)
          .eq("id", declaracion_id)
          .execute()
    )
    return res.data[0] if res.data else None


def cambiar_estado_declaracion(sb, declaracion_id, nuevo_estado):
    """
    Cambia el estado de la declaración. Estados válidos:
    'Borrador' | 'Revisada' | 'Presentada'.
    """
    payload = {"estado": nuevo_estado, "actualizado_en": "now()"}
    if nuevo_estado == "Presentada":
        payload["fecha_presentacion"] = "now()"
    res = (
        sb.table("f350_declaraciones")
          .update(payload)
          .eq("id", declaracion_id)
          .execute()
    )
    return res.data[0] if res.data else None


def eliminar_declaracion(sb, declaracion_id):
    """Borra una declaración y sus movimientos/subcuentas (CASCADE)."""
    sb.table("f350_declaraciones").delete().eq("id", declaracion_id).execute()


# =============================================================================
# MOVIMIENTOS
# =============================================================================

def guardar_movimientos(sb, declaracion_id, movimientos):
    """
    Reemplaza TODOS los movimientos de una declaración.
    Primero borra los existentes y luego inserta los nuevos.
    `movimientos` es lista de dicts con las columnas de
    f350_movimientos_declaracion (sin id ni creado_en).
    """
    # Borrar existentes
    sb.table("f350_movimientos_declaracion") \
      .delete() \
      .eq("declaracion_id", declaracion_id) \
      .execute()

    if not movimientos:
        return []

    # Asegurar que todos los movimientos tengan el declaracion_id
    payload = [{**m, "declaracion_id": declaracion_id} for m in movimientos]
    # Insertar en lotes de 500 para no sobrepasar límites
    insertados = []
    for i in range(0, len(payload), 500):
        chunk = payload[i:i + 500]
        res = sb.table("f350_movimientos_declaracion").insert(chunk).execute()
        insertados.extend(res.data or [])
    return insertados


def listar_movimientos(sb, declaracion_id):
    """Lista todos los movimientos de la declaración."""
    res = (
        sb.table("f350_movimientos_declaracion")
          .select("*")
          .eq("declaracion_id", declaracion_id)
          .order("cuenta_puc")
          .execute()
    )
    return res.data or []


def actualizar_movimiento(sb, mov_id, cambios):
    """Actualiza un movimiento específico (ej. al reclasificarlo a mano)."""
    res = (
        sb.table("f350_movimientos_declaracion")
          .update(cambios)
          .eq("id", mov_id)
          .execute()
    )
    return res.data[0] if res.data else None


# =============================================================================
# SUBCUENTAS DE AUTORRETENCIÓN
# =============================================================================

def guardar_subcuentas(sb, declaracion_id, subcuentas):
    """Reemplaza las subcuentas de la declaración."""
    sb.table("f350_subcuentas_autorretencion") \
      .delete() \
      .eq("declaracion_id", declaracion_id) \
      .execute()

    if not subcuentas:
        return []

    payload = [{**s, "declaracion_id": declaracion_id} for s in subcuentas]
    res = sb.table("f350_subcuentas_autorretencion").insert(payload).execute()
    return res.data or []


def listar_subcuentas(sb, declaracion_id):
    """Lista las subcuentas de la declaración."""
    res = (
        sb.table("f350_subcuentas_autorretencion")
          .select("*")
          .eq("declaracion_id", declaracion_id)
          .order("codigo_subcuenta")
          .execute()
    )
    return res.data or []
