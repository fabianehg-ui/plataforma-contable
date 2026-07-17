# Extractos bancarios → resumen y plano Contai

Lee los PDF de **Bancolombia, Banco de Bogotá y BBVA** directo (pdfplumber),
clasifica los gastos bancarios y arma el plano repartido entre los centros de costo.

## Archivos
- `core/procesadores/extractos_bancarios.py` — lectura, detección de banco, clasificación y plano.
- `app_pages/19_Bancos_a_Contai.py` — la página.

## Instalar
1. Copia los dos archivos al repo.
2. `requirements.txt`: añade **pdfplumber**.
3. Registra la página en `Home.py`:
   ```python
   bancos_contai = st.Page("app_pages/19_Bancos_a_Contai.py", title="Bancos a Contai",
                           icon="🏦", url_path="bancos-contai")
   ```
   y agrégala al grupo que prefieras del `st.navigation`.

## Uso
1. Sube los 3 extractos en PDF.
2. Revisa el resumen y **compáralo con los totales que declara cada extracto**.
3. Ajusta comprobante, documento, fecha y centros de costo.
4. "Generar plano" → descarga el .txt delimitado por tabulaciones.

## Cómo detecta cada banco
Por un texto **del cuerpo** único de cada uno, y **por puntaje** (gana el que más veces aparece):
- Bancolombia: `IMPTO GOBIERNO 4X1000`
- Banco de Bogotá: `Cobro 4x1.000 GMF`
- BBVA: `CARGO POR IMPUESTO 4X1.000`

Ojo: un extracto de Bancolombia menciona "BBVA" en pagos interbancarios; por eso
no basta con la primera coincidencia ni sirve buscar el nombre del banco.

## Reglas de clasificación (el orden manda)
| patrón | cuenta |
|---|---|
| `4X1.000`, `4 POR MIL`, `IMPTO GOBIERNO` | 53059501 Gravamen 4x1000 |
| `IVA` | 53050502 IVA gastos bancarios |
| `COMISION` | 53051501 Comisiones |
| `SERVICIO PAGO`, `CUOTA MANEJO`, `SERV TRANS EFECTIVO`, `SERVICIO ADMON` | 53050501 Gastos bancarios |

Lo que no coincide (nómina, proveedores, leasing, cuotas de crédito) **no entra al plano**.

## Validado
Mayo 2026 (JIPER), los 3 bancos y sus 12 cuentas exactas contra el total que declara
cada extracto. Plano: 363 líneas, Db = Cr = **13.354.848**.

| | Bancolombia | Bogotá | BBVA |
|---|---|---|---|
| 53050501 | 1.708.741 | 121.864 | 18.460 |
| 53050502 | 397.180 | 15.960 | 17.533 |
| 53051501 | 801.177 | 84.000 | 92.210 |
| 53059501 | 9.945.723 | 53.108 | 98.892 |

## Detalle técnico (por si hay que tocar los patrones)
- El texto se normaliza colapsando espacios pero **conservando los saltos de línea**:
  el patrón usa `.` que no cruza el salto, así cada movimiento queda dentro de su
  renglón. Si se unieran las líneas, los encabezados de página se mezclarían con
  los movimientos y producirían importes falsos.
- El patrón busca **movimientos**, no líneas: en Bogotá la extracción del PDF puede
  fusionar varios movimientos en un renglón.
- Cada gasto lleva el **NIT de su banco** y el crédito va a la cuenta PUC del banco
  (Bancolombia 11100501 · Bogotá 11100502 · BBVA 11100503).
