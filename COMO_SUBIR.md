# INTEGRAL — Libros y reportes contables

## Archivos
    Home.py                              (REEMPLAZA — nueva página en menú Reportes)
    app_pages/20_Contabilidad.py         (NUEVO)
    core/contable/servicio_contable.py   (REEMPLAZA — +reportes e importación)

(Requiere la migración 014 ya aplicada.)

## Qué agrega
Nueva página "📚 Contabilidad (Libros)" en el menú Reportes, que lee de
cn_movimientos y trae 5 pestañas:

1) ⚖️ Balance de prueba — por rango de períodos: saldo anterior, débitos,
   créditos, saldo final por cuenta, con cuadre Db=Cr y export a Excel.
2) 📒 Libro auxiliar — movimiento detallado de una cuenta y/o NIT, con
   saldo anterior y saldo corriente. Export a Excel.
3) 💳 Estado de cartera — saldo por tercero de las cuentas de cartera
   (por defecto las que empiezan por 13). Export a Excel.
4) 📥 Importar movimiento — sube un plano (.txt o .xlsx) con el formato de
   11 columnas; el período se toma de la FECHA de cada línea. Sirve para
   cargar HISTÓRICOS. Crea períodos y respeta los protegidos.
5) 🗓️ Períodos — lista, muestra el cuadre del período y permite
   abrir/proteger (estilo CNPERIOD).

## Nota
- Reportes leen con paginación (maneja miles de movimientos).
- El "aging" (edades de mora) de cartera se puede añadir cuando el import
  traiga fechas de vencimiento por documento.
