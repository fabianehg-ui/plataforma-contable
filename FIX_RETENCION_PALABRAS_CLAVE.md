# Retención F350 — clasificación por palabras clave (además de por cuenta)

## Problema
La retefuente por **regalías** se clasificaba como **Contratos de construcción**
(casilla 51). Causa: la cuenta `23-65-70` en el PUC es "Contratos construcción",
y el clasificador miraba **primero el código** y nunca llegaba al nombre —aunque
la cuenta se llame **"REGALIAS Y FRANQUICIAS 2.5%"**.

## Solución (`core/f350/clasificador.py`)
Se agregó una capa de **palabras clave PRIORITARIAS** sobre el **nombre** de la
cuenta, que corre **antes** del código PUC. Si el nombre dice claramente el
concepto (REGALIAS, ARRENDAMIENT, SERVICIO, FLETE, HONORARIO, COMISION,
DIVIDENDO, LICENCIAM, CONSTRUCCION, LOTER/RIFA, COMPRA…), **manda el nombre**.
Si el nombre no tiene palabra clave, sigue formulando **por cuenta** (como antes).

Resultado con tu reporte de junio (SILLA TRES):

| Cuenta        | Nombre                       | Antes                | Ahora            | Casilla |
|---------------|------------------------------|----------------------|------------------|---------|
| 23-65-70-02   | REGALIAS Y FRANQUICIAS 2.5%  | Contratos construcc. | **Regalías**     | 47 ✅   |
| 23-65-30-05   | ARRENDAMIENT BIENES INM 3.5% | Arrendamientos       | Arrendamientos   | 46      |
| 23-65-25-05   | SERVICIOS DEL 4%             | Servicios            | Servicios        | 44      |
| 23-65-25-20   | FLETES                       | Servicios            | Servicios        | 44      |
| 23-65-40-20   | RETECION COMPR 2.5%          | Compras              | Compras          | 49      |

## Cómo agregar más palabras clave
En `core/f350/clasificador.py`, edita la lista **`REGLAS_NOMBRE_PRIORITARIO`**
(arriba del archivo). Formato `("PALABRA_EN_MAYÚSCULAS", "Concepto")`, en orden
de prioridad (la primera que coincida gana). Ej.: `("PEAJE", "Servicios")`.

## Archivos
`core/f350/clasificador.py` (capa nueva) · `tests/test_f350.py` (4 tests nuevos,
32/32 en verde).

> Nota: en la UI de Retención puedes seguir **reclasificando manualmente** una
> fila si hiciera falta. Si quieres, luego hacemos que la lista de palabras clave
> se edite desde Configuración (sin tocar código).
