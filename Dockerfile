# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: builder — install dependencies into a venv
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools
RUN pip install --no-cache-dir hatchling

# Copy only dependency manifests first for better layer caching
COPY pyproject.toml ./

# Create venv and install all extras
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -e ".[tracing]" \
    && pip install --no-cache-dir "redis[asyncio]>=5.0.0"

# ---------------------------------------------------------------------------
# Stage 2: runtime — lean image, non-root user
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY app/ ./app/

# Run as non-root
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
