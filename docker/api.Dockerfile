# Placeholder API image; expand with multi-stage build and non-root user.
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
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
