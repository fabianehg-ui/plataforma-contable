# Hallazgos "extra" de Contai — el add-in de Excel (VBA)

Segunda pasada sobre la carpeta Contai. Los add-ins `Contai.xla` / `Contai.xlam`
tienen **código VBA** con lógica de negocio muy aprovechable. Fecha: 18-jul-2026.

## 1. Dígito de verificación (DV) del NIT — ya portado ✅

`csUtilidades.FnDigitoVer` es el algoritmo oficial DIAN (pesos
3,7,13,17,19,23,29,37,41,43,47,53,59,67,71 · módulo 11). Lo **porté a Python**
(`core/contable/dv.py`) y lo **verifiqué contra 16 NITs reales del exógena: 16/16
correctos**. Ya quedó enchufado: al crear un tercero sin DV, INTEGRAL lo calcula
solo. Útil para validar/mostrar NITs (ej. `800197268-4`).

## 2. Librería de consultas de saldos (blueprint para INTEGRAL)

`Funciones.bas` expone **37 funciones de Excel** que jalan saldos de la
contabilidad a celdas. Es el "lenguaje" al que están acostumbrados los usuarios
de Contai, y un plano perfecto para una capa de **consultas de saldos** en
INTEGRAL (ya tenemos las piezas: libro mayor/auxiliar). Familias:

| Función | Qué devuelve | Parámetros clave |
|---|---|---|
| `CTiCuentaDB/CR/SA/SF/MO/NO` | Débitos / Créditos / Saldo Ant. / Saldo Final / Movimiento / Neto de una cuenta | compañía, cuenta ini-fin, tipo, período, NIIF |
| `CTiEstDB/CR/SA/SF/MO` | Igual, pero por **rango de meses/años** | + mes/año inicial-final |
| `CTiCcoDB/CR/SA/SF/MO` | Por **centro de costo** | + CC ini-fin, NIT ini-fin |
| `CTiSNitDB/CR/SA/SF/MO/BaseMes` | Por **NIT / tercero** | cuenta, NIT ini-fin, período |
| `CTiCcoNom` | Nombre del centro de costo | |
| `CTiPptoValor` | Valor **presupuestado** (P) o real | cuenta, CC, mes, año |

Con esto podríamos ofrecer en INTEGRAL las mismas consultas (por cuenta, CC, NIT,
mes) y hasta un add-in de Excel/Sheets que lea de `cn_movimientos`.

## 3. Presupuestos (feature del roadmap) — modelo de datos revelado

`CsPresupuesto.cls` + `Globales.bas` muestran el archivo `CNPPTOS.BTV` y su
estructura por registro: **período · cuenta · centro de costo · valor
presupuestado · valor real**. Es justo lo que necesitaríamos para el módulo de
**presupuestos**: una tabla `cn_presupuesto(empresa_id, periodo, cuenta,
centro_costo, valor_ppto)` y comparar contra el real de `cn_movimientos`.

## 4. Acceso a datos Btrieve (para leer los .BTV "de verdad")

`APIBtrieve.bas` trae la API Btrieve (operaciones OPEN/GET_EQUAL/GET_NEXT…) y
`csUtilidades.FnByteArrayToDouble/FnDoubleToByteArray` revela cómo Contai
**codifica los números** (double de 8 bytes). Si algún día traemos los archivos
de movimiento reales desde el RDP, con esto se pueden **parsear campo por campo**
(no por heurística de strings como hicimos con el PUC).

## 5. Otros datos de la carpeta

- `Globales.bas`: nombres de archivos del sistema — `CNINSTAL.USU` (usuarios),
  `CNINSTAL.emp` (compañías), `CNINSTAL.DIR`, `CNPPTOS.BTV` (presupuestos).
- `csUtilidades.FnDecodificar_Cadena`: el **decodificador** de las cadenas
  ofuscadas del `config.ini` (endpoints Siigo/DIAN). No lo uso para sacar tokens
  (son secretos), pero explica cómo están guardados.
- `CNIMPCER.BTV`: definiciones de formato de **medios magnéticos / certificados**
  (campos tipo "No. Identificación", "Número de documento…").

## Archivos de referencia incluidos

`Funciones.bas`, `csUtilidades.cls`, `APIBtrieve.bas`, `Globales.bas`,
`CsPresupuesto.cls` — el código VBA extraído, por si quieres consultarlo al
construir presupuestos o las consultas de saldos.

## Siguientes pasos sugeridos

1. **Consultas de saldos** en INTEGRAL replicando `CTiCuenta*/CTiCco*/CTiSNit*`
   (por cuenta, CC, NIT, mes) — reusa el núcleo `cn_movimientos`.
2. **Presupuestos**: tabla `cn_presupuesto` + comparativo ppto vs real.
3. (Opcional) Add-in de Excel/Google Sheets que consuma esas consultas.
