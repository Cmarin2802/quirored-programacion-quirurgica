FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY ["9 Aplicacion Web/requirements.txt", "/tmp/quirored-requirements.txt"]
RUN pip install --no-cache-dir -r /tmp/quirored-requirements.txt

COPY ["9 Aplicacion Web/", "/app/9 Aplicacion Web/"]
COPY ["geo/", "/app/geo/"]
COPY ["benchmarks/", "/app/benchmarks/"]

RUN useradd --create-home --uid 10001 quirored
USER quirored

WORKDIR "/app/9 Aplicacion Web/backend"
EXPOSE 8080

CMD ["sh", "-c", "exec gunicorn --workers 1 --threads 2 --bind 0.0.0.0:${PORT:-8080} --timeout 120 app:app"]
