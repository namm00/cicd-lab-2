FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG APP_VERSION=local
ENV VITE_APP_VERSION=${APP_VERSION}
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
COPY --from=build --chown=node:node /app/dist ./dist
COPY --chown=node:node server.mjs ./
USER node
ENV BACKEND_URL=http://backend:8000
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=6 \
    CMD node -e "fetch('http://127.0.0.1:8080/').then(r => process.exit(r.status === 200 ? 0 : 1)).catch(() => process.exit(1))"
CMD ["node", "server.mjs"]
