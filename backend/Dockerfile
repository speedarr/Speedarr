# Speedarr Single-Container Dockerfile with Frontend

# Stage 1: Build React Frontend
FROM node:20.11-alpine3.19 AS frontend-builder

WORKDIR /frontend

# Copy package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm install

# Copy frontend source
COPY frontend/ ./

# Build frontend
RUN npm run build

# Stage 2: Python Backend + Serve Frontend
FROM python:3.11.7-slim-bookworm AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    supervisor \
    gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application
COPY backend/app/ ./app/

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
LABEL org.opencontainers.image.description="Intelligent bandwidth management for Plex and download clients"
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
