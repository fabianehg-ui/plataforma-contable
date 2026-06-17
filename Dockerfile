# Dockerfile  (raíz del repo) - version a prueba de balas con log de puerto
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Creamos un script de arranque interno. El ${PORT} se resuelve al ejecutar,
# no al construir. Imprime el puerto para verlo en Deploy Logs.
RUN printf '#!/bin/sh\necho "=== Arrancando Streamlit en puerto: ${PORT:-8080} ==="\nexec python -m streamlit run Home.py --server.port "${PORT:-8080}" --server.address 0.0.0.0 --server.headless true --server.enableCORS false --server.enableXsrfProtection false\n' > /app/start.sh \
    && chmod +x /app/start.sh

CMD ["/app/start.sh"]
