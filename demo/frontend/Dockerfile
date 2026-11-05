FROM node:20-alpine AS build
WORKDIR /app

# NPM_REGISTRY comes from .env via compose (e.g. https://registry.npmmirror.com)
ARG NPM_REGISTRY=https://registry.npmjs.org
COPY package.json package-lock.json ./
RUN npm config set registry "$NPM_REGISTRY" && npm ci --no-audit --no-fund

COPY . .
# the frontend only requests the relative path /api: nothing about the backend is baked in
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
