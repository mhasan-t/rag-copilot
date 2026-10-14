FROM node:24-slim

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
