# ---------- 阶段 1:前端构建 ----------
FROM node:26.4-slim@sha256:a1d9d671994fc2d26e297ac56b4b1522a8bc7fa71c43b14cd1b1fe6c5116f7dc AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- 阶段 2:Python 运行时 ----------
FROM python:3.12-slim@sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system interview \
    && adduser --system --ingroup interview interview

COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

COPY app app
COPY scripts scripts
COPY knowledge knowledge
COPY eval eval
COPY migrations migrations
COPY alembic.ini .

# 拷贝前端构建产物(由阶段 1 产出)
COPY --from=frontend-build /frontend/dist /app/frontend/dist

RUN mkdir -p /app/data \
    && chown -R interview:interview /app

USER interview

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
