# Dockerfile  (raíz del repo)
# Imagen oficial de Playwright: ya trae Chromium y sus librerías.

FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# sh -c hace que la shell expanda ${PORT} en tiempo de ejecución.
# Si Railway no inyectara PORT, usa 8080 por defecto.
CMD ["sh", "-c", "python -m streamlit run Home.py --server.port ${PORT:-8080} --server.address 0.0.0.0 --server.headless true --server.enableCORS false --server.enableXsrfProtection false"]
