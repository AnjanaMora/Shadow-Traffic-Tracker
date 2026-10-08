# =============================================================================
# Stage 1: Build Production Assets with Node & Vite
# =============================================================================
FROM node:20-alpine AS build

WORKDIR /app

# Leverage caching for dependencies
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci || npm install

# Build production bundle
COPY dashboard/ ./
RUN npm run build

# =============================================================================
# Stage 2: Serve via Hardened Nginx
# =============================================================================
FROM nginx:alpine AS runner

# Remove default configuration
RUN rm -rf /etc/nginx/conf.d/*

# Copy compiled assets from builder
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY dashboard/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
