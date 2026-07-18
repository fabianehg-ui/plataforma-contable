# Reorganización de menús + arreglo de scroll + módulo de plano

## ⚠️ Arreglo IMPORTANTE del scroll (asientos/Captura)
En `core/tema.py` había una regla que le quitaba el `overflow` al contenedor que
Streamlit usa para desplazarse, y por eso la página de asientos **no bajaba** al
pie. **Ya se quitó.** Con este `tema.py` el scroll vuelve a la normalidad; solo se
deja un poco de espacio extra abajo. **Sube este archivo sí o sí.**

## Reorganización del menú (`Home.py`)
- **Correcciones** pasó de *Sistema* → **Asistente Contable**.
- Nueva sección **🔌 Integraciones** (dentro de Asistente Contable) con:
  **Cargar plano Contai (TXT)** · **Bittal a Contai** · **Siigo a Contai** · **Bancos a Contai**.
- Se **quitaron del menú** (siguen los archivos en el repo, no se borraron):
  - **Provisiones** y **PILA** → sus funciones las cubre **Nómina**.
  - **Siigo Web (sin API)** → no lograba entrar a la página de Siigo.

  > Si confirmas que Nómina cubre todo, luego borramos esos archivos del repo
  > (`4_Provisiones.py`, `5_PILA.py`, `16_Siigo_Web.py`). Por ahora solo quedaron
  > ocultos del menú, sin riesgo.

## Nuevo módulo: 📄 Cargar plano Contai (TXT)
`app_pages/28_Cargar_Plano_Contai.py` — sube un TXT/CSV de 11 columnas (formato
Contai, sin encabezado) o pégalo; muestra vista previa + cuadre; permite
**descargar el plano normalizado** o **agregarlo al movimiento del mes**
(cn_movimientos, con selector de período). Queda asociado a la empresa activa.
También trae su ayuda animada.

Archivos: `core/ayuda.py` (guía nueva) · `core/contable/integracion.py` (origen
"plano_contai") · `Home.py` · `app_pages/28_Cargar_Plano_Contai.py` · `core/tema.py`.

## Pendiente que mencionaste (para después)
- El módulo de **XML DIAN se cayó**; queda por armar uno de **contabilidad desde
  Excel (reporte DIAN)**. Lo hacemos cuando digas.
