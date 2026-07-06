# Conector Siigo → Contai (módulo Python para ContaTools)

Porta la extensión de Chrome a tu repo de Streamlit: trae datos de Siigo por la
**API oficial** (server-side) y genera los planos de Contai, sin que nadie instale
nada en su navegador.

## Estructura

```
core/siigo/
  ├─ __init__.py
  ├─ cliente.py    # auth + descarga día por día con reintentos (invoices,
  │                #   vouchers, credit-notes, customers)
  ├─ empresas.py   # lista de empresas + Access Key cifrada + plan por empresa
  └─ planos.py     # armado de planos: ventas (plan de cuentas o legado),
                   #   recibos (cancelar por saldo / desde Siigo), NITs
pages/
  └─ 90_Siigo_a_Contai.py   # página Streamlit con selector de empresa
```

## Instalación

1. Copia `core/siigo/` dentro del `core/` de tu repo.
2. Copia `pages/90_Siigo_a_Contai.py` a tu carpeta de páginas (renómbrala con el
   prefijo que uses; si tu repo usa `app_pages/`, muévela allí).
3. Dependencias: `streamlit`, `requests`, `openpyxl` (para el .xlsx de NITs).
   Agrégalas a tu `requirements.txt` si faltan.

## Uso desde la página

1. Ingresa credenciales de Siigo (Usuario API, Access Key, Partner-Id).
2. Elige el rango de fechas y pulsa **Detectar prefijos del rango**.
3. Completa comprobante/centro por prefijo y el **plan de cuentas** (cuenta por
   cobrar, efectivo, y una cuenta por cada base e IVA detectados).
4. Marca qué exportar (Ventas / Recibos / NITs) y **Genera**. Descarga los `.txt`
   e impórtalos en Contai (*Procesos → Intercambio de Datos → Importar*).

## Recibos: dos modos

- **Cancelar todas las facturas**: un recibo por factura, por su **saldo pendiente**
  (`balance` de Siigo). Omite las de saldo 0 (nota crédito o ya pagadas). Pide el
  consecutivo inicial.
- **Solo los recibos asentados en Siigo**: baja `/v1/vouchers` y reproduce sus
  asientos, cruzando contra la factura que pagan. Para empresas que conservan cartera.

## Empresas y credenciales (importante)

La API de Siigo **no usa la contraseña web**: usa **usuario + Access Key** (la
"Credencial API" que se genera dentro de cada empresa en Siigo Nube →
*Alianzas → Mi Credencial API*). No existe un "un login → lista de empresas" en la
API oficial.

Por eso el modelo es: **cada empresa se registra una vez** con su Access Key, y
todas comparten el **mismo Partner-Id**. La página muestra un **selector de empresa**
en la barra lateral; al elegirla, el repo opera directamente sobre esa empresa, y
recuerda su plan de cuentas.

- El almacén por defecto (`empresas.py`) guarda las empresas en un JSON local y
  **cifra la Access Key** si defines la variable de entorno `SIIGO_STORE_KEY`
  (una clave Fernet). Sin esa variable, guarda en texto plano y la página lo
  advierte — **no lo uses así en producción**.
- Genera la clave una vez:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  y ponla en `SIIGO_STORE_KEY` (o en `st.secrets`). Añade `cryptography` al
  `requirements.txt`.
- **Producción:** reemplaza `empresas.py` por tu tabla en **Supabase** (mismas
  funciones: `list_empresas`, `get_credenciales`, `upsert_empresa`,
  `delete_empresa`, `get_config`, `save_config`), guardando la Access Key cifrada.

> Emular el login web con usuario+contraseña para "descubrir" las empresas es
> frágil, inseguro y va contra los términos de Siigo. No se hace.

## Uso del core desde código (sin la página)

```python
from core.siigo import cliente, planos

token = cliente.authenticate(username, access_key, partner_id)
invoices = cliente.get_invoices(token, partner_id, "2026-05-01", "2026-05-31")

mapeo = {"FESD": {"comprobante": "004FE", "centro": "1005"}}
plan = {
    "cuentaPorCobrar": "13050502", "cuentaEfectivo": "11050503",
    "bases": {"BASE_EXCLUIDA": "41659503"}, "impuestos": {},
}
plano_ventas = planos.build_ventas(invoices, mapeo, plan)      # str (TXT)
recibos = planos.build_recibos_cancelar(invoices, 500, mapeo, plan)  # dict: content, rango, omitidas
```

Si no pasas `plan`, ventas usa el modo legado (Db 13050502 / Cr 41659503).

## Pendiente (siguiente paso)

Compras (`/v1/purchases`) y notas crédito (`/v1/credit-notes`) tienen su cliente
listo en `cliente.get_credit_notes` / (por agregar `get_purchases`), pero el
armado de su plano necesita un JSON real de esa empresa para mapear las cuentas.
