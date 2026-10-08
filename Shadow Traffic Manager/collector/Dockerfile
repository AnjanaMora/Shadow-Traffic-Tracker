# =============================================================================
# Stage 1: Build & Dependency Resolution
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY shared/ /build/shared/
RUN pip install --no-cache-dir -e /build/shared/python

COPY collector/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir -r /build/requirements.txt

# =============================================================================
# Stage 2: Minimal Production Runtime
# =============================================================================
FROM python:3.11-slim AS runner

RUN groupadd -g 10001 shadow && \
    useradd -u 10001 -g shadow -m -s /bin/false shadow

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/shared /app/shared
COPY collector/src/ /app/src/

RUN chown -R shadow:shadow /app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

USER shadow

CMD ["python", "-m", "src.agent"]
