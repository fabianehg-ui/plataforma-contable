# Registrar la pagina "Siigo Web" en Home.py

1) Copia `core/siigo/web.py` dentro de tu `core/siigo/`.
2) Copia `app_pages/16_Siigo_Web.py` dentro de tu `app_pages/`.
3) En `Home.py`, junto a las otras definiciones `st.Page(...)`, agrega:

```python
asistente_siigo_web = st.Page(
    "app_pages/16_Siigo_Web.py",
    title="Siigo Web (sin API)",
    icon="🌐",
    url_path="siigo-web",
)
```

4) Anadelo al grupo de navegacion (por ejemplo "Asistente Contable"):

```python
        "🤖 Asistente Contable": [
            ...,
            asistente_siigo,        # el conector por API (si ya lo tienes)
            asistente_siigo_web,    # <-- NUEVO: version web sin API
            asistente_pila,
        ],
```

5) Commit/push y espera el redeploy de Railway.

Nota: `requests` ya esta en tu requirements.txt.

## Modo C (usuario y contraseña) — requisitos extra
El login server-side usa Playwright (navegador headless). En Railway agrega al
Dockerfile la instalación del navegador y sus dependencias:

```dockerfile
RUN pip install playwright && playwright install --with-deps chromium
```

Ten en cuenta: no funciona con MFA/CAPTCHA, es pesado, y va contra los términos
de Siigo. La contraseña NO se guarda (se usa una vez para obtener el refresh token).
