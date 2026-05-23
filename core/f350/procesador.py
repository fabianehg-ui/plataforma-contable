"""
core/f350/procesador.py — orquestador del procesamiento de una declaración.

Toma los PDFs de auxiliar + balance, ejecuta clasificador + autorretención,
y devuelve los movimientos y totales listos para guardar en Supabase.

Esta función NO toca Supabase; solo lógica pura. La página Streamlit
recibe el resultado y lo persiste con `servicios.guardar_movimientos()`.

Funciones:
    procesar_declaracion(auxiliar_bytes, balance_bytes, tarifa_pct,
                         es_exonerado=False, subcuentas_excluidas=None)
        → dict con: empresa, periodo, movimientos, totales, advertencias
"""

from core.f350.parser_contai import parsear_auxiliar_contai, parsear_balance_contai
from core.f350.clasificador import clasificar_concepto_detallado
from core.f350.casillas import obtener_casillas_f350, AUTORRET_CASILLAS_F350
from core.f350.autorretencion import (
    calcular_autorretencion_cuenta_4,
    calcular_autorretencion_por_subcuentas,
)
from core.f350.nit_utils import inferir_tipo_persona


def procesar_declaracion(
    auxiliar_fuente,
    balance_fuente,
    tarifa_pct,
    es_exonerado=False,
    subcuentas_excluidas=None,
):
    """
    Procesa los PDFs y produce un paquete completo de la declaración.

    Args:
        auxiliar_fuente: ruta / bytes / file-like del auxiliar de retefuente.
        balance_fuente:  ruta / bytes / file-like del balance de prueba.
        tarifa_pct:      tarifa de autorretención en PORCENTAJE (ej. 1.10).
        es_exonerado:    si la empresa está exonerada del art. 114-1, la
                         autorretención cae en la casilla de "Contribuyentes
                         exonerados 114-1" en vez de "Ventas".
        subcuentas_excluidas: set de códigos de subcuentas de la cuenta 4
                              que deben excluirse de la base de
                              autorretención (ej. {"4295"}).

    Retorna dict:
        empresa:      str
        nit_empresa:  str
        periodo:      str (ej. "Mar-3-2026")
        auxiliar:     dict (resultado de parsear_auxiliar_contai)
        balance:      dict (resultado de parsear_balance_contai)
        movimientos:  list[dict] — un dict por cada línea del auxiliar,
                                    con clasificación + casilla destino.
        retenciones_agrupadas: list[dict] — agrupadas por (concepto, tipo).
        autorretenciones:      list[dict] — bloque "Autorretenciones" F350.
        totales:               dict con base_autorretencion, valor_autorret,
                               total_retenciones_renta, total_retenciones_iva,
                               total_declaracion, ciiu_aplicado, tarifa.
        advertencias:          list[str] — cosas que la UI debe mostrar.
    """
    advertencias = []

    # ---- 1. Parsear los dos PDFs ----
    auxiliar = parsear_auxiliar_contai(auxiliar_fuente)
    balance  = parsear_balance_contai(balance_fuente)

    if not auxiliar["movimientos"]:
        advertencias.append("El auxiliar no contiene movimientos parseables.")

    if not balance["cuentas"]:
        advertencias.append("El balance no contiene cuentas parseables.")

    # Líneas que el parser descartó por tener una tarifa imposible (>=100%).
    # Suelen indicar una línea mal leída del PDF; el usuario debe revisarlas
    # manualmente porque podrían contener una retención real.
    for ls in auxiliar.get("lineas_sospechosas", []):
        advertencias.append(
            f"Línea no incluida (tarifa leída {ls['tarifa_leida']:.2f}% "
            f"fuera de rango) en cuenta {ls['cuenta']}: «{ls['linea']}». "
            f"Revísala manualmente."
        )

    # ---- 2. Procesar cada movimiento del auxiliar ----
    movimientos = []
    total_ret_renta = 0
    total_ret_iva   = 0

    for mov in auxiliar["movimientos"]:
        cuenta = mov["cuenta"]
        nombre_cuenta = mov["nombre_cuenta"]

        clasif = clasificar_concepto_detallado(cuenta, nombre_cuenta)
        concepto = clasif["concepto"]

        # Determinar tipo de persona del tercero (PN/PJ)
        tipo, es_ext, _, _ = inferir_tipo_persona(mov["nit"])

        # Encontrar casilla destino
        if concepto == "IVA":
            # No tiene casilla en la tabla de retenciones a terceros;
            # va al renglón 131 (Total IVA).
            casilla_destino = 131
            total_ret_iva += mov["retencion"]
        else:
            _cas_base, casilla_destino = obtener_casillas_f350(
                concepto, tipo, es_extranjero=es_ext
            )
            if casilla_destino is None:
                # Solo ocurre con "Rentas de trabajo" + PJ (no aplica)
                advertencias.append(
                    f"Movimiento de {mov['nombre_tercero']} ({mov['nit']}) "
                    f"clasificado como '{concepto}' + Persona Jurídica no "
                    f"tiene casilla F350. Revisar manualmente."
                )
            total_ret_renta += mov["retencion"]

        movimientos.append({
            "cuenta_puc":        cuenta,
            "nombre_cuenta":     nombre_cuenta,
            "nit_tercero":       mov["nit"],
            "nombre_tercero":    mov["nombre_tercero"],
            "tipo_inferido":     tipo,
            "es_extranjero":     es_ext,
            "base":              mov["base"],
            "tarifa":            mov["tarifa_mov"],
            "retencion":         mov["retencion"],
            "casilla_destino":   casilla_destino,
            "concepto_asignado": concepto,
            "confianza_clasif":  clasif["confianza"],
            "regla_clasif":      clasif["regla"],
            "estado":            "revisar" if clasif["confianza"] == "baja" else "ok",
        })

    # ---- 3. Agrupar retenciones por (concepto, tipo) para el F350 ----
    agrupadas_map = {}
    for m in movimientos:
        if m["concepto_asignado"] == "IVA":
            continue
        tipo_key = "PN" if m["tipo_inferido"] == "Persona Natural" else "PJ"
        key = (m["concepto_asignado"], tipo_key)
        if key not in agrupadas_map:
            agrupadas_map[key] = {
                "concepto":  m["concepto_asignado"],
                "tipo":      tipo_key,
                "base":      0,
                "retencion": 0,
                "movimientos": 0,
            }
        agrupadas_map[key]["base"] += m["base"]
        agrupadas_map[key]["retencion"] += m["retencion"]
        agrupadas_map[key]["movimientos"] += 1

    retenciones_agrupadas = sorted(
        agrupadas_map.values(),
        key=lambda r: (r["concepto"], r["tipo"]),
    )

    # ---- 4. Calcular autorretención sobre cuenta 4 ----
    if subcuentas_excluidas:
        autorret = calcular_autorretencion_por_subcuentas(
            balance, tarifa_pct, subcuentas_excluidas=set(subcuentas_excluidas),
        )
        base_autorret = autorret["base_total"]
        valor_autorret = autorret["autorretencion"]
    else:
        autorret = calcular_autorretencion_cuenta_4(balance, tarifa_pct)
        if autorret is None:
            advertencias.append(
                "No se encontró la cuenta 4 (Ingresos) en el balance. "
                "La autorretención no se pudo calcular."
            )
            base_autorret = 0
            valor_autorret = 0
            autorret = {}
        else:
            base_autorret = autorret["ingresos_netos"]
            valor_autorret = autorret["autorretencion"]

    # El bloque de autorretenciones del F350 — en este flujo todo va a
    # "Contribuyentes exonerados 114-1" (si la empresa lo es) o "Ventas".
    concepto_autorret = "Contribuyentes exonerados 114-1" if es_exonerado else "Ventas"
    autorretenciones = [{
        "concepto":  concepto_autorret,
        "base":      base_autorret,
        "retencion": valor_autorret,
    }]
    # Las demás casillas de autorretención quedan en 0 (la UI puede
    # añadirlas manualmente si la empresa hace autorretenciones por
    # otros conceptos como rendimientos financieros, etc).
    for c in AUTORRET_CASILLAS_F350:
        if c != concepto_autorret:
            autorretenciones.append({"concepto": c, "base": 0, "retencion": 0})

    # ---- 5. Totales finales ----
    total_decl = total_ret_renta + valor_autorret + total_ret_iva

    totales = {
        "base_autorretencion":     base_autorret,
        "valor_autorretencion":    valor_autorret,
        "total_retenciones_renta": total_ret_renta + valor_autorret,
        "total_retenciones_iva":   total_ret_iva,
        "total_declaracion":       total_decl,
        "tarifa_aplicada":         tarifa_pct,
    }

    return {
        "empresa":               auxiliar.get("empresa"),
        "nit_empresa":           auxiliar.get("nit_empresa"),
        "periodo":               auxiliar.get("periodo"),
        "auxiliar":              auxiliar,
        "balance":               balance,
        "movimientos":           movimientos,
        "retenciones_agrupadas": retenciones_agrupadas,
        "autorretenciones":      autorretenciones,
        "totales":               totales,
        "autorret_detalle":      autorret,
        "advertencias":          advertencias,
    }
