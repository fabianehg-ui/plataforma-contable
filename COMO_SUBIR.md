# Cómo subir estos archivos (plataforma-contable)

Todo se maneja DENTRO del módulo de Nómina. NO se crea página nueva.

Respeta EXACTAMENTE estas rutas:

    app_pages/3_Nomina.py                (REEMPLAZA el que ya tienes)
    core/lectores/lector_vacaciones.py   (NUEVO)

## Qué cambió
- En la pestaña "Procesar nómina" ahora, además de la nómina y la PILA,
  hay un tercer cargador OPCIONAL: **Vacaciones y liquidaciones definitivas**
  (acepta varios PDF a la vez), para cuando aparezcan en el movimiento del mes.
- Por cada PDF de VACACIONES:
    * Extrae los datos y muestra el desglose.
    * Aplica 4% pensión + 4% salud sobre el TOTAL VACACIONES y verifica
      contra la deducción del documento.
    * Genera el PLANO CONTABLE (Comp 11) del pago de vacaciones, cuadrado:
        Db 25301501  Pago de vacaciones            (total)
        Cr 25503002  Aporte pensión trabajador 4%
        Cr 25500502  Deducción salud trabajador 4%
        Cr 25050501  Neto a pagar (salarios x pagar)
      Descargable en .txt (plano Contai) y .xlsx. Sin centro de costo.
- Por cada PDF de LIQUIDACIÓN DEFINITIVA: muestra los conceptos detectados;
  las vacaciones dentro de la liquidación NO llevan la deducción de 4%+4%.

## Recordatorio
- requirements.txt ya trae pdfplumber (necesario para leer el PDF).
- Home.py NO se toca (no hay página nueva).
- Ejemplo validado (María Yorladis, mayo 2026):
  TOTAL 1.870.741 → pensión 74.830 + salud 74.829 = 149.659 → neto 1.721.082.
