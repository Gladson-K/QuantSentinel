FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/v1_impl:/app/v2_impl:/app/v3_impl
COPY . .
CMD ["python", "-m", "unittest", "discover", "-s", "/app", "-t", "/app", "-p", "test_*.py", "-v"]
