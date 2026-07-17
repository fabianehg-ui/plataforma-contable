"""
core/f350/muisca_adapter.py
Puente entre el modulo F350 existente y el cliente de Muisca.

Convierte el resultado de `core.f350.procesador.procesar_declaracion(...)`
en {numero_casilla: valor}, que es lo que MuiscaF350Client.construir_doc() necesita.

Usa los mapeos del propio repo:
  - obtener_casillas_f350(concepto, tipo_tercero)  -> retenciones a terceros
    OJO: espera el tipo como texto ("Persona Natural" / "Persona Juridica").
  - AUTORRET_CASILLAS_F350[concepto] -> (base, retencion) para autorretenciones.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.f350.casillas import obtener_casillas_f350, AUTORRET_CASILLAS_F350

# Plantilla del F350 v10 (misma estructura que consume la extensión del navegador)
_PLANTILLA_EXT = Path(__file__).with_name("plantilla_f350_v10.json")

# Totales del F350 (Res. 000031/2024)
CASILLA_TOTAL_RENTA = 130
CASILLA_TOTAL_IVA = 134
CASILLA_TOTAL_RETENCIONES = 136
CASILLA_SANCIONES = 137
CASILLA_TOTAL_MAS_SANCIONES = 138


def _tipo_texto(tipo) -> str:
    """Normaliza cualquier variante a lo que espera obtener_casillas_f350:
    exactamente 'Persona Natural' para PN; cualquier otra cosa se trata como PJ."""
    t = str(tipo or "").strip().upper()
    es_natural = t.startswith("PN") or "NATURAL" in t
    return "Persona Natural" if es_natural else "Persona Jurídica"


def casillas_desde_procesado(resultado: dict, incluir_totales: bool = True) -> dict:
    casillas: dict = {}
    avisos: list = []

    def add(cas, valor):
        if not cas or not valor:
            return
        casillas[int(cas)] = casillas.get(int(cas), 0) + int(round(float(valor)))

    # 1) Retenciones practicadas a terceros (base + retencion, por tipo de persona)
    filas = resultado.get("retenciones_agrupadas") or resultado.get("movimientos") or []
    for m in filas:
        concepto = m.get("concepto") or m.get("concepto_f350")
        if not concepto:
            continue
        tipo = m.get("tipo_persona") or m.get("tipo_tercero") or m.get("tipo")
        base = m.get("base") or m.get("base_retencion") or 0
        ret = m.get("retencion") or m.get("valor_retencion") or 0
        es_ext = bool(m.get("es_extranjero", False))
        try:
            cbase, cret = obtener_casillas_f350(concepto, _tipo_texto(tipo), es_ext)
        except Exception as e:  # noqa: BLE001
            avisos.append("Sin casilla para '%s' (%s): %s" % (concepto, tipo, e))
            continue
        if not cret:
            avisos.append("Concepto '%s' no tiene casilla para %s." % (concepto, _tipo_texto(tipo)))
            continue
        add(cbase, base)
        add(cret, ret)

    # 2) Autorretenciones -> AUTORRET_CASILLAS_F350 (NO el mapeo de terceros)
    for a in resultado.get("autorretenciones", []) or []:
        base = a.get("base", 0)
        val = a.get("retencion", 0)
        if not base and not val:
            continue
        concepto = a.get("concepto")
        par = AUTORRET_CASILLAS_F350.get(concepto)
        if not par:
            avisos.append("Autorretencion sin casilla: '%s'." % concepto)
            continue
        cbase, cret = par
        add(cbase, base)
        add(cret, val)

    # 3) Retenciones de IVA (si el procesado las trae con casilla explicita)
    for r in resultado.get("retenciones_iva", []) or []:
        cas = r.get("casilla")
        if cas:
            add(cas, r.get("retencion", 0))

    # 4) Totales
    if incluir_totales:
        tot = resultado.get("totales", {}) or {}
        total_renta = int(round(tot.get("total_retenciones_renta", 0) or 0))
        total_iva = int(round(tot.get("total_retenciones_iva", 0) or 0))
        sanciones = int(round(tot.get("sanciones", 0) or 0))
        if total_renta:
            add(CASILLA_TOTAL_RENTA, total_renta)
        if total_iva:
            add(CASILLA_TOTAL_IVA, total_iva)
        total_ret = total_renta + total_iva
        if total_ret:
            add(CASILLA_TOTAL_RETENCIONES, total_ret)
            if sanciones:
                add(CASILLA_SANCIONES, sanciones)
            add(CASILLA_TOTAL_MAS_SANCIONES, total_ret + sanciones)

    return {"casillas": casillas, "avisos": avisos}


def generar_doc_extension(
    casillas: dict,
    *,
    nit,
    dv,
    razon_social,
    anio,
    periodo,
    actividad_economica=None,
    plantilla_path: str | None = None,
) -> dict:
    """Construye el JSON que se pega en la extensión del F350 para autollenar.

    Es la versión OFFLINE de MuiscaF350Client.construir_doc(): parte de la
    plantilla local del formulario y coloca cada casilla en su renglón
    (cs_id_{renglon}), sin conectarse a la DIAN.

    Args:
        casillas: {numero_renglon: valor} (por ej. la salida de
                  casillas_desde_procesado(...)["casillas"]).
        nit, dv, razon_social: datos del aportante (encabezado).
        anio, periodo: año y periodo (mes) de la declaración.
        actividad_economica: código CIIU principal (renglón 27). Opcional.
        plantilla_path: ruta a la plantilla; por defecto la del repo.

    Returns:
        dict con el documento completo listo para pegar en la extensión
        (misma forma que plantilla_f350_v10.json). Incluye además la clave
        'renglones_no_existentes' con los que no se encontraron, si los hay.
    """
    ruta = Path(plantilla_path) if plantilla_path else _PLANTILLA_EXT
    base = json.loads(ruta.read_text(encoding="utf-8"))

    doc = base.get("doc", base)
    cab = doc["cab"]
    cuerpo = doc["cuerpo"]
    pie = doc.get("pie", {})

    # Encabezado
    cab["id"] = -1
    cab["cs_id_1"] = int(anio)
    cab["cs_id_3"] = int(periodo)
    cab["cs_id_5"] = str(nit)
    cab["cs_id_6"] = str(dv)
    cab["cs_id_11"] = razon_social
    if actividad_economica is not None and str(actividad_economica).strip():
        cuerpo["cs_id_27"] = str(actividad_economica)

    # Casillas -> renglones
    no_existen = []
    for renglon, valor in (casillas or {}).items():
        clave = f"cs_id_{int(renglon)}"
        v = int(round(float(valor or 0)))
        if clave in cuerpo:
            cuerpo[clave] = v
        elif clave in pie:
            pie[clave] = v
        else:
            no_existen.append(int(renglon))

    resultado = {
        "doc": doc,
        "status": base.get("status", 200),
        "statusText": base.get("statusText", "OK"),
    }
    if no_existen:
        resultado["renglones_no_existentes"] = sorted(no_existen)
    return resultado


def json_extension_texto(doc_extension: dict) -> str:
    """Serializa el DOC completo del F350 a texto JSON (formato cs_id_...).

    OJO: esto NO es lo que pide la extensión 'DIAN F350 — Llenar renglones';
    esa extensión usa el mapa plano {renglon: valor} de json_casillas_planas().
    Se conserva por si se necesita el documento completo del formulario.
    """
    limpio = {k: v for k, v in doc_extension.items() if k != "renglones_no_existentes"}
    return json.dumps(limpio, ensure_ascii=False, indent=1)


def json_casillas_planas(casillas: dict) -> str:
    """JSON plano {renglon: valor} para pegar en la extensión del F350.

    Formato exacto que espera el cuadro 'CASILLAS (JSON DE TU PLATAFORMA)':
        {"29": 5533840, "42": 608723, "31": 7163000, "44": 190000}
    Llaves = número de renglón (string), valores = enteros.
    """
    plano = {
        str(int(k)): int(round(float(v or 0)))
        for k, v in (casillas or {}).items()
        if int(round(float(v or 0))) != 0
    }
    return json.dumps(plano, ensure_ascii=False)
