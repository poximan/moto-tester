FROM node:24.18.0-alpine AS frontend-builder

WORKDIR /workspace/products/moto-tester/trasvase-tester/frontend
COPY --from=frontend-foundation / /workspace/platform/frontend-foundation
COPY trasvase-tester/frontend/package.json ./package.json
COPY trasvase-tester/frontend/package-lock.json ./package-lock.json
COPY trasvase-tester/frontend/tsconfig.json ./tsconfig.json
COPY trasvase-tester/frontend/vite.config.ts ./vite.config.ts
COPY trasvase-tester/frontend/index.html ./index.html
COPY trasvase-tester/frontend/public ./public
COPY trasvase-tester/frontend/src ./src
RUN npm ci --ignore-scripts --no-audit --no-fund
RUN npm run build

FROM python:3.12-slim-bookworm

ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid "${APP_GID}" appgroup \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /bin/sh appuser \
    && install -d -o "${APP_UID}" -g "${APP_GID}" /app /app/runtime /shared

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/trasvase-tester \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8080

WORKDIR /app
COPY --chown=${APP_UID}:${APP_GID} requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=${APP_UID}:${APP_GID} trasvase-tester/app ./trasvase-tester/app
COPY --from=frontend-builder --chown=${APP_UID}:${APP_GID} \
    /workspace/products/moto-tester/trasvase-tester/frontend/dist \
    /app/trasvase-tester/frontend
COPY --chown=${APP_UID}:${APP_GID} config ./config
COPY --chown=${APP_UID}:${APP_GID} docs ./docs

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=20 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2).read()"

USER 1000:1000

CMD ["sh", "-c", "uvicorn app.main:app --host ${WEB_HOST} --port ${WEB_PORT}"]
