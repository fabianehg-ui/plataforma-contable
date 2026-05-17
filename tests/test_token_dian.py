"""
Smoke test del módulo Procesar Token DIAN.

Mockea requests.Session para simular el portal DIAN y verifica:
  1. autenticar() obtiene CSRF
  2. listar_documentos() pagina y filtra
  3. descargar_zip() valida el ZIP
  4. clasificar_documentos() categoriza correctamente
  5. extraer_xml_de_zip_dian() funciona
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import io
import json
import zipfile
from unittest.mock import patch, MagicMock

from core.procesadores import cliente_token_dian as cli
from core.procesadores import clasificador_documentos as clf


# ────────────────────────────────────────────────────────────
# Helpers para fabricar respuestas DIAN simuladas
# ────────────────────────────────────────────────────────────

CSRF_DUMMY = "AAAAAA_FAKE_CSRF_TOKEN_BBBBBB"

def html_con_csrf():
    return f'<html><body><form><input name="__RequestVerificationToken" value="{CSRF_DUMMY}"></form></body></html>'


def mock_response(status=200, text="", content=b"", json_data=None):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.content = content
    r.url = "https://catalogo-vpfe.dian.gov.co/"
    r.headers = {}
    if json_data is not None:
        r.json = MagicMock(return_value=json_data)
    r.raise_for_status = MagicMock()
    if status >= 400:
        from requests import HTTPError
        r.raise_for_status.side_effect = HTTPError(f"{status}")
    return r


def make_doc(track_id, folio, tipo, sender, receiver, valor, fecha_ms, sender_name="Emisor", receiver_name="Receptor"):
    return {
        "Id": track_id,
        "SerieAndNumber": folio,
        "DocumentTypeId": tipo,
        "DocumentTypeName": cli.TIPOS_DOC.get(tipo, "?"),
        "SenderCode": sender,
        "SenderName": sender_name,
        "ReceiverCode": receiver,
        "ReceiverName": receiver_name,
        "TotalAmount": valor,
        "EmissionDate": f"/Date({fecha_ms})/",
    }


def fake_zip_with_xml(xml_content):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("documento.xml", xml_content)
        zf.writestr("documento.pdf", b"%PDF-1.4 fake pdf")
    return buf.getvalue()


# ────────────────────────────────────────────────────────────
# TESTS
# ────────────────────────────────────────────────────────────

def test_autenticar_ok():
    """Token válido devuelve sesión con CSRF capturado."""
    with patch("core.procesadores.cliente_token_dian.requests.Session") as MockS:
        sess = MagicMock()
        sess.cookies = MagicMock()
        sess.cookies.get = MagicMock(return_value=None)
        sess.get = MagicMock(return_value=mock_response(200, text=html_con_csrf()))
        sess.headers = MagicMock()
        sess.headers.update = MagicMock()
        MockS.return_value = sess

        url = "https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=A%7CB&rk=901038325&token=abc-123"
        s = cli.autenticar(url)

        assert s.csrf_token == CSRF_DUMMY, f"CSRF esperado {CSRF_DUMMY}, recibido {s.csrf_token}"
        assert s.nit_cuenta == "901038325"
        assert s.partition_key == "A|B"
    print("✅ test_autenticar_ok")


def test_autenticar_token_expirado():
    """Token expirado → redirige a login → TokenInvalido."""
    with patch("core.procesadores.cliente_token_dian.requests.Session") as MockS:
        sess = MagicMock()
        sess.cookies = MagicMock(); sess.cookies.get = MagicMock(return_value=None)
        sess.headers = MagicMock(); sess.headers.update = MagicMock()
        r = mock_response(200, text="<html>Iniciar sesión</html>")
        r.url = "https://catalogo-vpfe.dian.gov.co/User/Login"
        sess.get = MagicMock(return_value=r)
        MockS.return_value = sess

        try:
            cli.autenticar("https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=A&rk=1&token=x")
            assert False, "Debió lanzar TokenInvalido"
        except cli.TokenInvalido as e:
            assert "expir" in str(e).lower() or "login" in str(e).lower()
    print("✅ test_autenticar_token_expirado")


def test_autenticar_url_invalido():
    """URL fuera de dominio DIAN → TokenInvalido sin hacer request."""
    try:
        cli.autenticar("https://google.com/whatever")
        assert False, "Debió lanzar TokenInvalido"
    except cli.TokenInvalido as e:
        assert "dominio" in str(e).lower() or "esperado" in str(e).lower()
    print("✅ test_autenticar_url_invalido")


def test_listar_documentos_pagina_y_filtra():
    """listar_documentos pagina y aplica corte temprano por fecha."""
    # Catálogo simulado: docs ordenados por fecha DESC
    # Abril 2026 → marzo (lo que buscamos) → febrero
    catalogo_01 = []
    # 50 docs de abril
    abril_ms = 1775347200000  # 2026-04-15
    for i in range(50):
        catalogo_01.append(make_doc(f"t_abr_{i}", f"MLA{4000+i}", "01", "901038325", "111", 1000, abril_ms))
    # 88 docs STL de marzo
    marzo_ms = 1773792000000  # 2026-03-15
    for i in range(88):
        catalogo_01.append(make_doc(f"t_stl_{i}", f"STL{15808+i}", "01", "901038325", "111", 5000, marzo_ms))
    # 100 docs de febrero
    feb_ms = 1771113600000  # 2026-02-15
    for i in range(100):
        catalogo_01.append(make_doc(f"t_feb_{i}", f"MLA{2000+i}", "01", "901038325", "111", 1500, feb_ms))

    sesion = cli.SesionDIAN(session=MagicMock(), csrf_token=CSRF_DUMMY,
                            nit_cuenta="901038325", partition_key="A|B")

    # Configurar el mock para devolver páginas según start
    def fake_post(url, data=None, headers=None, timeout=None):
        if data is None: data = {}
        start = int(data.get("start", 0))
        length = int(data.get("length", 100))
        tipo = data.get("DocumentTypeId", "01")
        if tipo == "01":
            page = catalogo_01[start:start+length]
            return mock_response(200, json_data={"data": page, "recordsFiltered": len(catalogo_01)})
        return mock_response(200, json_data={"data": [], "recordsFiltered": 0})
    sesion.session.post = fake_post

    # Rango: marzo 2026 completo
    desde = 1772582400000  # 2026-03-01
    hasta = 1775174399000  # 2026-03-31 23:59:59

    docs = sesion.listar_documentos(tipos=["01"], desde_ms=desde, hasta_ms=hasta)
    # Debería traer los 88 STL de marzo (filtró abril y februarios)
    assert len(docs) == 88, f"esperado 88 docs, obtenido {len(docs)}"
    folios = {d["SerieAndNumber"] for d in docs}
    assert "STL15808" in folios
    assert "STL15895" in folios
    assert "MLA4000" not in folios  # abril no debe entrar
    assert "MLA2000" not in folios  # feb no debe entrar
    print(f"✅ test_listar_documentos_pagina_y_filtra ({len(docs)} docs)")


def test_descargar_zip_ok():
    """descargar_zip valida bytes 'PK' y devuelve el blob."""
    sesion = cli.SesionDIAN(session=MagicMock(), csrf_token="x", nit_cuenta="1", partition_key="A")
    zip_bytes = fake_zip_with_xml("<Invoice/>")
    sesion.session.get = MagicMock(return_value=mock_response(200, content=zip_bytes))
    blob = sesion.descargar_zip("track_abc")
    assert len(blob) > 200
    assert blob[:2] == b"PK"
    print("✅ test_descargar_zip_ok")


def test_descargar_zip_no_es_zip():
    """Si la API devuelve HTML (sesión caducó), error claro."""
    sesion = cli.SesionDIAN(session=MagicMock(), csrf_token="x", nit_cuenta="1", partition_key="A")
    # HTML largo (> 200 bytes) que no es ZIP
    html_error = b"<html><head><title>Error</title></head><body>" + b"X" * 300 + b"</body></html>"
    sesion.session.get = MagicMock(return_value=mock_response(200, content=html_error))
    try:
        sesion.descargar_zip("track_x")
        assert False, "debió fallar"
    except cli.ErrorDIAN as e:
        assert "ZIP" in str(e), f"mensaje inesperado: {e}"
    print("✅ test_descargar_zip_no_es_zip")


def test_extraer_xml_de_zip():
    """Extrae XML del ZIP DIAN correctamente."""
    xml = "<?xml version='1.0'?><Invoice><cbc:ID>STL15808</cbc:ID></Invoice>"
    zb = fake_zip_with_xml(xml)
    extraido = cli.extraer_xml_de_zip_dian(zb)
    assert extraido == xml
    print("✅ test_extraer_xml_de_zip")


def test_extraer_xml_zip_corrupto():
    """ZIP corrupto → None, no exception."""
    extraido = cli.extraer_xml_de_zip_dian(b"not a zip")
    assert extraido is None
    print("✅ test_extraer_xml_zip_corrupto")


def test_clasificar_categorias_completas():
    """Clasificador asigna correctamente cada categoría."""
    docs = [
        # Ventas
        make_doc("t1", "STL15808", "01", "901038325", "900001", 1000000, 1773792000000, sender_name="JIPER", receiver_name="Mayorista"),
        make_doc("t2", "IND12345", "01", "901038325", "222222222", 50000, 1773792000000, sender_name="JIPER", receiver_name="Consumidor"),
        make_doc("t3", "MLA98765", "01", "901038325", "222222222", 80000, 1773792000000, sender_name="JIPER", receiver_name="Consumidor"),
        # NCs emitidas
        make_doc("t4", "NC2570", "91", "901038325", "900001", -50000, 1773792000000, sender_name="JIPER", receiver_name="Mayorista"),
        make_doc("t5", "NCI100", "91", "901038325", "222222222", -10000, 1773792000000, sender_name="JIPER", receiver_name="Consumidor"),
        # Compras
        make_doc("t6", "FACTPROV", "01", "800000001", "901038325", 500000, 1773792000000, sender_name="Proveedor", receiver_name="JIPER"),
        # NC de compra
        make_doc("t7", "NCPROV100", "91", "800000001", "901038325", -50000, 1773792000000, sender_name="Proveedor", receiver_name="JIPER"),
        # DS emitido
        make_doc("t8", "DSE3052", "05", "901038325", "888888", 100000, 1773792000000, sender_name="JIPER", receiver_name="NoObligado"),
    ]
    mapeo = {
        "IND": {"cc": "001101", "nombre": "Indiana", "tipo": "venta"},
        "NCI": {"cc": "001101", "nombre": "Indiana", "tipo": "nc"},
    }
    r = clf.clasificar_documentos(docs, nit_empresa="901038325", mapeo_prefijos=mapeo)
    conteos = r.conteos()
    print(f"   Conteos: {conteos}")
    assert conteos.get(clf.CAT_VENTA_STL) == 1, "1 STL"
    assert conteos.get(clf.CAT_VENTA_POS) == 1, "1 venta POS Indiana"
    assert conteos.get(clf.CAT_VENTA_OTRA) == 1, "1 venta otra (MLA no mapeado)"
    assert conteos.get(clf.CAT_NC_STL) == 1
    assert conteos.get(clf.CAT_NC_POS) == 1
    assert conteos.get(clf.CAT_COMPRA) == 1
    assert conteos.get(clf.CAT_NC_COMPRA) == 1
    assert conteos.get(clf.CAT_DS_EMITIDO) == 1
    # Prefijos no mapeados debe contener MLA
    assert "MLA" in r.prefijos_no_mapeados
    print("✅ test_clasificar_categorias_completas")


def test_clasificar_doc_huerfano():
    """Doc donde la empresa no es ni emisor ni receptor → DESCONOCIDO + advertencia."""
    docs = [
        make_doc("t1", "X1", "01", "111", "222", 100, 1773792000000),
    ]
    r = clf.clasificar_documentos(docs, nit_empresa="901038325")
    assert r.conteos().get(clf.CAT_DESCONOCIDO) == 1
    assert len(r.advertencias) == 1
    print("✅ test_clasificar_doc_huerfano")


def test_clasificar_normaliza_nit_con_dv():
    """NITs con guión o DV deberían normalizarse a solo dígitos."""
    docs = [
        # NIT con guión
        make_doc("t1", "IND1", "01", "901038325-7", "222", 100, 1773792000000),
    ]
    r = clf.clasificar_documentos(docs, nit_empresa="901038325",
                                  mapeo_prefijos={"IND": {"cc": "001", "nombre": "Indiana", "tipo": "venta"}})
    assert r.conteos().get(clf.CAT_VENTA_POS) == 1, "Debió clasificar como venta POS aún con DV"
    print("✅ test_clasificar_normaliza_nit_con_dv")


def test_construir_mapeo_prefijos():
    """Helper que arma el mapeo desde datos_punto.json."""
    sucursales = [
        {"cc": "001101", "nombre_reporte": "Indiana", "prefijo_token": "IND", "prefijo_token_nc": "NCI"},
        {"cc": "001102", "nombre_reporte": "Oviedo", "prefijo_token": "OVI", "prefijo_token_nc": ""},
        {"cc": "001103", "nombre_reporte": "Sin Prefijo"},  # sin prefijo configurado
    ]
    mapeo = clf.construir_mapeo_prefijos(sucursales)
    assert "IND" in mapeo and mapeo["IND"]["tipo"] == "venta"
    assert "NCI" in mapeo and mapeo["NCI"]["tipo"] == "nc"
    assert "OVI" in mapeo
    # Sucursal sin prefijo no debe estar
    assert "Sin Prefijo" not in mapeo
    print("✅ test_construir_mapeo_prefijos")


def test_corte_temprano_funciona():
    """Si la primera página completa viene MÁS NUEVA que el rango, no encuentra; debe parar igual."""
    sesion = cli.SesionDIAN(session=MagicMock(), csrf_token=CSRF_DUMMY, nit_cuenta="901038325", partition_key="A")

    # Catálogo: TODO en abril, buscamos marzo
    abril_ms = 1775347200000
    catalogo = [make_doc(f"t{i}", f"MLA{i}", "01", "901038325", "111", 1000, abril_ms) for i in range(50)]

    def fake_post(url, data=None, headers=None, timeout=None):
        return mock_response(200, json_data={"data": catalogo, "recordsFiltered": 50})
    sesion.session.post = fake_post

    # Rango: marzo (anterior a los datos)
    docs = sesion.listar_documentos(tipos=["01"], desde_ms=1772582400000, hasta_ms=1775174399000)
    assert len(docs) == 0, f"esperado 0, obtenido {len(docs)}"
    print("✅ test_corte_temprano_funciona (rango sin docs)")


# ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_autenticar_ok,
        test_autenticar_token_expirado,
        test_autenticar_url_invalido,
        test_listar_documentos_pagina_y_filtra,
        test_descargar_zip_ok,
        test_descargar_zip_no_es_zip,
        test_extraer_xml_de_zip,
        test_extraer_xml_zip_corrupto,
        test_clasificar_categorias_completas,
        test_clasificar_doc_huerfano,
        test_clasificar_normaliza_nit_con_dv,
        test_construir_mapeo_prefijos,
        test_corte_temprano_funciona,
    ]
    fails = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"❌ {t.__name__}: {e}")
            fails += 1
        except Exception as e:
            import traceback
            print(f"💥 {t.__name__}: {e}")
            traceback.print_exc()
            fails += 1
    if fails == 0:
        print(f"\n🎉 {len(tests)}/{len(tests)} tests pasaron")
    else:
        print(f"\n💥 {fails}/{len(tests)} tests fallaron")
        sys.exit(1)
