# Módulo F350 — Diligenciar borrador en Muisca (DIAN) y descargar PDF

Añade a tu repo, dentro de `core/f350/`:
- `muisca_client.py` — cliente que loguea, llena el borrador por renglón y baja el PDF.
- `cifrado_dian.py` — cifra las credenciales DIAN por empresa (Fernet) antes de Supabase.
- `plantilla_f350_v10.json` — estructura de casillas del F350 v10 (respaldo si la API no responde).

## Flujo (todo contra `api.dian.gov.co`, login en `muisca.dian.gov.co`)
1. **login** — `POST /IdentidadRest_Acceso/api/sts/v1/auth/weblogin` (clave en base64) + `POST /identidad/sts/v2/cookies/token`.
2. **obtener_borrador** — `GET /documentos/retefuente350v10/v1/formularios/borrador?modo=inicial&anio=&periodicidad=mensual&periodo=`.
3. **construir_doc** — coloca cada valor en su renglón: `cs_id_{renglon} = valor` (cs_id_27 = actividad económica, renglón 27).
4. **guardar_borrador** — `POST /documentos/retefuente350v10/v1/formularios` → devuelve el `id`.
5. **descargar_pdf** — `GET /documentos/retefuente350v10/v1/formularios/{id}/descargar` → PDF.

## Uso desde la página del módulo
```python
from core.f350.muisca_client import MuiscaF350Client

cli = MuiscaF350Client()
ruta, form_id = cli.diligenciar_y_descargar(
    tipo_doc="CC", num_doc="<cedula>", nit_empresa="901477071", password="<clave>",
    nit="901477071", dv="9", razon_social="NUTRIENDO ALMAS S.A.S.",
    anio=2026, periodo=6, actividad_economica="5612",
    valores_por_renglon={29: 1200000, 36: 450000, 74: 98000},   # {renglon: valor} que ya calcula tu módulo
    ruta_pdf="/tmp/F350_borrador.pdf",
)
```
`valores_por_renglon` es justamente la salida que tu módulo F350 ya produce por concepto/renglón.

## Seguridad
- Genera la clave de cifrado y ponla en el entorno (Railway), nunca en el repo:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` → `F350_FERNET_KEY`.
- Guarda por empresa el token cifrado: `cifrar(json.dumps({"tipo_doc","num_doc","password"}))`.
- **Alcance:** el cliente llega hasta **descargar el borrador en PDF**. La firma/presentación las hace el contador tras revisar. No encadenes la presentación automática.

## Pendiente de validar en vivo (no se puede probar contra la DIAN desde el generador)
1. **Mapeo renglón→casilla:** se asume `cs_id_N = renglón N` (confirmado para el 27). Corre una vez con pocos valores, baja el PDF y verifica que caen en el renglón correcto; si hay desfase, ajusta el mapeo.
2. **Login/cookies:** si el `login()` no deja sesión, revisa headers/redirecciones (algunas veces el token va en un header o requiere un paso extra). El HAR muestra que la sesión es por cookies httpOnly.
3. **clientId:** el valor `CLIENT_ID` puede rotar; si el login falla, tómalo de la petición weblogin del portal.
