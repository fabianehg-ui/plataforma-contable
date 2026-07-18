# Legibilidad + PDF del comprobante (colores suaves)

## Qué cambió
1. **Legibilidad** (`core/tema.py`): en el área de trabajo, sobre fondos
   blancos/claros el texto va **oscuro** (#1f2b38), inputs y selects en azul
   oscuro, y los captions en gris oscuro legible. La barra lateral mantiene su
   texto claro sobre el degradado oscuro.
2. **PDF del comprobante** (`core/contable/pdf_comprobante.py`):
   - Colores **suaves**: encabezado de tabla azul claro, fila de totales gris
     azulado, **texto negro** en todo (antes: azul fuerte con texto blanco).
   - **Datos de la empresa**: nombre, NIT y —si existen en la tabla `empresas`—
     dirección, ciudad, teléfono y correo.
   - **Cliente / Proveedor**: bloque con el nombre del tercero + NIT.
3. **Captura** (`app_pages/21_Captura.py`): al imprimir, ahora envía al PDF el
   nombre del tercero (por NIT) y los datos de contacto de la empresa.

## Instalar
Reemplaza los 3 archivos en el repo (misma ruta) y redepliega. Requiere
`reportlab` (ya estaba en uso para el PDF).

## Nota
Los datos de contacto de la empresa se toman de las columnas `direccion`,
`ciudad`/`municipio`, `telefono`/`celular`, `email`/`correo` de la tabla
`empresas` **si existen**; si no están, el PDF simplemente no las muestra (no da
error). Si quieres, luego agregamos esos campos en Configuración de la empresa.
