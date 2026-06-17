# Dockerfile  (raíz del repo)
# Imagen oficial de Playwright: ya trae Chromium y sus librerías instaladas.
# NO se ejecuta "playwright install" aquí: el navegador ya viene en la imagen.

FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway inyecta $PORT
CMD streamlit run Home.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
