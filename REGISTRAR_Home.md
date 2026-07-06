# Cómo hacer que aparezca en el menú (tu repo usa `st.navigation` en Home.py)

Tu plataforma NO usa la carpeta automática `pages/`. Usa `app_pages/` + navegación
explícita en `Home.py` con `st.Page(...)` y `st.navigation({...})`. Por eso, dejar
el archivo en `pages/` no lo muestra. Sigue estos 3 pasos:

## 1) Ubica los archivos
- `core/siigo/`  → va en la RAÍZ del repo, junto a `Home.py` (para que
  `from core.siigo import ...` resuelva; tu `Home.py` ya hace `sys.path.insert(ROOT)`).
- `app_pages/15_Siigo_a_Contai.py` → dentro de tu carpeta `app_pages/`.
  (Si el prefijo 15 choca con otro, renómbralo; el número NO define el orden del
  menú, ese lo controla la lista de `st.navigation`.)

## 2) Regístrala en `Home.py`

Donde defines las páginas con `st.Page(...)`, agrega:

```python
siigo_contai = st.Page(
    "app_pages/15_Siigo_a_Contai.py",
    title="Siigo → Contai",
    icon="🧾",
)
```

Y dentro de tu `st.navigation({...})`, añade `siigo_contai` al grupo donde lo
quieras que aparezca. Por ejemplo:

```python
nav = st.navigation(
    {
        "": [pagina_inicio],
        "🤖 Asistente Contable": [
            asistente_pos,
            asistente_xml,
            siigo_contai,          # <-- NUEVO
        ],
    },
    position="sidebar",
)
nav.run()
```

IMPORTANTE: el archivo de la página NO debe llamar a `st.set_page_config(...)`
(ya lo hace `Home.py`). Este archivo no lo llama, así que está bien.

## 3) Dependencias y deploy
- Agrega a `requirements.txt` (si faltan): `requests`, `openpyxl`, `cryptography`.
- Define la variable de entorno `SIIGO_STORE_KEY` en Railway (clave Fernet) para
  cifrar las Access Keys. Genérala una vez con:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Haz commit/push y espera el redeploy de Railway. La página nueva solo aparece
  tras el redeploy.

## Si prefieres que te deje el Home.py exacto
Pásame el bloque de `st.navigation(...)` de tu `Home.py` actual (o el archivo) y
te devuelvo el `Home.py` con la página ya registrada en el grupo que quieras.
