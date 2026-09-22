# Speedarr Single-Container Dockerfile with Frontend

# Build args (declared globally, re-declared per stage as needed)
ARG SPEEDARR_VERSION=dev
ARG SPEEDARR_COMMIT=unknown
ARG SPEEDARR_BRANCH=unknown

# Stage 1: Build React Frontend
FROM node:24.21.0-alpine3.24 AS frontend-builder

# Re-declare ARGs for this stage
ARG SPEEDARR_VERSION
ARG SPEEDARR_COMMIT
ARG SPEEDARR_BRANCH

# Set as env vars for Vite define (read at build time)
ENV VITE_APP_VERSION=${SPEEDARR_VERSION}
ENV VITE_APP_COMMIT=${SPEEDARR_COMMIT}
ENV VITE_APP_BRANCH=${SPEEDARR_BRANCH}

WORKDIR /frontend

# Copy package files
COPY frontend/package*.json ./

# Install dependencies from the committed lockfile for reproducible builds
# Retries cover the arm64 leg of Develop Build, which runs npm ci under QEMU and has failed with ECONNRESET
RUN npm ci --fetch-retries=5 --fetch-retry-maxtimeout=120000

# Copy frontend source
COPY frontend/ ./

# Unit tests gate the image the same way tsc does: a red test fails the build
RUN npm test

# Build frontend
RUN npm run build

# Stage 2: Python Backend + Serve Frontend
FROM python:3.14.7-slim-bookworm AS base

# Re-declare ARGs for this stage
ARG SPEEDARR_VERSION
ARG SPEEDARR_COMMIT
ARG SPEEDARR_BRANCH

# Set as env vars for backend runtime (os.getenv)
ENV SPEEDARR_VERSION=${SPEEDARR_VERSION}
ENV SPEEDARR_COMMIT=${SPEEDARR_COMMIT}
ENV SPEEDARR_BRANCH=${SPEEDARR_BRANCH}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    supervisor \
    gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python requirements and install (wheels only: every pin ships a wheel for amd64 and arm64)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

# Copy backend application
COPY backend/app/ ./app/

# Copy backend tests
COPY backend/tests/ ./tests/

# Copy built frontend from previous stage
COPY --from=frontend-builder /frontend/dist/ ./static/

# Create non-root user and data directory
RUN useradd -r -s /sbin/nologin speedarr \
    && mkdir -p /data \
    && chown -R speedarr:speedarr /data

# Copy supervisor configuration
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN chmod 644 /etc/supervisor/conf.d/supervisord.conf

# Copy entrypoint script
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

# Make app files readable by non-root user
RUN chmod -R a+rX /app

# Container metadata
LABEL org.opencontainers.image.title="Speedarr"
LABEL org.opencontainers.image.description="Smooth streams first, downloads and seeding with what's left"
LABEL org.opencontainers.image.source="https://github.com/speedarr/speedarr"
LABEL org.opencontainers.image.licenses="MIT"

# Expose FastAPI port
EXPOSE 9494

# Volume for persistent data (SQLite database)
VOLUME ["/data"]

# Note: Container starts as root, entrypoint switches to speedarr user
# after applying PUID/PGID settings

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
