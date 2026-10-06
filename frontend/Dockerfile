# syntax=docker/dockerfile:1
# SafeSpeak PES frontend: production React build served by an unprivileged nginx.
#   docker build -t safespeak-frontend frontend
# The UI calls the API at the relative path /api/v1 (same origin through the
# reverse proxy), so no CORS and no backend address are baked into the build.

FROM node:22-bookworm-slim AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget -qO /dev/null http://127.0.0.1:8080/ || exit 1
