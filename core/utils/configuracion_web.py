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
}

COMPROBANTES_DEFAULT = {
    "CM": "13",
    "FE": "1",
    "NC": "5",
    "DS": "7",
    "NOM": "8",
    "PROV": "9",
    "CE": "2",
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

    def prefijos_set(self, clave: str, default=None) -> set:
        """Parámetros que son listas de prefijos separados por coma."""
        valor = self._parametros.get(clave, default or "")
        if not valor:
            return set()
        return {p.strip().upper() for p in str(valor).split(",") if p.strip()}
