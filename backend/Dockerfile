# ── Stage 1: install dependencies ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install -e .

# ── Stage 2: lean runtime image ────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

EXPOSE 8000

# 2 workers handles concurrent requests without OOMing on 512 MB
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
