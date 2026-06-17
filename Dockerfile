# Dockerfile  (raíz del repo)
# Imagen oficial de Playwright: ya trae Chromium y sus librerías.

FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Arrancamos Streamlit con "python -m" para no depender del PATH.
# Railway inyecta $PORT; hay que escuchar en 0.0.0.0 y en ese puerto.
CMD python -m streamlit run Home.py \
    --server.port $PORT \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false
