# Hallazgos VBA de Contai + utilidad de Dígito de Verificación

- `core/contable/dv.py` (NUEVO): `digito_verificacion(nit)` — algoritmo oficial DIAN
  portado del add-in de Contai, verificado 16/16 contra NITs reales.
- `core/contable/servicio_contable.py` (MOD): `upsert_tercero` calcula el DV solo si no viene.
- `tests/test_dv.py` (NUEVO): pruebas del DV.
- `HALLAZGOS_CONTAI_VBA.md`: qué más sacamos del VBA (consultas de saldos, presupuestos, Btrieve).
- `referencia_contai/*.bas/.cls`: código VBA extraído (solo referencia; no se sube al repo).

Sin migración. Sube dv.py y servicio_contable.py; el resto es documentación/referencia.
