"""
Tests del editor de reglas con mock de Supabase.

Valida la lógica de:
    - Lectura por formato
    - Lectura por búsqueda libre (3 capas)
    - Edición de Capa 1 con log
    - Creación/actualización de override en Capa 3
    - Eliminación de override
    - Conteo de formatos
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime
from core.exogena import editor_reglas as er


# ============================================================================
# Mock de cliente Supabase
# ============================================================================

class MockResponse:
    def __init__(self, data):
        self.data = data


class MockTable:
    def __init__(self, name, db):
        self.name = name
        self.db = db
        self._filters = []
        self._select_cols = '*'
        self._order_by = []
        self._limit = None
        self._single = False

    def select(self, cols):
        self._select_cols = cols
        return self

    def eq(self, col, val):
        self._filters.append(('eq', col, val))
        return self

    def neq(self, col, val):
        self._filters.append(('neq', col, val))
        return self

    def lte(self, col, val):
        self._filters.append(('lte', col, val))
        return self

    def gte(self, col, val):
        self._filters.append(('gte', col, val))
        return self

    def like(self, col, pattern):
        self._filters.append(('like', col, pattern))
        return self

    def ilike(self, col, pattern):
        self._filters.append(('ilike', col, pattern))
        return self

    def is_(self, col, val):
        self._filters.append(('is', col, val))
        return self

    @property
    def not_(self):
        # Devuelve un wrapper que invierte la siguiente operación
        return _NotWrapper(self)

    def or_(self, expr):
        return self  # Simplificación

    def order(self, col, desc=False):
        self._order_by.append((col, desc))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = True
        return self

    def insert(self, data):
        # Asignar ID
        items = data if isinstance(data, list) else [data]
        for item in items:
            item['id'] = self.db.next_id(self.name)
            self.db.tables[self.name].append(dict(item))
        return MockExec(MockResponse(items))

    def update(self, data):
        # Devuelve un nuevo MockTable que mantiene los filtros y aplica el update al ejecutar
        new = MockTable(self.name, self.db)
        new._filters = list(self._filters)
        new._pending_action = ('update', data)
        return new

    def delete(self):
        new = MockTable(self.name, self.db)
        new._filters = list(self._filters)
        new._pending_action = ('delete', None)
        return new

    def _filtered_rows(self):
        rows = self.db.tables.get(self.name, [])
        for op, col, val in self._filters:
            if op == 'eq':
                rows = [r for r in rows if r.get(col) == val]
            elif op == 'neq':
                rows = [r for r in rows if r.get(col) != val]
            elif op == 'lte':
                rows = [r for r in rows if r.get(col) is not None and str(r.get(col)) <= str(val)]
            elif op == 'gte':
                rows = [r for r in rows if r.get(col) is not None and str(r.get(col)) >= str(val)]
            elif op == 'like':
                pat = val.replace('%', '')
                rows = [r for r in rows if r.get(col, '') and pat in r.get(col, '')]
            elif op == 'ilike':
                pat = val.replace('%', '').lower()
                rows = [r for r in rows if r.get(col, '') and pat in (r.get(col, '') or '').lower()]
            elif op == 'is':
                if val == 'null':
                    rows = [r for r in rows if r.get(col) is None]
            elif op == 'is_not':
                if val == 'null':
                    rows = [r for r in rows if r.get(col) is not None]
        return rows

    def execute(self):
        # Ejecutar acción pendiente si hay (update/delete)
        action = getattr(self, '_pending_action', None)
        if action:
            kind, data = action
            affected = self._filtered_rows()
            if kind == 'update':
                for row in affected:
                    row.update(data)
                return MockResponse(affected)
            elif kind == 'delete':
                for row in affected:
                    self.db.tables[self.name].remove(row)
                return MockResponse(affected)

        rows = self._filtered_rows()
        for col, desc in reversed(self._order_by):
            rows = sorted(rows, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        if self._limit:
            rows = rows[: self._limit]
        if self._single:
            return MockResponse(rows[0] if rows else None)
        return MockResponse(rows)


class _NotWrapper:
    """Wrapper que invierte la siguiente operación (negación de filtro)."""
    def __init__(self, parent):
        self.parent = parent

    def is_(self, col, val):
        # not_.is_(col, 'null')  =>  filter "col IS NOT NULL"
        if val == 'null':
            self.parent._filters.append(('is_not', col, val))
        return self.parent


class MockExec:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class MockSupabase:
    def __init__(self):
        self.tables = {
            'exogena_puc_generico': [],
            'exogena_mapeo_empresa': [],
            'exogena_mapeo_manual': [],
            'exogena_cat_concepto_formato': [],
            'exogena_reglas_log': [],
        }
        self._ids = {}

    def table(self, name):
        return MockTable(name, self)

    def next_id(self, table_name):
        self._ids[table_name] = self._ids.get(table_name, 0) + 1
        return self._ids[table_name]


# ============================================================================
# Fixtures de datos
# ============================================================================

def setup_db():
    """Crea un mock de BD con datos representativos."""
    sb = MockSupabase()

    # Capa 1 — algunas reglas globales
    sb.tables['exogena_puc_generico'] = [
        {'id': 1, 'codigo_cuenta': '510303', 'nombre_cuenta': 'SALUD EPS',
         'formato_dian': '1001', 'concepto_dian': 5010,
         'descripcion_concepto': 'Pagos al sistema de salud',
         'naturaleza': 'Débito', 'activo': True, 'año_gravable': 2025,
         'modificado_en': None, 'modificado_por': None, 'nota': None},
        {'id': 2, 'codigo_cuenta': '510306', 'nombre_cuenta': 'PENSION',
         'formato_dian': '1001', 'concepto_dian': 5011,
         'descripcion_concepto': 'Pagos al sistema de pensiones',
         'naturaleza': 'Débito', 'activo': True, 'año_gravable': 2025,
         'modificado_en': None, 'modificado_por': None, 'nota': None},
        {'id': 3, 'codigo_cuenta': '530525', 'nombre_cuenta': 'GMF',
         'formato_dian': '1001', 'concepto_dian': 5101,
         'descripcion_concepto': 'GMF',
         'naturaleza': 'Débito', 'activo': True, 'año_gravable': 2025,
         'modificado_en': None, 'modificado_por': None, 'nota': None},
        {'id': 4, 'codigo_cuenta': '413515', 'nombre_cuenta': 'INGRESOS POR VENTAS',
         'formato_dian': '1007', 'concepto_dian': 4003,
         'descripcion_concepto': 'Ingresos por ventas',
         'naturaleza': 'Crédito', 'activo': True, 'año_gravable': 2025,
         'modificado_en': None, 'modificado_por': None, 'nota': None},
    ]
    sb._ids['exogena_puc_generico'] = 4

    # Capa 3 — un override existente para Quinto Sentido
    sb.tables['exogena_mapeo_manual'] = [
        {'id': 100, 'empresa_id': 'qs-uuid', 'codigo_cuenta': '513580',
         'nombre_cuenta': 'CUENTA NO-PUC',
         'formato_dian': '1001', 'concepto_dian': 5099,
         'descripcion_concepto': 'Otros gastos por concepto especial',
         'nit': None, 'excluir': False, 'motivo_exclusion': None,
         'nota': 'Override por plan de cuentas no estándar',
         'año_gravable': 2025,
         'modificado_en': None, 'modificado_por': None,
         'creado_en': '2026-05-01'},
    ]
    sb._ids['exogena_mapeo_manual'] = 100

    # Catálogo de conceptos
    sb.tables['exogena_cat_concepto_formato'] = [
        {'formato_dian': '1001', 'concepto_dian': 5010, 'descripcion': 'Pagos al sistema de salud', 'año_gravable': 2025},
        {'formato_dian': '1001', 'concepto_dian': 5011, 'descripcion': 'Pagos al sistema de pensiones', 'año_gravable': 2025},
        {'formato_dian': '1001', 'concepto_dian': 5012, 'descripcion': 'Pagos al sistema de riesgos', 'año_gravable': 2025},
        {'formato_dian': '1001', 'concepto_dian': 5101, 'descripcion': 'GMF', 'año_gravable': 2025},
        {'formato_dian': '1001', 'concepto_dian': 5099, 'descripcion': 'Otros gastos', 'año_gravable': 2025},
        {'formato_dian': '1007', 'concepto_dian': 4003, 'descripcion': 'Ingresos por ventas', 'año_gravable': 2025},
    ]

    return sb


# ============================================================================
# Tests
# ============================================================================

def test_listar_formatos():
    sb = setup_db()
    formatos = er.listar_formatos_con_reglas(sb, 2025)
    nombres = [f['formato_dian'] for f in formatos]
    assert '1001' in nombres
    assert '1007' in nombres
    # 1001 tiene 3 reglas, 1007 tiene 1
    f1001 = next(f for f in formatos if f['formato_dian'] == '1001')
    assert f1001['conteo'] == 3
    print('✅ test_listar_formatos')


def test_listar_conceptos_de_formato():
    sb = setup_db()
    conceptos = er.listar_conceptos_de_formato(sb, '1001', 2025)
    códigos = [c['concepto_dian'] for c in conceptos]
    assert 5010 in códigos
    assert 5011 in códigos
    assert 5101 in códigos
    print('✅ test_listar_conceptos_de_formato')


def test_listar_reglas_por_formato_capa1():
    sb = setup_db()
    reglas = er.listar_reglas_por_formato(sb, '1001', empresa_id=None, año_gravable=2025)
    assert len(reglas) == 3
    códigos = sorted([r.codigo_cuenta for r in reglas])
    assert códigos == ['510303', '510306', '530525']
    assert all(r.capa == 1 for r in reglas)
    print('✅ test_listar_reglas_por_formato_capa1')


def test_listar_reglas_por_formato_con_override():
    sb = setup_db()
    reglas = er.listar_reglas_por_formato(
        sb, '1001', empresa_id='qs-uuid', año_gravable=2025
    )
    # 3 globales + 1 override de Quinto Sentido
    assert len(reglas) == 4
    overrides = [r for r in reglas if r.capa == 3]
    assert len(overrides) == 1
    assert overrides[0].codigo_cuenta == '513580'
    print('✅ test_listar_reglas_por_formato_con_override')


def test_buscar_cuenta_por_codigo():
    sb = setup_db()
    res = er.buscar_cuenta(sb, '510303', empresa_id='qs-uuid')
    códigos = [r.codigo_cuenta for r in res if r.capa != 2]
    assert '510303' in códigos
    print('✅ test_buscar_cuenta_por_codigo')


def test_buscar_cuenta_por_nombre():
    sb = setup_db()
    res = er.buscar_cuenta(sb, 'salud', empresa_id='qs-uuid')
    assert any('SALUD' in r.nombre_cuenta.upper() for r in res)
    print('✅ test_buscar_cuenta_por_nombre')


def test_editar_regla_global():
    sb = setup_db()
    res = er.editar_regla_global(
        sb=sb,
        id_capa1=3,
        formato_nuevo='1001',
        concepto_nuevo=5101,
        descripcion_nueva='GMF',
        usuario='test@user.com',
        motivo='Test edición global',
    )
    assert res.ok, res.mensaje
    # Verificar que el log se creó
    log = sb.tables['exogena_reglas_log']
    assert len(log) == 1
    assert log[0]['accion'] == 'editar'
    assert log[0]['capa'] == 1
    assert log[0]['codigo_cuenta'] == '530525'
    print('✅ test_editar_regla_global')


def test_crear_override_nuevo():
    sb = setup_db()
    res = er.crear_o_actualizar_override(
        sb=sb,
        empresa_id='qs-uuid',
        codigo_cuenta='91234567',
        nombre_cuenta='CUENTA RARA',
        formato_dian='1007',
        concepto_dian=4003,
        descripcion_concepto='Ingresos especiales',
        usuario='test@user.com',
        motivo='Plan de cuentas no estándar',
    )
    assert res.ok, res.mensaje
    # Verificar que se insertó
    overrides = sb.tables['exogena_mapeo_manual']
    nuevos = [o for o in overrides if o['codigo_cuenta'] == '91234567']
    assert len(nuevos) == 1
    # Verificar log
    log_create = [l for l in sb.tables['exogena_reglas_log'] if l['accion'] == 'crear']
    assert len(log_create) == 1
    print('✅ test_crear_override_nuevo')


def test_actualizar_override_existente():
    sb = setup_db()
    # Override ya existe para 513580
    res = er.crear_o_actualizar_override(
        sb=sb,
        empresa_id='qs-uuid',
        codigo_cuenta='513580',
        nombre_cuenta='CUENTA NO-PUC',
        formato_dian='1001',
        concepto_dian=5101,  # Cambia de 5099 → 5101
        descripcion_concepto='GMF',
        usuario='test@user.com',
        motivo='Reclasificación a GMF',
    )
    assert res.ok, res.mensaje
    # Verificar que NO se duplicó
    overrides = [o for o in sb.tables['exogena_mapeo_manual'] if o['codigo_cuenta'] == '513580']
    assert len(overrides) == 1
    assert overrides[0]['concepto_dian'] == 5101
    # Log debe ser 'editar', no 'crear'
    log = sb.tables['exogena_reglas_log']
    assert log[-1]['accion'] == 'editar'
    print('✅ test_actualizar_override_existente')


def test_eliminar_override():
    sb = setup_db()
    res = er.eliminar_override(sb, 100, 'test@user.com', 'Ya no aplica')
    assert res.ok, res.mensaje
    # Verificar eliminación
    assert len(sb.tables['exogena_mapeo_manual']) == 0
    # Log
    log = [l for l in sb.tables['exogena_reglas_log'] if l['accion'] == 'eliminar']
    assert len(log) == 1
    print('✅ test_eliminar_override')


def test_no_duplicar_regla_global():
    sb = setup_db()
    res = er.crear_regla_global(
        sb=sb,
        codigo_cuenta='510303',  # Ya existe
        nombre_cuenta='X',
        formato_dian='1001',
        concepto_dian=5010,
        descripcion_concepto='X',
        naturaleza='Débito',
        usuario='test@user.com',
    )
    assert not res.ok
    assert 'Ya existe' in res.mensaje
    print('✅ test_no_duplicar_regla_global')


def test_excluir_con_formato_es_invalido():
    sb = setup_db()
    res = er.crear_o_actualizar_override(
        sb=sb,
        empresa_id='qs-uuid',
        codigo_cuenta='99999',
        nombre_cuenta='X',
        formato_dian='1001',  # No puede tener formato si excluir=True
        concepto_dian=5010,
        descripcion_concepto='X',
        usuario='test@user.com',
        excluir=True,
    )
    assert not res.ok
    print('✅ test_excluir_con_formato_es_invalido')


def test_log_reciente():
    sb = setup_db()
    er.editar_regla_global(sb, 1, '1001', 5010, 'Salud', 'u@x.com', 'test')
    er.editar_regla_global(sb, 2, '1001', 5011, 'Pensión', 'u@x.com', 'test 2')
    log = er.listar_log_reciente(sb, limit=10)
    assert len(log) == 2
    print('✅ test_log_reciente')


# ============================================================================
# Runner
# ============================================================================

if __name__ == '__main__':
    import traceback
    tests = [
        test_listar_formatos,
        test_listar_conceptos_de_formato,
        test_listar_reglas_por_formato_capa1,
        test_listar_reglas_por_formato_con_override,
        test_buscar_cuenta_por_codigo,
        test_buscar_cuenta_por_nombre,
        test_editar_regla_global,
        test_crear_override_nuevo,
        test_actualizar_override_existente,
        test_eliminar_override,
        test_no_duplicar_regla_global,
        test_excluir_con_formato_es_invalido,
        test_log_reciente,
    ]
    pasados = 0
    fallidos = []
    for t in tests:
        try:
            t()
            pasados += 1
        except Exception as e:
            fallidos.append((t.__name__, str(e)))
            print(f'❌ {t.__name__}: {e}')
            traceback.print_exc()
    print(f'\n{"=" * 50}')
    print(f'✅ {pasados}/{len(tests)} tests pasaron')
    if fallidos:
        print(f'❌ {len(fallidos)} fallidos:')
        for name, err in fallidos:
            print(f'   - {name}: {err}')
        sys.exit(1)
