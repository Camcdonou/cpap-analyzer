FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Production image ──
FROM node:20-alpine

WORKDIR /app
COPY --from=builder /app/package.json ./
COPY --from=builder /app/package-lock.json ./
COPY --from=builder /app/.next/ ./.next/
COPY --from=builder /app/public/ ./public/
COPY --from=builder /app/next.config.ts ./
COPY --from=builder /app/node_modules/ ./node_modules/

ENV NEXT_PUBLIC_API_URL=http://localhost:8000/api
ENV PORT=3000

EXPOSE 3000

CMD ["npm", "start"]
