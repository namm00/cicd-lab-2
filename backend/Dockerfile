FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home appuser
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
USER appuser

FROM base AS test
ENV PYTEST_ADDOPTS="-o cache_dir=/tmp/pytest-cache" RUFF_CACHE_DIR=/tmp/ruff-cache
USER root
COPY requirements-dev.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
USER appuser
CMD ["sh", "-c", "alembic upgrade head && alembic check && pytest"]

FROM base AS runtime
ARG APP_VERSION=local
ENV APP_VERSION=${APP_VERSION}
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=6 \
    CMD python -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4); assert r.status == 200 and json.load(r) == {'status':'ok'}"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
