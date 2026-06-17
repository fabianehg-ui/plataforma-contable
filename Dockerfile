# Dockerfile  (ALTERNATIVA, la más robusta)
# Si el nixpacks.toml da errores al lanzar Chromium, usa este Dockerfile:
# Railway lo detecta automáticamente y construye con él en vez de Nixpacks.
# Trae Chromium y TODAS sus librerías ya instaladas.

FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# el navegador ya viene en la imagen; esto solo asegura la versión
RUN python -m playwright install chromium

COPY . .

# Railway inyecta $PORT
CMD streamlit run Home.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
