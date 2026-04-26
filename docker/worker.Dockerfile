# Placeholder worker image; point CMD at your queue runner (arq/celery/etc.).
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app app
COPY db db
COPY services services
COPY connectors connectors
COPY workers workers
COPY media media
RUN pip install --no-cache-dir .
CMD ["python", "-c", "print('worker entrypoint TBD')"]
