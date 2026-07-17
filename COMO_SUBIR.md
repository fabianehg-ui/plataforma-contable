# F350 — quitar conexión DIAN + JSON PLANO para la extensión

## 1) BORRAR en tu repo (los que se conectaban a la DIAN)
    app_pages/10a_DIAN_F350_Muisca.py    <- ELIMINAR
    app_pages/11_DIAN_F350_Muisca.py     <- ELIMINAR

## 2) REEMPLAZAR / SUBIR estos 3 archivos
    Home.py                              (REEMPLAZA — sin "DIAN F350 (Muisca)" en el menú)
    app_pages/10_Retencion_Fuente.py     (REEMPLAZA — botón "JSON extensión")
    core/f350/muisca_adapter.py          (REEMPLAZA — json_casillas_planas)

## Formato del JSON (el que pide TU extensión)
Mapa plano {renglon: valor}, ej:
    {"29": 5533840, "42": 608723, "31": 7163000, "44": 190000}
Se pega en el cuadro "CASILLAS (JSON DE TU PLATAFORMA)" y luego
"Copiar datos a los renglones". Los totales (130/136/138) NO se
incluyen: los calcula la DIAN en el portal.

Nota: quedó también generar_doc_extension() (documento completo cs_id_...),
pero NO es lo que usa esta extensión; se conserva por si acaso.
