"""
Tests de CORRECCIÓN de movimientos — usan un Supabase falso en memoria,
así se valida la lógica (update/delete por id, reemplazo de comprobante y
respeto al período protegido) sin tocar la red.

Ejecutar: pytest tests/test_correcciones.py -v
"""
import pandas as pd
import pytest

from core.contable import servicio_contable as cont


# ============================================================
# Fake Supabase (mínimo, suficiente para estas funciones)
# ============================================================

class _Result:
    def __init__(self, data):
        self.data = data


class _Table:
    def __init__(self):
        self.rows = []
        self._seq = 0

    def next_id(self):
        self._seq += 1
        return f"id{self._seq}"


class _Query:
    def __init__(self, table):
        self.t = table
        self._op = None
        self._payload = None
        self._filters = []
        self._limit = None

    def select(self, *a, **k):
        self._op = "select"; return self

    def insert(self, payload):
        self._op = "insert"; self._payload = payload; return self

    def update(self, payload):
        self._op = "update"; self._payload = payload; return self

    def delete(self):
        self._op = "delete"; return self

    def eq(self, k, v):
        self._filters.append((k, v)); return self

    def gte(self, k, v): return self
    def lte(self, k, v): return self
    def ilike(self, k, v): return self
    def order(self, *a, **k): return self
    def range(self, *a, **k): return self

    def limit(self, n):
        self._limit = n; return self

    def _match(self, row):
        return all(str(row.get(k)) == str(v) for k, v in self._filters)

    def execute(self):
        rows = self.t.rows
        if self._op == "select":
            sel = [dict(r) for r in rows if self._match(r)]
            if self._limit:
                sel = sel[:self._limit]
            return _Result(sel)
        if self._op == "insert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for p in payload:
                p = dict(p)
                p.setdefault("id", self.t.next_id())
                rows.append(p)
                out.append(p)
            return _Result(out)
        if self._op == "update":
            upd = [r for r in rows if self._match(r)]
            for r in upd:
                r.update(self._payload)
            return _Result([dict(r) for r in upd])
        if self._op == "delete":
            removed = [dict(r) for r in rows if self._match(r)]
            self.t.rows[:] = [r for r in rows if not self._match(r)]
            return _Result(removed)
        return _Result([])


class FakeSB:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return _Query(self.tables.setdefault(name, _Table()))


EMP = "emp1"


def _sb_con_asiento():
    sb = FakeSB()
    movs = sb.tables.setdefault("cn_movimientos", _Table())
    movs.rows.extend([
        {"id": "A", "empresa_id": EMP, "periodo": "202606", "comprobante": "1",
         "documento": "100", "fecha": "2026-06-15", "cuenta": "519595", "nit": "800",
         "detalle": "Papel", "tr": "1", "valor": 100000, "base": 100000, "centro_costo": "01"},
        {"id": "B", "empresa_id": EMP, "periodo": "202606", "comprobante": "1",
         "documento": "100", "fecha": "2026-06-15", "cuenta": "111005", "nit": "800",
         "detalle": "Papel", "tr": "2", "valor": 100000, "base": 0, "centro_costo": ""},
    ])
    sb.tables.setdefault("cn_periodos", _Table())
    return sb


def _proteger(sb, periodo):
    sb.tables["cn_periodos"].rows.append(
        {"empresa_id": EMP, "periodo": periodo, "estado": "P"})


class TestActualizarMovimiento:
    def test_cambia_solo_campos_permitidos(self):
        sb = _sb_con_asiento()
        cont.actualizar_movimiento(sb, EMP, "A", {"detalle": "Papelería junio", "xyz": "no"})
        a = [r for r in sb.tables["cn_movimientos"].rows if r["id"] == "A"][0]
        assert a["detalle"] == "Papelería junio"
        assert "xyz" not in a

    def test_normaliza_valor(self):
        # En la app el valor llega como entero desde el editor numérico.
        sb = _sb_con_asiento()
        cont.actualizar_movimiento(sb, EMP, "A", {"valor": 150000, "base": "$ 150000"})
        a = [r for r in sb.tables["cn_movimientos"].rows if r["id"] == "A"][0]
        assert a["valor"] == 150000
        assert a["base"] == 150000

    def test_bloquea_si_protegido(self):
        sb = _sb_con_asiento()
        _proteger(sb, "202606")
        with pytest.raises(PermissionError):
            cont.actualizar_movimiento(sb, EMP, "A", {"detalle": "x"})


class TestEliminarMovimiento:
    def test_elimina_por_id(self):
        sb = _sb_con_asiento()
        cont.eliminar_movimiento(sb, EMP, "A")
        ids = {r["id"] for r in sb.tables["cn_movimientos"].rows}
        assert ids == {"B"}

    def test_bloquea_si_protegido(self):
        sb = _sb_con_asiento()
        _proteger(sb, "202606")
        with pytest.raises(PermissionError):
            cont.eliminar_movimiento(sb, EMP, "A")


class TestReemplazarComprobante:
    def test_reemplaza_asiento(self):
        sb = _sb_con_asiento()
        df = pd.DataFrame([
            {"CUENTA": "519595", "COMPROBANTE": "1", "FECHA": "2026-06-15",
             "DOCUMENTO": "100", "DOC REFERENCIA": "100", "NIT": "800",
             "DETALLE": "Corregido", "TR": "1", "VALOR": 120000, "BASE": 120000,
             "CENTRO DE COSTO": "01"},
            {"CUENTA": "111005", "COMPROBANTE": "1", "FECHA": "2026-06-15",
             "DOCUMENTO": "100", "DOC REFERENCIA": "100", "NIT": "800",
             "DETALLE": "Corregido", "TR": "2", "VALOR": 120000, "BASE": 0,
             "CENTRO DE COSTO": ""},
        ], columns=cont.COLUMNAS_PLANO)
        n = cont.reemplazar_comprobante(sb, EMP, "202606", "1", "100", df)
        assert n == 2
        rows = sb.tables["cn_movimientos"].rows
        assert len(rows) == 2
        assert all(r["detalle"] == "Corregido" for r in rows)
        assert all(int(r["valor"]) == 120000 for r in rows)
        # los ids viejos ya no están (se reemplazaron)
        assert {"A", "B"}.isdisjoint({r["id"] for r in rows})

    def test_bloquea_si_protegido(self):
        sb = _sb_con_asiento()
        _proteger(sb, "202606")
        df = pd.DataFrame([{"CUENTA": "1", "COMPROBANTE": "1", "FECHA": "2026-06-15",
                            "DOCUMENTO": "100", "DOC REFERENCIA": "100", "NIT": "",
                            "DETALLE": "", "TR": "1", "VALOR": 1, "BASE": 0,
                            "CENTRO DE COSTO": ""}], columns=cont.COLUMNAS_PLANO)
        with pytest.raises(PermissionError):
            cont.reemplazar_comprobante(sb, EMP, "202606", "1", "100", df)
        # no debe haber tocado nada
        assert len(sb.tables["cn_movimientos"].rows) == 2


class TestBuscarMovimientos:
    def test_filtra_por_cuenta(self):
        sb = _sb_con_asiento()
        r = cont.buscar_movimientos(sb, EMP, cuenta="519595")
        assert len(r) == 1 and r[0]["id"] == "A"

    def test_filtra_por_comprobante_y_documento(self):
        sb = _sb_con_asiento()
        r = cont.buscar_movimientos(sb, EMP, comprobante="1", documento="100")
        assert len(r) == 2

    def test_sin_coincidencias(self):
        sb = _sb_con_asiento()
        assert cont.buscar_movimientos(sb, EMP, nit="999") == []
