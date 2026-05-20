FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    RIGOL_HOST=192.168.1.34 \
    RIGOL_SCPI_PORT=5555 \
    RIGOL_HTTP_PORT=80 \
    RIGOL_STORAGE_DIR=/data

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY docs ./docs

RUN pip install --no-cache-dir .

VOLUME ["/data"]

CMD ["rigol-dho814-mcp"]

