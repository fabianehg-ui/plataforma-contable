"""
APRENDIZ DE MAPEO desde Balance de Prueba

Lee un BP por NIT con CC (formato Siigo / Helisa estándar) y genera:
  - mapeo_nits.json   con cuenta dominante + CC dominante por NIT
  - centros_costo.json con la lista de CCs y sus nombres
  - direcciones_locales.json (esqueleto vacío para que el usuario llene)

USO:
    python aprendiz_bp.py <archivo_bp.xlsx> --salida <carpeta>

El BP debe tener las columnas:
  Cuenta | Equivalencia | Nombre | NIT | Nombre NIT | CC | Nombre CC |
  Saldo Anterior | Débitos | Créditos | Nuevo Saldo
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


# Cuentas que CONSIDERAMOS imputables (donde se carga el costo/gasto/inventario/activo)
# Excluye cuentas de proveedores (22xx), retenciones (23xx), bancos (1110), caja (1105), etc.
def es_cuenta_imputable(cuenta: str) -> bool:
    c = str(cuenta).strip()
    if not c or c == 'nan':
        return False
    # Inventarios mercancía
    if c.startswith('1435') or c.startswith('1455') or c.startswith('1465'):
        return True
    # Anticipos a proveedores
    if c.startswith('133005'):
        return True
    # Activos fijos (cuando se compra equipo)
    if c.startswith('152') or c.startswith('154') or c.startswith('15'):
        return True
    # Costos
    if c.startswith('6') or c.startswith('7'):
        return True
    # Gastos
    if c.startswith('5'):
        return True
    return False


def normalizar_nit(nit_raw) -> str:
    """Normaliza NIT a solo dígitos sin DV."""
    if not nit_raw or pd.isna(nit_raw):
        return ''
    s = str(nit_raw).strip()
    # Quitar puntos
    s = s.replace('.', '').replace(' ', '')
    # Si tiene guión, quitar dígito verificación
    if '-' in s:
        s = s.split('-')[0]
    # Solo dígitos
    s = re.sub(r'\D', '', s)
    return s


def _limpiar_codigo_cuenta(v) -> str:
    """Limpia un código de cuenta que viene como float (143505.0) o str."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    s = str(v).strip()
    # Si termina en .0 (número entero leído como float), quitar
    if s.endswith('.0'):
        s = s[:-2]
    # Si por alguna razón hay punto decimal en medio (no debería), quitar
    if '.' in s:
        try:
            f = float(s)
            if f == int(f):
                s = str(int(f))
        except (ValueError, TypeError):
            pass
    return s


def cargar_bp(path: Path) -> pd.DataFrame:
    """Lee el BP. Detecta automáticamente la fila de encabezado."""
    df = pd.read_excel(path, header=None)
    # Buscar la fila con 'Cuenta' en columna 0
    fila_header = None
    for i in range(min(10, len(df))):
        v = str(df.iloc[i, 0]).strip().lower()
        if v == 'cuenta':
            fila_header = i
            break
    if fila_header is None:
        raise ValueError("No se encontró fila de encabezado 'Cuenta' en las primeras 10 filas")

    # Releer con header
    df = pd.read_excel(path, header=fila_header)
    # Renombrar columnas a estándar
    cols_map = {
        'Cuenta': 'cuenta',
        'Equivalencia': 'equivalencia',
        'Nombre': 'nombre_cuenta',
        'NIT': 'nit',
        'Nombre NIT': 'nombre_nit',
        'Centro de Costos': 'cc',
        'Nombre CC': 'nombre_cc',
        'Saldo Anterior': 'saldo_ant',
        'Débitos': 'debitos',
        'Créditos': 'creditos',
        'Nuevo Saldo': 'nuevo_saldo',
    }
    df = df.rename(columns=cols_map)
    # Numéricos
    for c in ['saldo_ant', 'debitos', 'creditos', 'nuevo_saldo']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    return df


def construir_mapeo_nits(df: pd.DataFrame) -> dict:
    """A partir del BP genera mapeo_nits.json compatible con módulo DIAN XML."""
    # Solo filas con NIT real
    det = df[df['nit'].notna() & (df['nit'].astype(str).str.strip() != '')].copy()
    det['nit_norm'] = det['nit'].apply(normalizar_nit)
    det = det[det['nit_norm'] != '']
    det['cuenta_str'] = det['cuenta'].apply(_limpiar_codigo_cuenta)
    det['cc_str'] = det['cc'].astype(str).str.strip() if 'cc' in det.columns else ''
    det['nombre_cc_str'] = det['nombre_cc'].astype(str).str.strip() if 'nombre_cc' in det.columns else ''

    # Solo lineas imputables con débitos (=donde se cargó la compra)
    imput = det[det['cuenta_str'].apply(es_cuenta_imputable) & (det['debitos'] > 0)].copy()

    nits = {}
    for nit_n, g in imput.groupby('nit_norm'):
        nombre = str(g['nombre_nit'].iloc[0]).strip()

        # Cuenta dominante (por monto de débitos)
        cuentas_peso = g.groupby('cuenta_str')['debitos'].sum().sort_values(ascending=False)
        if len(cuentas_peso) == 0:
            continue
        cuenta_dominante = cuentas_peso.index[0]
        confianza_cuenta = cuentas_peso.iloc[0] / cuentas_peso.sum()

        # CC dominante (por monto)
        ccs_peso = g[g['cc_str'] != ''].groupby('cc_str')['debitos'].sum().sort_values(ascending=False)
        if len(ccs_peso) > 0:
            cc_dominante = ccs_peso.index[0]
            confianza_cc = ccs_peso.iloc[0] / ccs_peso.sum()
        else:
            cc_dominante = ''
            confianza_cc = 0.0

        # Lista de CCs alternos (por si la dirección XML no coincide con el dominante)
        ccs_alternos = list(ccs_peso.head(8).index)

        # Cuentas alternas (en caso que haya varias por tarifa de IVA)
        cuentas_alternas = list(cuentas_peso.head(5).index)

        nits[nit_n] = {
            'nombre': nombre,
            'cuenta_default': cuenta_dominante,
            'cc_default': cc_dominante,
            'confianza_cuenta': round(confianza_cuenta, 3),
            'confianza_cc': round(confianza_cc, 3),
            'cuentas_vistas': cuentas_alternas,
            'ccs_vistos': ccs_alternos,
            'fuente': 'BP_aprendido',
            # Campos para el usuario llenar (RST, autorretenedor, etc.)
            'regimen': 'ordinario',  # opciones: ordinario, simple_RST, gran_contribuyente
            'autorretenedor_renta': False,
            'concepto_retencion': '',  # se autodetecta abajo según cuenta
        }

    # Inferir concepto de retención según cuenta dominante
    for nit_n, info in nits.items():
        info['concepto_retencion'] = inferir_concepto_retencion(
            info['cuenta_default']
        )

    return nits


def inferir_concepto_retencion(cuenta: str) -> str:
    """Mapea cuenta dominante a concepto de retención sugerido."""
    c = str(cuenta).strip()
    # Inventarios → compras
    if c.startswith('1435') or c.startswith('1455'):
        return 'compras_2_5'  # 2.5%
    # Activos fijos → compras
    if c.startswith('152') or c.startswith('154'):
        return 'compras_2_5'
    # Honorarios típicos
    if c.startswith('5110') or c.startswith('51103') or c.startswith('5113'):
        return 'honorarios_11'
    # Arrendamientos inmuebles
    if c.startswith('5120') or c.startswith('5220'):
        return 'arrendamiento_inmueble_3_5'
    # Servicios públicos (NO se retienen) — ENERGIA, ACUEDUCTO, GAS
    if c.startswith('52353') or c.startswith('52352'):
        return 'sin_retencion_servicio_publico'
    # Fletes / transporte
    if c.startswith('52355'):
        return 'transporte_carga_1'
    # Aseo, vigilancia, mantenimiento
    if c.startswith('52350') or c.startswith('52450') or c.startswith('5235'):
        return 'servicios_4'
    # Software / licenciamiento
    if c.startswith('52352') or c.startswith('51552'):
        return 'software_3_5'
    # Comisiones
    if c.startswith('5305'):
        return 'comisiones_11'
    # Gastos generales clase 5 (default conservador)
    if c.startswith('5'):
        return 'servicios_4'
    return 'sin_retencion'


def construir_centros_costo(df: pd.DataFrame) -> dict:
    """Extrae todos los CCs únicos con sus nombres."""
    ccs_df = df[df['cc'].notna()].copy() if 'cc' in df.columns else pd.DataFrame()
    if len(ccs_df) == 0:
        return {}
    ccs_df['cc_str'] = ccs_df['cc'].astype(str).str.strip()
    ccs_df['nombre_cc_str'] = ccs_df['nombre_cc'].astype(str).str.strip() if 'nombre_cc' in ccs_df.columns else ''
    ccs_df = ccs_df[(ccs_df['cc_str'] != '') & (ccs_df['cc_str'] != 'Centro de Costos')]
    ccs_unique = ccs_df.drop_duplicates('cc_str').set_index('cc_str')['nombre_cc_str'].to_dict()
    return {cc: nombre for cc, nombre in sorted(ccs_unique.items())}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('archivo_bp', help='Ruta al .xlsx del Balance de Prueba')
    p.add_argument('--salida', default='./aprendido', help='Carpeta de salida')
    args = p.parse_args()

    bp_path = Path(args.archivo_bp)
    out_dir = Path(args.salida)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"📂 Leyendo BP: {bp_path}")
    df = cargar_bp(bp_path)
    print(f"   Filas: {len(df)}")

    print("🔍 Construyendo mapeo de NITs...")
    mapeo = construir_mapeo_nits(df)
    print(f"   NITs mapeados: {len(mapeo)}")

    print("🔍 Extrayendo centros de costo...")
    ccs = construir_centros_costo(df)
    print(f"   CCs únicos: {len(ccs)}")

    # Guardar
    salida_mapeo = out_dir / 'mapeo_nits.json'
    with open(salida_mapeo, 'w', encoding='utf-8') as f:
        json.dump(mapeo, f, indent=2, ensure_ascii=False)
    print(f"💾 {salida_mapeo}")

    salida_ccs = out_dir / 'centros_costo.json'
    with open(salida_ccs, 'w', encoding='utf-8') as f:
        json.dump(ccs, f, indent=2, ensure_ascii=False)
    print(f"💾 {salida_ccs}")

    # Esqueleto de direcciones → CC (el usuario lo llena)
    direcciones_template = {
        '_descripcion': 'Mapeo de direcciones físicas (de Delivery del XML) a CCs',
        '_instrucciones': 'Edita la sección "direcciones" para que cada dirección apunte al CC correcto',
        '_normalizacion': 'Las direcciones se normalizan: CRA/KRA→CR, CALLE/CLL→CL, DG, AV. Sin puntos ni #',
        'direcciones': {
            # Ejemplo:
            # 'CR 98 18 49': '10-04',
        }
    }
    salida_dir = out_dir / 'direcciones_locales.json'
    if not salida_dir.exists():
        with open(salida_dir, 'w', encoding='utf-8') as f:
            json.dump(direcciones_template, f, indent=2, ensure_ascii=False)
        print(f"💾 {salida_dir} (vacío - el usuario debe llenar)")

    # Resumen
    print("\n" + "="*60)
    print("RESUMEN APRENDIZAJE")
    print("="*60)
    cnt_alta_conf = sum(1 for v in mapeo.values() if v['confianza_cuenta'] >= 0.7)
    cnt_baja_conf = len(mapeo) - cnt_alta_conf
    print(f"NITs con cuenta dominante clara (≥70%):  {cnt_alta_conf}")
    print(f"NITs con cuenta dispersa (necesitan revisión): {cnt_baja_conf}")
    print(f"CCs encontrados: {len(ccs)}")
    print(f"\n👉 Próximo paso: editar {salida_dir.name}")
    print(f"    para mapear cada dirección XML al CC correcto.")


if __name__ == '__main__':
    main()
