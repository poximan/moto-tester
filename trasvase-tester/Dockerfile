FROM python:3.12-slim

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
COPY --chown=${APP_UID}:${APP_GID} trasvase-tester ./trasvase-tester
COPY --chown=${APP_UID}:${APP_GID} config ./config
COPY --chown=${APP_UID}:${APP_GID} docs ./docs

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=20 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2).read()"

USER 1000:1000

CMD ["sh", "-c", "uvicorn app.main:app --host ${WEB_HOST} --port ${WEB_PORT}"]
