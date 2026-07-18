# CÓMO SUBIR — Guarda de empresa en todas las páginas + acceso por empresa

Ninguna página opera ya sin saber a qué empresa pertenece, y cada usuario solo
ve su(s) empresa(s); tu usuario general (superadmin) las ve todas y puede
cambiar. Fecha: 18-jul-2026. **Sin migración.**

## 1. Guarda estándar de página (nuevo)

`auth/guard.py`:
- `guard_empresa(roles=…)` — una línea al inicio de una página: exige login,
  fija la **empresa activa** (sidebar) y muestra el banner **"🏢 Empresa activa:
  X"**. Devuelve `(emp, sb)`.
- `guard_login()` — solo login, para páginas multi-empresa.

Aplicada a las páginas que antes NO fijaban empresa: **Bittal (4c y NN), Bancos,
Siigo (a Contai / Web / Excel), RADIAN (acuses recibidos y VPFE)**. El **DIAN XML
masivo (5a)** se deja multi-empresa a propósito, con un aviso claro de que causa
a la empresa de cada documento (no a una sola).

Toda página futura usa la misma línea: `emp, sb = guard_empresa()`.

## 2. Acceso por empresa (privacidad multi-empresa)

`auth/empresas.py → empresas_del_usuario()`:
- **Usuario normal**: SOLO las empresas a las que fue asignado (tabla
  `usuario_empresa`). Si tiene una, queda fija en esa; no ve las demás.
- **Superadmin (tu usuario general)**: TODAS las empresas activas, y puede
  **cambiar de empresa** en cualquier momento desde el sidebar.

El sidebar ahora indica el modo: "🔑 Superadmin — todas las empresas" o "Acceso
restringido a tu empresa asignada".

## Archivos

| Archivo | Estado |
|---|---|
| `auth/guard.py` | **NUEVO** — guarda reusable. |
| `auth/empresas.py` | **MOD** — superadmin ve todas; normal solo asignadas; indicador en sidebar. |
| `app_pages/4c_Bittal…`, `NN_Bittal…`, `19_Bancos…`, `15/16/17_Siigo…`, `1/6_RADIAN…` | **MOD** — guarda de empresa. |
| `app_pages/5a_DIAN_XML.py` | **MOD** — aviso multi-empresa. |

Sin migración: usa `usuario_empresa`, `superadmins` y el RPC `admin_listar_empresas`
que ya existen. **96 pruebas contables pasan.**

## Cómo asignar usuarios a empresas

Desde **🛡️ Panel Admin** se asignan usuarios a empresas con su rol (admin /
operador / consulta). Un usuario solo entrará a las empresas que le asignes; tu
usuario superadmin entra a todas.
