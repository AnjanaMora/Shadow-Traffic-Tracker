# =============================================================================
# Stage 1: Build & Dependency Resolution
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for clean isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install shared library
COPY shared/ /build/shared/
RUN pip install --no-cache-dir -e /build/shared/python

# Install backend dependencies
COPY backend/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir -r /build/requirements.txt

# =============================================================================
# Stage 2: Minimal Production Runtime
# =============================================================================
FROM python:3.11-slim AS runner

# Install only curl for container healthchecking
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 10001 shadow && \
    useradd -u 10001 -g shadow -m -s /bin/false shadow

WORKDIR /app

# Copy virtual environment and shared packages from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/shared /app/shared

# Copy application source code
COPY backend/src/ /app/src/

# Set ownership
RUN chown -R shadow:shadow /app

# Configure execution environment
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

USER shadow

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
