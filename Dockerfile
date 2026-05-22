# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Build Rust native extension
FROM python:3.12-slim AS rust-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Rust toolchain (stable, minimal profile)
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH="/usr/local/cargo/bin:$PATH"
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable --profile minimal

RUN pip install --no-cache-dir maturin

WORKDIR /build
COPY Cargo.toml ./
COPY src/ ./src/
COPY aidd_intern_core/ ./aidd_intern_core/

# Build the extension wheel in release mode
RUN maturin build --release --out /build/wheels

# Stage 3: Production
FROM python:3.12-slim

# Install uv directly from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create user with UID 1000 (required for HF Spaces)
RUN useradd -m -u 1000 user

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into /app/.venv
# Use --frozen to ensure exact versions from uv.lock
RUN uv sync --no-dev --frozen

# Install Rust native extension from pre-built wheel
COPY --from=rust-builder /build/wheels/*.whl /tmp/
RUN uv pip install --no-deps /tmp/*.whl && rm -f /tmp/*.whl

# Copy application code
COPY agent/ ./agent/
COPY backend/ ./backend/
COPY configs/ ./configs/
COPY aidd_intern_core/ ./aidd_intern_core/

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./static/

# Create directories and set ownership
RUN mkdir -p /app/session_logs && \
    chown -R user:user /app

# Switch to non-root user
USER user

# Set environment
ENV HOME=/home/user \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH"

# Expose port
EXPOSE 7860

# Run the application from backend directory
WORKDIR /app/backend
CMD ["bash", "start.sh"]
