FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS builder

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./

ARG VITE_API_URL=/api
ARG VITE_PUBLIC_REGISTRATION_ENABLED=false
ARG VITE_ENABLE_SOURCEMAPS=false
ENV VITE_API_URL=${VITE_API_URL} \
    VITE_PUBLIC_REGISTRATION_ENABLED=${VITE_PUBLIC_REGISTRATION_ENABLED} \
    VITE_ENABLE_SOURCEMAPS=${VITE_ENABLE_SOURCEMAPS}
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6 AS runtime

LABEL org.opencontainers.image.title="InfraSentinel AI dashboard" \
      org.opencontainers.image.description="React dashboard served by unprivileged Nginx"

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

USER 101:101
EXPOSE 8080
