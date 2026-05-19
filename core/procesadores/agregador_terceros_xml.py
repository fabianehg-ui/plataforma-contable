"""
core/procesadores/agregador_terceros_xml.py

Agrega los terceros (emisores) detectados en los XMLs procesados por
`procesador_dian_xml.procesar_multiples_zips` y los convierte en un
`maestro_terceros`-like dict para alimentar `exportador_nits_siigo`.

El propósito es exponer en la página 5a_DIAN_XML el mismo flujo de
"terceros nuevos para Siigo" que ya existía en la página 2 (Token DIAN).

API:
    construir_maestro_desde_resultados(resultados) -> dict
        Recibe la lista de `ResultadoProcesamiento` y devuelve un dict con
        la forma esperada por `exportar_nits_desde_maestro`:
            {
              "terceros": {
                "<nit_normalizado>": {
                    "nombre": ...,
                    "direccion": ...,
                    "ciudad": ...,
                    "telefono": ...,
                    "email": ...,
                    "celular": ...,
                    "tax_level_principal": ...,
                    "actividad_economica": ...,
                }
              }
            }

    detectar_nits_nuevos(maestro, ruta_historico_compras=None) -> set
        Compara con un histórico opcional y devuelve los NITs nuevos.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Optional


def _normalizar_nit(nit: str) -> str:
    """Misma normalización que exportador_nits_siigo.normalizar_nit."""
    if not nit:
        return ""
    s = str(nit).strip()
    s = s.split("-")[0]
    s = re.sub(r"\D", "", s)
    return s


def construir_maestro_desde_resultados(resultados: Iterable) -> dict:
    """Recorre los `ResultadoProcesamiento` y agrega los emisores únicos.

    Cuando el mismo NIT aparece en varios documentos, se conserva la
    información más completa (la que tenga más campos no vacíos).
    """
    terceros: dict[str, dict] = {}

    for r in resultados:
        for doc in getattr(r, "documentos", []) or []:
            nit_norm = _normalizar_nit(doc.nit_emisor)
            if not nit_norm:
                continue

            datos_nuevos = {
                "nombre": (doc.nombre_emisor or "").strip(),
                "direccion": (getattr(doc, "direccion_emisor", "") or "").strip(),
                "ciudad": (getattr(doc, "ciudad_emisor", "") or "").strip(),
                "codigo_ciudad": (getattr(doc, "codigo_ciudad_emisor", "") or "").strip(),
                "telefono": (getattr(doc, "telefono_emisor", "") or "").strip(),
                "email": (getattr(doc, "email_emisor", "") or "").strip(),
                "celular": (getattr(doc, "telefono_emisor", "") or "").strip(),
                "tax_level_principal": (doc.regimen_emisor or "").strip(),
                "actividad_economica": (
                    getattr(doc, "actividad_economica_emisor", "") or ""
                ).strip(),
            }

            if nit_norm not in terceros:
                terceros[nit_norm] = datos_nuevos
                continue

            # Merge: rellenar campos vacíos del existente con los nuevos
            existente = terceros[nit_norm]
            for k, v in datos_nuevos.items():
                if v and not existente.get(k):
                    existente[k] = v

    return {"terceros": terceros}


def detectar_nits_nuevos(
    maestro: dict,
    ruta_historico_compras: Optional[Path | str] = None,
    nits_extra_conocidos: Optional[Iterable[str]] = None,
) -> set[str]:
    """Devuelve el set de NITs (normalizados) que NO están en el histórico.

    El histórico se lee de `mapeo_compras_historico.json` (formato:
    `{"mapeo": [{"nit": "...", ...}, ...]}`). Si la ruta no existe, todos
    los NITs del maestro se consideran nuevos.

    `nits_extra_conocidos` permite pasar un set adicional de NITs que la
    UI considera ya conocidos (p.ej. los del mapeo_nits.json de la empresa).
    """
    nits_conocidos: set[str] = set()

    if ruta_historico_compras:
        ruta = Path(ruta_historico_compras)
        if ruta.exists():
            try:
                with open(ruta, encoding="utf-8") as f:
                    hist = json.load(f)
                for entry in hist.get("mapeo", []) or []:
                    nit = _normalizar_nit(str(entry.get("nit", "")))
                    if nit:
                        nits_conocidos.add(nit)
            except (json.JSONDecodeError, OSError):
                pass

    if nits_extra_conocidos:
        for n in nits_extra_conocidos:
            n_norm = _normalizar_nit(str(n))
            if n_norm:
                nits_conocidos.add(n_norm)

    nits_maestro = {_normalizar_nit(k) for k in maestro.get("terceros", {}).keys()}
    nits_maestro.discard("")
    return nits_maestro - nits_conocidos
