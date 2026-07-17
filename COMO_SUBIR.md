# INTEGRAL — Captura: crear comprobantes dentro del flujo

## Archivo
    app_pages/21_Captura.py   (REEMPLAZA)

## Qué cambió
La creación de tipos de comprobante ya NO está escondida en la barra lateral:
ahora está en el cuerpo de la página, en la sección "🧾 Tipos de comprobante",
como un panel que se abre automáticamente cuando no tienes ninguno.

Desde ahí puedes:
- Ver los comprobantes existentes (código y nombre).
- Crear/actualizar uno escribiendo Código + Nombre.
- Botón "⚡ Crear los 4 sugeridos" (recibo de caja, egreso, causación, nota).

Con al menos un comprobante creado, sigues con la cabecera y las líneas del
asiento normalmente. Si tu rol no tiene permiso (solo admin/superadmin puede
crear comprobantes por RLS), sale un aviso claro en vez de fallar en silencio.
