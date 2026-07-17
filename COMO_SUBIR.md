# Cómo subir estos archivos a tu repo (plataforma-contable)

Respeta EXACTAMENTE estas rutas dentro del repo:

    Home.py                                  (REEMPLAZA el que ya tienes)
    app_pages/3b_Vacaciones_Liquidaciones.py (NUEVO)
    core/lectores/lector_vacaciones.py       (NUEVO)

## Pasos
1. Sube `core/lectores/lector_vacaciones.py` a la carpeta `core/lectores/`.
2. Sube `app_pages/3b_Vacaciones_Liquidaciones.py` a la carpeta `app_pages/`.
3. Reemplaza `Home.py` en la raíz por el de esta entrega (ya trae el
   `st.Page` declarado y agregado al `st.navigation`, grupo "Asistente Contable").
4. Railway redespliega solo. El link aparece en el menú como
   "Vacaciones y Liquidaciones" (🏖️), justo debajo de Nómina.

## Recordatorio
- `requirements.txt` ya tiene `pdfplumber` (se usa para leer el PDF).
- Regla aplicada: a las VACACIONES (no definitivas) se les deduce 4% pensión
  + 4% salud sobre el TOTAL VACACIONES. En LIQUIDACIÓN DEFINITIVA las
  vacaciones NO llevan esa deducción.
