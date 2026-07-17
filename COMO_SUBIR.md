# INTEGRAL — Captura de comprobantes (partida doble)

## Archivos
    Home.py                              (REEMPLAZA — nueva página en Asistente Contable)
    app_pages/21_Captura.py              (NUEVO)
    core/contable/servicio_contable.py   (por si no lo tenías al día)

(Requiere migración 014 aplicada.)

## Qué agrega
Nueva página "✍️ Captura de Comprobantes". Permite armar un documento de
partida doble y guardarlo en cn_movimientos:

- Tipos de comprobante: se gestionan en la barra lateral (botón "Crear los 4
  sugeridos": recibo de caja, egreso, causación, nota).
- Cabecera: comprobante, fecha, documento (consecutivo), NIT, detalle.
- Líneas: editor tipo Excel; escribes cuenta y el valor en Débito o Crédito.
- Valida en vivo: total Db, total Cr, diferencia; avisa si no cuadra o si una
  línea tiene débito y crédito a la vez.
- Guardar: solo si cuadra (Db=Cr) y el período NO está protegido. Queda con
  origen='captura' y se ve en 📚 Contabilidad (auxiliar, balance, cartera).

## Ejemplos del ciclo
- Egreso        → Db gasto/pasivo, Cr banco.
- Causación     → Db gasto + Db IVA, Cr proveedor + Cr retenciones.
- Recibo de caja→ Db caja/banco, Cr cartera/ingreso.
