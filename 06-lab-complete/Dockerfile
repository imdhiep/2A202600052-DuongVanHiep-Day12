# ============================================================
# Production Dockerfile - multi-stage, slim, non-root
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install --yes --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.11-slim AS runtime

RUN groupadd --system agent \
    && useradd --system --gid agent --create-home --home-dir /home/agent agent

WORKDIR /app

COPY --from=builder /root/.local /home/agent/.local
COPY app/ ./app/
COPY utils/ ./utils/

RUN chown -R agent:agent /app /home/agent

USER agent

ENV PATH=/home/agent/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WEB_CONCURRENCY=2

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2}"]
