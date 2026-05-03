FROM python:3.11-slim AS backend

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/edf_lib/ ./edf_lib/
COPY backend/app/ ./app/
COPY backend/load_data.py .

# ── Final image ──
FROM node:20-alpine AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ── Production ──
FROM python:3.11-slim

WORKDIR /app

# Install Node.js runtime (for Next.js production server)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install supervisord
RUN apt-get update && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/*

# Backend
COPY --from=backend /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=backend /usr/local/bin/uvicorn /usr/local/bin/
COPY --from=backend /app/ /app/backend/

# Frontend
COPY --from=builder /app/.next/ /app/frontend/.next/
COPY --from=builder /app/public/ /app/frontend/public/
COPY --from=builder /app/package.json /app/frontend/
COPY --from=builder /app/package-lock.json /app/frontend/
COPY --from=builder /app/next.config.ts /app/frontend/
COPY --from=builder /app/node_modules/ /app/frontend/node_modules/

# Supervisor config
COPY unraid/supervisord.conf /etc/supervisor/conf.d/cpap.conf

# Data directory
RUN mkdir -p /data/uploads

ENV DATABASE_URL=sqlite:////data/cpap.db
ENV UPLOAD_DIR=/data/uploads
ENV NEXT_PUBLIC_API_URL=http://localhost:8000/api
ENV API_INTERNAL_URL=http://localhost:8000/api

EXPOSE 3000 8000

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/cpap.conf"]
