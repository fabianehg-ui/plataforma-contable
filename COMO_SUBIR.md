# INTEGRAL — Maestros: subir NITs y cuentas desde plano

## PASO 1 — Correr en Supabase (SQL Editor)
    db/migrations/015_terceros.sql     (crea la tabla cn_terceros)

## PASO 2 — Subir al repo
    Home.py                              (REEMPLAZA — nueva página "Maestros" en Sistema)
    app_pages/22_Maestros.py             (NUEVO)
    core/contable/servicio_contable.py   (REEMPLAZA — +terceros e importadores)

## Qué agrega
Nueva página "🗂️ Maestros" (menú Sistema) con 3 pestañas, cada una lista lo
existente y permite CARGA MASIVA desde plano (.txt / .csv / .xlsx):

1) 👥 Terceros (NITs)
   Columnas: NIT, NOMBRE + opcionales TIPO (N/J), DV, RÉGIMEN, EMAIL,
   TELÉFONO, DIRECCIÓN, MUNICIPIO. Sin encabezados asume: NIT, NOMBRE, TIPO.

2) 📚 Plan de cuentas (PUC)
   Columnas: CÓDIGO, NOMBRE + opcionales NATURALEZA (D/C), TIPO,
   MANEJA NIT/CC/BASE (S/N). Sin encabezados asume: CÓDIGO, NOMBRE, NATURALEZA.

3) 🏷️ Centros de costo
   Columnas: CÓDIGO, NOMBRE.

Detalles:
- Reconoce las columnas por su ENCABEZADO (en cualquier orden) o por POSICIÓN
  si el plano no trae encabezados.
- Acepta separador tab, ; o , en los .txt/.csv, y .xlsx.
- Es UPSERT por (empresa, NIT/código): si ya existe, actualiza.
- Requiere rol admin (por RLS); si no, avisa.

## Tip
Puedes exportar desde Contai el PUC (CNCTCIAL) y tus terceros a un plano y
subirlos aquí para arrancar con tus maestros reales.
