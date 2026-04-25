"""
Reemplazo de 'configuracion.py' del .exe original.

En el .exe, la configuración era global y se leía de archivos Excel locales
(cuentas.xlsx, mapeos.xlsx) de la empresa activa. En web, la configuración
es POR EMPRESA y viene de:

  1. Archivos Excel subidos a Supabase Storage (cuentas/mapeos de cada empresa)
  2. Tabla 'parametros_empresa' en Supabase (para valores simples)

Esta clase Configuracion se instancia con el ID de empresa y expone las
mismas funciones que el módulo configuracion.py original, para que los
procesadores se porten con cambios mínimos.
"""
from __future__ import annotations
import io
from typing import Optional
import pandas as pd


# Valores por defecto si la empresa no tiene configurado algo
DEFAULTS = {
    "CENTRO_COSTOS_DEFAULT": "PRINCIPAL",
    "CUENTA_CAJA_MENOR_EGRESO": "11050500",
    "CUENTA_CAJA_MENOR_DEFAULT_T1": "23359501",
    "CUENTA_CAJA_MENOR_DEFAULT_T2": "22050501",
    # ---- Compras DIAN (v2.6) ----
    "APLICAR_RETENCIONES_COMPRAS": "SI",
    "RESPETAR_HISTORICO_BALANCE": "SI",
    "UVT_VIGENTE": "52374",
    "CUENTA_DIAN_COMPRA": "620505",
    "CUENTA_DIAN_PROVEEDOR": "22050501",
    "CUENTA_DIAN_PROVEEDOR_SERVICIOS": "23359501",
    "CUENTA_IVA_MERCANCIA": "24080201",
    "CUENTA_IVA_SERVICIOS": "24080308",
    "CUENTA_DIAN_NC_IVA": "24080204",
    "CUENTA_IMP_CONSUMO": "511575",
    "CUENTA_ICUI": "511586",
    "CUENTA_INPP_IBUA": "519525",
    "CUENTA_RETEIVA_15": "23670109",
}

COMPROBANTES_DEFAULT = {
    "CM": "13",
    "FE": "1",
    "NC": "5",
    "DS": "7",
    "NOM": "8",
    "PROV": "9",
    "CE": "2",
    # ---- Compras DIAN (v2.6) ----
    "FDI": "3",   # Factura DIAN recibida
    "NDI": "7",   # Nota crédito DIAN recibida
    "PBD": "2",   # Pago banco DIAN (egreso)
}


class Configuracion:
    """Configuración de una empresa. Equivalente al módulo configuracion.py
    del .exe original, pero por empresa."""

    def __init__(
        self,
        parametros: Optional[dict] = None,
        comprobantes: Optional[dict] = None,
        cuentas_df: Optional[pd.DataFrame] = None,
        mapeos_sheets: Optional[dict] = None,
    ):
        """
        Args:
            parametros: dict de parámetros simples (clave: valor)
            comprobantes: dict de códigos de comprobante ('CM': '13', ...)
            cuentas_df: DataFrame con el PUC (columnas 'CUENTA' y 'NOMBRE')
            mapeos_sheets: dict con las hojas del archivo de mapeos.xlsx,
                          ej: {'Caja_Menor_Beneficiarios': DataFrame, ...}
        """
        self._parametros = {**DEFAULTS, **(parametros or {})}
        self._comprobantes = {**COMPROBANTES_DEFAULT, **(comprobantes or {})}
        self._cuentas = {}
        if cuentas_df is not None:
            self._cargar_cuentas_df(cuentas_df)
        self._mapeos = mapeos_sheets or {}

        # Cargar comprobantes y parámetros desde la hoja Parametros si existe
        # (los del archivo pisan a los DEFAULTS pero NO a los pasados explícitos)
        self._cargar_extras_de_mapeos()

    # ----- Factories -----

    @classmethod
    def vacia(cls) -> "Configuracion":
        """Configuración mínima con solo valores por defecto. Útil para
        empresas recién creadas que no han subido sus archivos."""
        return cls()

    @classmethod
    def desde_excel(
        cls,
        cuentas_bytes: Optional[bytes] = None,
        mapeos_bytes: Optional[bytes] = None,
        parametros: Optional[dict] = None,
    ) -> "Configuracion":
        """Construye la configuración a partir de bytes de archivos Excel
        (ej: descargados de Supabase Storage).

        Los archivos cuentas.xlsx y mapeos.xlsx mantienen la misma estructura
        del .exe original.
        """
        cuentas_df = None
        if cuentas_bytes:
            try:
                cuentas_df = pd.read_excel(
                    io.BytesIO(cuentas_bytes), engine="openpyxl"
                )
            except Exception as e:
                print(f"Aviso: no se pudo leer cuentas.xlsx: {e}")

        mapeos_sheets = {}
        if mapeos_bytes:
            try:
                xl = pd.ExcelFile(io.BytesIO(mapeos_bytes), engine="openpyxl")
                for hoja in xl.sheet_names:
                    mapeos_sheets[hoja] = xl.parse(hoja)
            except Exception as e:
                print(f"Aviso: no se pudo leer mapeos.xlsx: {e}")

        return cls(
            parametros=parametros,
            cuentas_df=cuentas_df,
            mapeos_sheets=mapeos_sheets,
        )

    # ----- Carga interna -----

    def _cargar_cuentas_df(self, df: pd.DataFrame):
        cols = {str(c).strip().upper(): c for c in df.columns}
        col_cuenta = cols.get("CUENTA")
        col_nombre = cols.get("NOMBRE")
        if not col_cuenta or not col_nombre:
            return
        for _, fila in df.iterrows():
            cuenta = str(fila[col_cuenta]).strip()
            nombre = str(fila[col_nombre]).strip()
            if cuenta and cuenta != "nan":
                self._cuentas[cuenta] = nombre

    def _cargar_extras_de_mapeos(self):
        """Lee la hoja Parametros y Comprobantes de mapeos.xlsx, si existen,
        y los integra en los dicts internos. Los DEFAULTS y lo pasado al
        constructor tienen prioridad sobre lo del Excel SOLO si fue pasado
        explícitamente; la hoja del Excel pisa a los DEFAULTS de fábrica."""
        # Hoja Parametros
        df_par = self._mapeos.get("Parametros")
        if df_par is not None:
            cols = {str(c).strip().upper(): c for c in df_par.columns}
            col_clave = cols.get("PARÁMETRO") or cols.get("PARAMETRO")
            col_valor = cols.get("VALOR")
            if col_clave and col_valor:
                for _, f in df_par.iterrows():
                    clave = str(f[col_clave]).strip()
                    valor = str(f[col_valor]).strip()
                    if clave and clave.lower() != "nan" and valor.lower() != "nan":
                        # Solo agrega si no fue ya configurado explícitamente
                        # (DEFAULTS sí se pueden pisar; valores del usuario no)
                        # Como _parametros = DEFAULTS + user, basta con pisar
                        # los DEFAULTS y mantener los del usuario.
                        # Estrategia simple: el Excel pisa SIEMPRE, y luego
                        # el caller puede volver a pasar parametros si quiere.
                        self._parametros.setdefault(clave, valor)
                        # Nota: setdefault evita pisar lo que ya viene del
                        # constructor. Para forzar, el caller pasa parametros.

        # Hoja Comprobantes
        df_comp = self._mapeos.get("Comprobantes")
        if df_comp is not None:
            cols = {str(c).strip().upper(): c for c in df_comp.columns}
            col_pre = cols.get("PREFIJO")
            col_cod = cols.get("CÓDIGO") or cols.get("CODIGO")
            if col_pre and col_cod:
                for _, f in df_comp.iterrows():
                    pre = str(f[col_pre]).strip()
                    cod = str(f[col_cod]).strip()
                    if pre and cod and pre.lower() != "nan":
                        self._comprobantes.setdefault(pre, cod)

    # ----- API pública (misma que configuracion.py original) -----

    def parametro(self, clave: str, default=None):
        return self._parametros.get(clave, default)

    def codigo_comprobante(self, prefijo: str, default=None):
        return self._comprobantes.get(prefijo, default)

    def cuentas(self) -> dict:
        return self._cuentas

    def nombre_cuenta(self, cuenta: str) -> str:
        return self._cuentas.get(str(cuenta).strip(), "")

    def caja_menor_beneficiarios(self) -> list:
        """Lista de reglas [{palabra_clave, cuenta}, ...] para mapear el
        nombre del beneficiario a una cuenta contable."""
        df = self._mapeos.get("Caja_Menor_Beneficiarios")
        if df is None:
            return []
        reglas = []
        cols = {str(c).strip().upper(): c for c in df.columns}
        col_pk = cols.get("PALABRA_CLAVE") or cols.get("PALABRA CLAVE")
        col_cu = cols.get("CUENTA")
        if not col_pk or not col_cu:
            return []
        for _, fila in df.iterrows():
            pk = str(fila[col_pk]).strip()
            cu = str(fila[col_cu]).strip()
            if pk and pk.lower() != "nan":
                reglas.append({"palabra_clave": pk, "cuenta": cu})
        return reglas

    def dian_proveedores(self) -> list:
        """Lista de reglas de la hoja DIAN_Proveedores (mapeos.xlsx).

        Cada regla es un dict con:
            palabra_clave:   str — palabra que debe aparecer en el nombre
                                   del emisor para que la regla aplique.
            cuenta_gasto:    str — cuenta de gasto (Db).  Vacío si solo
                                   queremos marcar tipo especial.
            cuenta_pasivo:   str — cuenta de pasivo (Cr). Vacío idem.
            tipo_retencion:  str — COMPRA_NATURAL, COMPRA_JURIDICA,
                                   HONORARIOS, COMISIONES, ARRENDAMIENTO,
                                   o vacío.
            tipo_especial:   str — AUTORRET, RST o vacío.
        """
        df = self._mapeos.get("DIAN_Proveedores")
        if df is None:
            return []
        reglas = []
        cols = {str(c).strip().upper(): c for c in df.columns}
        col_pk = cols.get("PALABRA_CLAVE") or cols.get("PALABRA CLAVE")
        col_cg = cols.get("CUENTA GASTO (DB)") or cols.get("CUENTA_GASTO")
        col_cp = cols.get("CUENTA PASIVO (CR)") or cols.get("CUENTA_PASIVO")
        col_tr = cols.get("TIPO RETENCIÓN") or cols.get("TIPO RETENCION") \
                 or cols.get("TIPO_RETENCION")
        col_te = cols.get("TIPO ESPECIAL") or cols.get("TIPO_ESPECIAL")
        if not col_pk:
            return []

        def _val(fila, col):
            if not col:
                return ""
            v = str(fila[col]).strip()
            return "" if v.lower() == "nan" else v

        for _, fila in df.iterrows():
            pk = _val(fila, col_pk)
            if not pk:
                continue
            te = _val(fila, col_te).upper()
            if te not in ("AUTORRET", "RST", ""):
                te = ""
            reglas.append({
                "palabra_clave": pk,
                "cuenta_gasto": _val(fila, col_cg),
                "cuenta_pasivo": _val(fila, col_cp),
                "tipo_retencion": _val(fila, col_tr).upper(),
                "tipo_especial": te,
            })
        return reglas

    def retenciones_compras(self) -> dict:
        """Reglas de retefuente por tipo (hoja Retenciones_Compras).

        Returns:
            dict {tipo_upper: {tarifa: float, base_uvt: float, cuenta: str}}
        """
        df = self._mapeos.get("Retenciones_Compras")
        if df is None:
            return {}
        cols = {str(c).strip().upper(): c for c in df.columns}
        col_tipo = cols.get("TIPO")
        col_tar = cols.get("TARIFA %") or cols.get("TARIFA")
        col_uvt = cols.get("BASE UVT MÍNIMA") or cols.get("BASE UVT MINIMA") \
                  or cols.get("BASE_UVT")
        col_cu = cols.get("CUENTA CRÉDITO") or cols.get("CUENTA CREDITO") \
                 or cols.get("CUENTA")
        if not col_tipo or not col_tar or not col_cu:
            return {}

        out = {}
        for _, f in df.iterrows():
            tipo = str(f[col_tipo]).strip()
            tarifa_s = str(f[col_tar]).strip().replace(",", ".")
            uvt_s = str(f[col_uvt]).strip().replace(",", ".") if col_uvt else "0"
            cuenta = str(f[col_cu]).strip()
            if not tipo or tipo.lower() == "nan" or not cuenta:
                continue
            try:
                tarifa = float(tarifa_s)
                uvt = float(uvt_s) if uvt_s and uvt_s.lower() != "nan" else 0.0
            except ValueError:
                continue
            out[tipo.upper()] = {
                "tarifa": tarifa,
                "base_uvt": uvt,
                "cuenta": cuenta,
            }
        return out

    def prefijos_set(self, clave: str, default=None) -> set:
        """Parámetros que son listas de prefijos separados por coma."""
        valor = self._parametros.get(clave, default or "")
        if not valor:
            return set()
        return {p.strip().upper() for p in str(valor).split(",") if p.strip()}
