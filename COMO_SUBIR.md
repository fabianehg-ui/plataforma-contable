# CÓMO SUBIR — "Agregar al movimiento del mes" en Bittal, Bancos y POS

Ahora cada módulo, junto a **Descargar plano**, ofrece **agregar al movimiento
del mes** (causar en cn_movimientos). Fecha: 18-jul-2026. **Sin migración.**

## Qué cambia

- **Bittal → Contai**: tras *Generar plano*, aparece **💾 Contabilizar en INTEGRAL**
  (para los informes que producen plano de texto). Elige período → causa con
  `origen = bittal`.
- **Bancos a Contai**: tras *Generar plano*, la opción de contabilizar con
  `origen = bancos`.
- **Ingresos POS**: en ambos modos (Token y Excel), la opción con `origen = pos`.
- Adaptador universal `plano_texto_a_df()`: convierte cualquier plano de texto
  Contai (TSV sin encabezado, bytes o str) a DataFrame de 11 columnas, para
  causar planos que los módulos generan como texto.
- `render_contabilizar_activa(df, origen)`: una línea; toma la **empresa activa**
  del menú. Si no hay empresa seleccionada, avisa y no hace nada (Bittal y Bancos
  son páginas-herramienta sin login propio).

## Archivos

| Archivo | Estado | Cambio |
|---|---|---|
| `core/contable/integracion.py` | **MOD** | + `plano_texto_a_df()`. |
| `core/contable/ui_contabilizar.py` | **MOD** | + `render_contabilizar_activa()` (usa empresa activa). |
| `app_pages/4c_Bittal_a_Contai.py` | **MOD** | Opción contabilizar (planos de texto). |
| `app_pages/19_Bancos_a_Contai.py` | **MOD** | Opción contabilizar. |
| `app_pages/4b_Ingresos_POS.py` | **MOD** | Opción contabilizar (2 modos). |
| `tests/test_integracion.py` | **MOD** | + pruebas del adaptador de texto. **94 pruebas pasan.** |

> Requiere los archivos base del **Puente contable** (integracion.py,
> ui_contabilizar.py, Centro Contable) de la entrega anterior.

## Resultado

Todos los módulos quedan con el mismo par: **Descargar plano** (para Contai) o
**Agregar al movimiento del mes** (a INTEGRAL), y lo causado se ve/reversa en
🔗 Centro Contable. Los módulos nuevos siguen el mismo patrón de una línea.
