"""
Tests del PUENTE CONTABLE (integracion) con Supabase falso en memoria.

Ejecutar: pytest tests/test_integracion.py -v
"""
import pandas as pd
import pytest

from core.contable import integracion as integ
from core.contable import servicio_contable as cont
from tests.test_correcciones import FakeSB, _Table, EMP


def _plano(filas):
    return pd.DataFrame(filas, columns=cont.COLUMNAS_PLANO)


def _asiento_ventas():
    return _plano([
        {"CUENTA": "130505", "COMPROBANTE": "5", "FECHA": "2026-06-15", "DOCUMENTO": "V1",
         "DOC REFERENCIA": "V1", "NIT": "900", "DETALLE": "Venta", "TR": "1",
         "VALOR": 1190000, "BASE": 0, "CENTRO DE COSTO": ""},
        {"CUENTA": "413501", "COMPROBANTE": "5", "FECHA": "2026-06-15", "DOCUMENTO": "V1",
         "DOC REFERENCIA": "V1", "NIT": "900", "DETALLE": "Venta", "TR": "2",
         "VALOR": 1000000, "BASE": 0, "CENTRO DE COSTO": ""},
        {"CUENTA": "240810", "COMPROBANTE": "5", "FECHA": "2026-06-15", "DOCUMENTO": "V1",
         "DOC REFERENCIA": "V1", "NIT": "900", "DETALLE": "IVA", "TR": "2",
         "VALOR": 190000, "BASE": 0, "CENTRO DE COSTO": ""},
    ])


class TestCuadrePlano:
    def test_cuadra(self):
        c = integ.cuadre_plano(_asiento_ventas())
        assert c["cuadra"] and c["debitos"] == 1190000 == c["creditos"]

    def test_vacio(self):
        assert integ.cuadre_plano(pd.DataFrame())["cuadra"] is True


class TestPlanoTextoADf:
    def test_tsv_sin_encabezado(self):
        txt = ("143501\t3\t2026-06-15\tF1\tF1\t800\tCompra\t1\t100000\t100000\t01\n"
               "220505\t3\t2026-06-15\tF1\tF1\t800\tCompra\t2\t100000\t\t")
        df = integ.plano_texto_a_df(txt)
        assert list(df.columns) == cont.COLUMNAS_PLANO
        assert len(df) == 2
        assert df.iloc[0]["CUENTA"] == "143501"
        assert integ.cuadre_plano(df)["cuadra"] is True

    def test_bytes_y_sep(self):
        raw = b"sep=\t\n143501\t3\t2026-06-15\tF1\tF1\t800\tX\t1\t50\t0\t\n"
        df = integ.plano_texto_a_df(raw)
        assert len(df) == 1 and df.iloc[0]["VALOR"] == "50"

    def test_vacio(self):
        assert len(integ.plano_texto_a_df("")) == 0


class TestContabilizarYTrazabilidad:
    def test_contabiliza_y_aparece_por_origen(self):
        sb = FakeSB(); sb.tables.setdefault("cn_movimientos", _Table()); sb.tables.setdefault("cn_periodos", _Table())
        r = integ.contabilizar(sb, EMP, "202606", _asiento_ventas(), "ventas")
        assert r["insertados"] == 3
        res = integ.resumen_por_origen(sb, EMP, "202606")
        assert len(res) == 1
        assert res[0]["origen"] == "ventas"
        assert res[0]["etiqueta"] == "Ventas C13"
        assert res[0]["cuadra"] is True

    def test_reemplazar_no_duplica(self):
        sb = FakeSB(); sb.tables.setdefault("cn_movimientos", _Table()); sb.tables.setdefault("cn_periodos", _Table())
        integ.contabilizar(sb, EMP, "202606", _asiento_ventas(), "ventas")
        integ.contabilizar(sb, EMP, "202606", _asiento_ventas(), "ventas", reemplazar=True)
        movs = cont.listar_movimientos(sb, EMP, "202606")
        assert len(movs) == 3   # no se duplicó

    def test_reversar_borra_solo_ese_origen(self):
        sb = FakeSB(); sb.tables.setdefault("cn_movimientos", _Table()); sb.tables.setdefault("cn_periodos", _Table())
        integ.contabilizar(sb, EMP, "202606", _asiento_ventas(), "ventas")
        # otra causación de otro origen
        otro = _asiento_ventas().copy(); otro["COMPROBANTE"] = "2"
        integ.contabilizar(sb, EMP, "202606", otro, "compras")
        integ.reversar_origen(sb, EMP, "202606", "ventas")
        origenes = {m["origen"] for m in cont.listar_movimientos(sb, EMP, "202606")}
        assert origenes == {"compras"}

    def test_reversar_bloquea_periodo_protegido(self):
        sb = FakeSB(); sb.tables.setdefault("cn_movimientos", _Table())
        sb.tables.setdefault("cn_periodos", _Table()).rows.append(
            {"empresa_id": EMP, "periodo": "202606", "estado": "P"})
        with pytest.raises(PermissionError):
            integ.reversar_origen(sb, EMP, "202606", "ventas")


class TestRetencionesPracticadas:
    def test_lee_2365_por_nit(self):
        sb = FakeSB(); movs = sb.tables.setdefault("cn_movimientos", _Table())
        # causación de compra con retefuente (Cr 2365) a dos proveedores
        movs.rows.extend([
            {"empresa_id": EMP, "periodo": "202606", "cuenta": "236540", "nit": "800",
             "tr": "2", "valor": 25000, "base": 1000000},
            {"empresa_id": EMP, "periodo": "202606", "cuenta": "236540", "nit": "801",
             "tr": "2", "valor": 10000, "base": 400000},
            {"empresa_id": EMP, "periodo": "202606", "cuenta": "111005", "nit": "800",
             "tr": "1", "valor": 25000, "base": 0},  # no es 2365, se ignora
        ])
        df = integ.retenciones_practicadas(sb, EMP, "202601", "202612")
        by = {r["NIT"]: r for _, r in df.iterrows()}
        assert by["800"]["Retención"] == 25000
        assert by["801"]["Retención"] == 10000
        assert "111005" not in set(df["Cuenta"])
