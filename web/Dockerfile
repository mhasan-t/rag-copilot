# --- Development: Vite dev server with hot reload (docker-compose.dev.yaml) ---
FROM node:24-slim AS dev

# Dependencies live in /opt/web/node_modules and the source in /opt/web/app, so the dev bind mount over the source
# doesn't hide them; Node finds them by walking up from /opt/web/app.
WORKDIR /opt/web
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
ENV PATH=/opt/web/node_modules/.bin:$PATH

WORKDIR /opt/web/app
COPY . .
# Mount point that masks a host node_modules (see docker-compose.dev.yaml); Vite keeps its cache there.
RUN mkdir -p node_modules && chown -R node:node /opt/web/app
USER node

EXPOSE 5173
CMD ["vite", "--host", "0.0.0.0"]

# --- Production build ---
FROM dev AS build
RUN vite build

# --- Production: static files, with /v1 forwarded to the API ---
FROM nginxinc/nginx-unprivileged:1.29-alpine AS prod

# Where /v1 requests go, e.g. http://api:8000 (rendered into the config at startup by the image's envsubst step).
ENV API_UPSTREAM=http://api:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /opt/web/app/dist /usr/share/nginx/html

EXPOSE 8080
